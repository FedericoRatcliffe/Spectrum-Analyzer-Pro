"""Vistas de referencia para producir: balance tonal y ancho estereo por banda.

No dictan veredictos. La pregunta que contestan no es "esto sirve" sino "en que
se diferencia mi tema del que tomo como referencia", que es una comparacion que
interpreta quien mezcla.

Dos decisiones que hacen que esto sea util y no un adorno:

Resolucion. El espectrograma usa ventanas de 4096 muestras porque necesita ver
transitorios, y eso da bandas de 10.8 Hz: entre 20 y 100 Hz entran apenas siete.
En un eje logaritmico esa zona ocupa tanto ancho como 100-500 o 500-2500, asi
que se veria escalonada justo donde se toman las decisiones de grave. Aca el
tiempo no importa, solo el promedio, asi que se usan ventanas de 32768 que dan
1.35 Hz y setenta y cuatro bandas en esa misma zona.

Normalizacion. Las curvas se alinean por sonoridad y no por pico. Alinear por
pico compara volumen; alinear por sonoridad compara balance, que es lo que se
quiere mirar.
"""
import numpy as np
import soundfile as sf

import spectro_loudness
import spectro_master

FFT_SIZE = 32768        # 1.35 Hz por banda a 44.1 kHz
F_LO = 20.0
F_HI = 20000.0
POINTS = 420            # puntos de la curva, espaciados logaritmicamente
SMOOTH_FRACTION = 6     # ventana de suavizado, en fracciones de octava
MONO_HI_HZ = 120.0      # debajo de esto conviene que el estereo sea angosto
MONO_LO_HZ = 25.0       # debajo de esto casi ningun tema tiene contenido
UMBRAL_CANDIDATO = 0.7  # -3 dB del pico: mas abajo no puede contener el pico real
RELEVANT_DB = 35.0      # una banda a mas de esto bajo el pico grave no cuenta


def average_spectrum(path, fft_size=FFT_SIZE):
    """Potencia media por banda de los canales central y lateral.

    Lee por bloques solapados en vez de cargar el tema entero: solo se acumula
    el espectro, que son unos pocos miles de valores, asi que un tema de once
    minutos cuesta lo mismo que uno de tres.
    """
    info = sf.info(str(path))
    rate = info.samplerate
    window = np.hanning(fft_size).astype(np.float32)

    mid_acc = np.zeros(fft_size // 2 + 1)
    side_acc = np.zeros(fft_size // 2 + 1)
    cuadros = 0

    # De paso se acumula la potencia con filtro K de cada bloque. Sale gratis
    # porque la transformada ya esta hecha, y con eso se arma la curva de
    # sonoridad sin una segunda pasada sobre el archivo.
    freqs_fft = np.fft.rfftfreq(fft_size, 1 / rate)
    peso_k = spectro_loudness.k_weight_power(freqs_fft, rate)
    espejo = np.full(len(freqs_fft), 2.0)
    espejo[0] = 1.0
    espejo[-1] = 1.0
    factor_k = espejo * peso_k
    st_power = []

    # El pico real se mide al vuelo, bloque por bloque, y solo se guarda el
    # maximo. Guardar los bloques candidatos para medirlos al final obligaba a
    # ponerles un tope, y con tope el resultado erraba hasta medio decibel
    # contra el que informa el analisis: un numero distinto para la misma cosa
    # en la misma herramienta.
    #
    # Solo se miden los bloques que estan a menos de 3 dB del pico muestreado
    # mas alto visto hasta el momento: mas abajo no pueden contener el pico
    # real, porque el pico entre muestras supera al muestreado por poco.
    pico_real = -np.inf
    pico_max = 0.0

    for block in sf.blocks(str(path), blocksize=fft_size, overlap=fft_size // 2,
                           dtype='float32', always_2d=True, fill_value=0.0):
        if len(block) < fft_size:
            break
        mid = block.mean(axis=1) * window
        mid_pot = np.abs(np.fft.rfft(mid)) ** 2
        mid_acc += mid_pot
        bloque_k = float(np.sum(mid_pot * factor_k))

        if block.shape[1] == 2:
            side = (block[:, 0] - block[:, 1]) / 2 * window
            side_pot = np.abs(np.fft.rfft(side)) ** 2
            side_acc += side_pot
            bloque_k = (bloque_k + float(np.sum(side_pot * factor_k))) * 2

        st_power.append(bloque_k / (fft_size ** 2) / 0.375)

        # Sobre la mezcla mono, que es lo que se mide: mirar el pico en estereo
        # dejaba afuera el bloque que realmente contenia el pico mono
        mono = block.mean(axis=1)
        pico_bloque = float(np.abs(mono).max())
        if pico_bloque >= pico_max * UMBRAL_CANDIDATO:
            pico_max = max(pico_max, pico_bloque)
            pico_real = max(pico_real, spectro_master.true_peak_db(mono, rate))

        cuadros += 1

    if cuadros == 0:
        return None

    # Escala a algo comparable con dBFS. Sin esto los valores salen de la
    # transformada sin normalizar y el eje muestra setenta u ochenta dB, que no
    # significan nada: hay que dividir por el tamano de la ventana al cuadrado
    # y compensar la ventana de Hann, cuyo valor cuadratico medio es 3/8.
    escala = 1.0 / (fft_size ** 2 * 0.375 / 2)
    mid_acc *= escala
    side_acc *= escala

    freqs = np.fft.rfftfreq(fft_size, 1 / rate)
    tiene_side = side_acc.any()
    return {
        'freqs': freqs,
        'mid': mid_acc / cuadros,
        'side': (side_acc / cuadros) if tiene_side else None,
        'rate': rate,
        'st_power': np.array(st_power),
        'hop_sec': (fft_size / 2) / rate,
        'true_peak_db': float(pico_real) if np.isfinite(pico_real) else None,
    }


def log_points(f_lo=F_LO, f_hi=F_HI, points=POINTS):
    """Frecuencias de la curva, espaciadas parejo en el eje logaritmico."""
    return np.geomspace(f_lo, f_hi, points)


def smooth(freqs, power, salida=None, fraction=SMOOTH_FRACTION):
    """Promedia la potencia en una ventana de 1/fraction de octava.

    Sin esto la curva es ilegible: el promedio crudo de una transformada tiene
    tanto detalle que no se distingue la forma, que es justamente lo unico que
    se quiere leer.
    """
    if salida is None:
        salida = log_points()
    mitad = 2 ** (1 / (2 * fraction))
    lo = np.searchsorted(freqs, salida / mitad, side='left')
    hi = np.searchsorted(freqs, salida * mitad, side='right')
    # Por debajo de unos cien hertz la ventana de una fraccion de octava es mas
    # angosta que una banda de la transformada; se toma al menos una
    hi = np.maximum(hi, lo + 1)

    acumulado = np.concatenate([[0.0], np.cumsum(power)])
    return (acumulado[hi] - acumulado[lo]) / (hi - lo)


def to_db(power, floor=1e-20):
    return 10 * np.log10(np.maximum(power, floor))


def tonal_balance(spec, offset_db=0.0):
    """Curvas de central y lateral en dB, suavizadas y listas para dibujar.

    `offset_db` desplaza toda la curva; se usa para alinear por sonoridad dos
    temas de volumen distinto.
    """
    if spec is None:
        return None
    salida = log_points()
    curvas = {'freqs': salida,
              'mid': to_db(smooth(spec['freqs'], spec['mid'], salida)) + offset_db}
    curvas['side'] = (to_db(smooth(spec['freqs'], spec['side'], salida)) + offset_db
                      if spec['side'] is not None else None)
    return curvas


def stereo_width(spec):
    """Relacion lateral contra central por banda, en dB.

    Cero significa que los dos canales aportan lo mismo; muy negativo, que esa
    banda es practicamente mono. En los graves conviene que sea bien negativo:
    un sub ancho se cancela en cualquier sistema que sume el bajo a mono.
    """
    if spec is None or spec['side'] is None:
        return None
    salida = log_points()
    mid = smooth(spec['freqs'], spec['mid'], salida)
    side = smooth(spec['freqs'], spec['side'], salida)
    # Se devuelve tambien el nivel total: sin el no hay forma de saber si una
    # banda tiene contenido, y el cociente entre dos ruidos no significa nada.
    # Total y no central, porque un tema con el grave fuera de fase lo tiene
    # entero en el lateral, y mirando solo el central pareceria estar vacio
    # justo en el caso que interesa detectar.
    return {'freqs': salida,
            'width': to_db(side) - to_db(mid),
            'total_db': to_db(mid + side)}


def integrated_from_spec(spec):
    """Sonoridad integrada calculada desde el propio espectro, o None.

    Existe para no depender de que el archivo este en la tabla: una referencia
    se carga desde cualquier carpeta y nunca paso por el analisis, y sin su
    sonoridad las curvas no se pueden alinear.

    Los bloques aca duran 0.37 s en vez de los 0.4 s de la norma, porque salen
    del mismo recorrido que el espectro promedio. Para alinear dos curvas la
    diferencia es irrelevante.
    """
    if spec is None or 'st_power' not in spec or len(spec['st_power']) == 0:
        return None
    bloques = spec['st_power']
    nivel = spectro_loudness.OFFSET_DB + 10 * np.log10(np.maximum(bloques, 1e-30))

    arriba = bloques[nivel > spectro_loudness.ABSOLUTE_GATE_LUFS]
    if len(arriba) == 0:
        return None
    relativo = (spectro_loudness.OFFSET_DB + 10 * np.log10(arriba.mean())
                + spectro_loudness.RELATIVE_GATE_LU)
    nivel_arriba = spectro_loudness.OFFSET_DB + 10 * np.log10(np.maximum(arriba, 1e-30))
    quedan = arriba[nivel_arriba > relativo]
    if len(quedan) == 0:
        quedan = arriba
    return float(spectro_loudness.OFFSET_DB + 10 * np.log10(quedan.mean()))


def short_term_loudness(spec, offset_db=0.0, window_sec=spectro_loudness.SHORT_TERM_SEC):
    """Curva de sonoridad de corto plazo: (tiempos, LUFS) o None.

    Usa la potencia que ya se acumulo al recorrer el archivo. El valor
    integrado resume el tema en un numero; esta curva muestra como respira el
    arreglo, que es lo que se compara contra una referencia.

    `offset_db` alinea dos temas de volumen distinto, igual que en el balance.
    """
    if spec is None or 'st_power' not in spec or len(spec['st_power']) < 2:
        return None

    ventana = max(1, int(round(window_sec / spec['hop_sec'])))
    potencia = spec['st_power']
    if len(potencia) < ventana:
        return None

    acumulado = np.concatenate([[0.0], np.cumsum(potencia)])
    promedio = (acumulado[ventana:] - acumulado[:-ventana]) / ventana
    tiempos = (np.arange(len(promedio)) + ventana / 2) * spec['hop_sec']
    lufs = spectro_loudness.OFFSET_DB + 10 * np.log10(np.maximum(promedio, 1e-30)) + offset_db

    # El silencio da valores irrisorios que aplastarian el eje
    visible = lufs > (spectro_loudness.ABSOLUTE_GATE_LUFS + offset_db)
    if not visible.any():
        return None
    return tiempos[visible], lufs[visible]


def bands_over_zero(width, min_octavas=1 / 3):
    """Tramos de la curva de ancho donde el lateral supera al central.

    Sale de la misma curva que se dibuja, no del espectrograma: asi lo que
    avisa el texto es exactamente lo que se ve cruzar el cero en el grafico.
    """
    if width is None:
        return []
    freqs = width['freqs']
    piso = width['total_db'].max() - RELEVANT_DB
    excede = (width['width'] > 0) & (width['total_db'] > piso)
    if not excede.any():
        return []

    razon = 2 ** min_octavas
    bordes = np.diff(np.concatenate([[0], excede.view(np.int8), [0]]))
    inicios = np.where(bordes == 1)[0]
    finales = np.where(bordes == -1)[0]
    return [(float(freqs[i]), float(freqs[f - 1]))
            for i, f in zip(inicios, finales)
            if freqs[i] > 0 and freqs[f - 1] / freqs[i] >= razon]


def describe_over_zero(tramos):
    """Texto del aviso de compatibilidad mono, o cadena vacia."""
    if not tramos:
        return ''
    def etiqueta(hz):
        return f'{hz/1000:.1f} kHz' if hz >= 1000 else f'{hz:.0f} Hz'
    partes = ', '.join(f'{etiqueta(a)}-{etiqueta(b)}' for a, b in tramos[:2])
    extra = '...' if len(tramos) > 2 else ''
    return f'lateral supera al central en {partes}{extra}'


def mono_verdict(width, limite_hz=MONO_HI_HZ, umbral_db=-12.0):
    """Texto corto sobre si el grave esta suficientemente centrado.

    Solo mira bandas con contenido real. Abajo de unos veinticinco hertz casi
    ningun tema tiene energia, y ahi la relacion entre lateral y central es el
    cociente de dos ruidos: puede dar cualquier numero y arruinar el veredicto.
    """
    if width is None:
        return 'archivo mono'
    freqs = width['freqs']
    en_rango = (freqs >= MONO_LO_HZ) & (freqs <= limite_hz)
    if not en_rango.any():
        return ''

    # Referencia: la banda mas fuerte de todo el grave, sumando los dos canales
    grave = width['total_db'][freqs <= 200]
    piso = (grave.max() - RELEVANT_DB) if len(grave) else -np.inf
    con_contenido = en_rango & (width['total_db'] > piso)
    if not con_contenido.any():
        return 'sin contenido grave que evaluar'

    peor = float(width['width'][con_contenido].max())
    if peor <= umbral_db:
        return f'sub centrado (lateral {peor:.0f} dB bajo el central)'
    if peor <= -6.0:
        return f'sub algo ancho (lateral a {peor:.0f} dB)'
    return f'sub muy ancho (lateral a {peor:.0f} dB): riesgo al sumar a mono'
