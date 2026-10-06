"""Comparacion por bandas contra un perfil, y sugerencias de EQ.

Traduce la diferencia entre un tema y su perfil objetivo a algo accionable:
ocho bandas con nombre, cuanto se desvia cada una, si ese desvio cae dentro de
lo que varian las referencias entre si, y que movimiento de EQ lo acercaria.

Las sugerencias son orientativas. Corregir con EQ en el master tapa el sintoma;
lo que suele resolver de verdad es arreglar el elemento que lo causa en la
mezcla. Sirven para saber hacia donde mirar, no como receta.
"""
import numpy as np

# Los nombres son los que se usan al hablar de una mezcla, no divisiones
# arbitrarias: cada uno corresponde a un problema tipico distinto.
BANDAS = [
    ('Sub', 20, 60),
    ('Bass', 60, 120),
    ('Low-mid', 120, 250),
    ('Mid-bass', 250, 500),
    ('Mid', 500, 2000),
    ('Upper-mid', 2000, 5000),
    ('Presence', 5000, 10000),
    ('Air', 10000, 20000),
]

def etiqueta_hz(hz):
    """Frecuencia legible: 500 Hz, 2 kHz, 3.2 kHz."""
    if hz < 1000:
        return f'{hz:.0f} Hz'
    miles = hz / 1000
    return f'{miles:.0f} kHz' if abs(miles - round(miles)) < 0.05 else f'{miles:.1f} kHz'


def etiqueta_rango(desde, hasta):
    """Rango de una banda. Cada extremo se formatea aparte: convertir los dos a
    kilohertz porque uno pasa de mil dejaba '0-2 kHz' para la banda de 500 a 2000."""
    return f'{etiqueta_hz(desde)} - {etiqueta_hz(hasta)}'


MAX_BANDAS_EQ = 8
MAX_GANANCIA_DB = 4.0     # tope de cada movimiento sugerido
MIN_GANANCIA_DB = 0.5     # menos que esto no vale la pena tocar
BORDE_DB = 0.5            # margen desde el limite de tolerancia para 'al borde'


def _centrar(diferencia, peso):
    """Quita el nivel general de la curva de diferencia.

    Las curvas se alinean por sonoridad, y subir una banda sube tambien la
    sonoridad del tema: al alinear se resta parte de lo mismo que se quiere
    medir, asi que un realce ancho se lee mas chico de lo que es y el resto del
    espectro se lee un poco bajo.

    Restando la media ponderada por nivel queda solo la forma, que es lo unico
    que un EQ corrige. El nivel general lo maneja la etapa de ganancia aparte.
    """
    pesos = np.maximum(peso - peso.max() + 40.0, 0.0)   # 40 dB por debajo del pico
    if pesos.sum() <= 0:
        return diferencia - float(np.mean(diferencia))
    return diferencia - float(np.average(diferencia, weights=pesos))


def deviation(curvas, perfil, canal='mid'):
    """Diferencia entre el tema y la mediana del perfil, en dB y ya centrada.

    Devuelve tambien los bordes de tolerancia desplazados igual, para que
    comparar contra ellos siga teniendo sentido despues de centrar.
    """
    objetivo = perfil.get(canal)
    if curvas is None or not objetivo:
        return None
    propia = curvas['mid'] if canal == 'mid' else curvas.get('side')
    if propia is None:
        return None

    cruda = np.asarray(propia) - np.asarray(objetivo['mediana'])
    corrimiento = float(np.mean(cruda - _centrar(cruda, np.asarray(objetivo['mediana']))))
    return {
        'freqs': np.asarray(perfil['freqs']),
        'diferencia': cruda - corrimiento,
        'tolerancia_baja': np.asarray(objetivo['bajo']) - np.asarray(objetivo['mediana']),
        'tolerancia_alta': np.asarray(objetivo['alto']) - np.asarray(objetivo['mediana']),
        'corrimiento_db': corrimiento,
    }


def suavizar(curva, freqs, octavas=1 / 3):
    """Suaviza para dibujar, sin tocar lo que se mide.

    Las curvas vienen a un sexto de octava, que es la resolucion que hace falta
    para medir, pero deja mucho detalle: la linea queda dentada y cuesta ver la
    forma, que es lo unico que se decide mirando. Los promedios por banda de la
    tabla salen de la curva sin suavizar.
    """
    if len(freqs) < 2:
        return curva
    por_octava = (len(freqs) - 1) / np.log2(freqs[-1] / freqs[0])
    ventana = max(1, int(round(por_octava * octavas)))
    if ventana <= 1:
        return curva
    nucleo = np.ones(ventana) / ventana
    # Se extienden los bordes para que no se hundan contra cero
    extendida = np.concatenate([np.full(ventana, curva[0]), curva,
                                np.full(ventana, curva[-1])])
    return np.convolve(extendida, nucleo, mode='same')[ventana:-ventana]


def _promedio(valores, freqs, desde, hasta):
    dentro = (freqs >= desde) & (freqs < hasta)
    return float(np.mean(valores[dentro])) if dentro.any() else None


def estado(desvio, baja, alta):
    """Si el desvio cae dentro de lo que varian las referencias entre si."""
    if desvio is None:
        return 'sin datos'
    if baja - BORDE_DB <= desvio <= alta + BORDE_DB:
        return 'dentro' if baja <= desvio <= alta else 'al borde'
    return 'fuera'


def band_report(dev, dev_side=None):
    """Una fila por banda con su desvio, su estado y el desvio de ancho."""
    if dev is None:
        return []
    freqs = dev['freqs']
    filas = []
    for nombre, desde, hasta in BANDAS:
        desvio = _promedio(dev['diferencia'], freqs, desde, hasta)
        baja = _promedio(dev['tolerancia_baja'], freqs, desde, hasta)
        alta = _promedio(dev['tolerancia_alta'], freqs, desde, hasta)

        ancho = None
        if dev_side is not None:
            lateral = _promedio(dev_side['diferencia'], freqs, desde, hasta)
            if lateral is not None and desvio is not None:
                ancho = lateral - desvio

        filas.append({
            'banda': nombre, 'desde': desde, 'hasta': hasta,
            'desvio_db': desvio,
            'tolerancia': (baja, alta),
            'estado': estado(desvio, baja if baja is not None else -2,
                             alta if alta is not None else 2),
            'ancho_db': ancho,
        })
    return filas


def _q_para(desde, hasta):
    """Q que cubre el ancho de la banda, con la relacion habitual de un bell."""
    octavas = np.log2(hasta / desde)
    return round(float(1 / (2 ** (octavas / 2) - 2 ** (-octavas / 2))), 2)


def eq_suggestions(filas, maximo=MAX_BANDAS_EQ):
    """Movimientos de EQ que acercarian el tema al perfil.

    Uno por banda fuera de tolerancia, con la ganancia al reves del desvio y
    acotada: una correccion mayor a cuatro decibeles en el master casi siempre
    significa que el problema esta en la mezcla y hay que resolverlo ahi.

    Las bandas de los extremos van como shelf porque el desvio ahi no suele
    ser un pico sino toda la zona corrida; las del medio, como bell.
    """
    candidatos = []
    for i, fila in enumerate(filas):
        desvio = fila['desvio_db']
        if desvio is None or fila['estado'] == 'dentro':
            continue
        if abs(desvio) < MIN_GANANCIA_DB:
            continue

        ganancia = float(np.clip(-desvio, -MAX_GANANCIA_DB, MAX_GANANCIA_DB))
        if i == 0:
            tipo, freq, q = 'low shelf', fila['hasta'], 0.71
        elif i == len(filas) - 1:
            tipo, freq, q = 'high shelf', fila['desde'], 0.71
        else:
            tipo = 'bell'
            freq = int(round(np.sqrt(fila['desde'] * fila['hasta'])))
            q = _q_para(fila['desde'], fila['hasta'])

        candidatos.append({
            'banda': fila['banda'], 'tipo': tipo, 'freq_hz': int(freq),
            'ganancia_db': round(ganancia, 1), 'q': q,
            'recortada': abs(desvio) > MAX_GANANCIA_DB,
        })

    # Si sobran, se quedan las correcciones mas grandes
    candidatos.sort(key=lambda c: abs(c['ganancia_db']), reverse=True)
    return sorted(candidatos[:maximo], key=lambda c: c['freq_hz'])


def loudness_summary(resumen, perfil):
    """Sonoridad y pico del tema contra los promedios del perfil."""
    if not perfil:
        return []
    filas = []
    for clave, etiqueta, unidad in (('lufs', 'Sonoridad', 'LUFS'),
                                    ('true_peak_db', 'Pico real', 'dBTP')):
        propio = resumen.get(clave) if resumen else None
        objetivo = perfil.get(clave)
        if propio is None or objetivo is None:
            continue
        filas.append({'que': etiqueta, 'unidad': unidad, 'tema': propio,
                      'perfil': objetivo, 'diferencia': propio - objetivo})
    return filas


CSV_BANDAS = ['banda', 'desde', 'hasta', 'desvio_db', 'estado', 'ancho_db']
CSV_EQ = ['banda', 'tipo', 'freq_hz', 'ganancia_db', 'q', 'recortada']
