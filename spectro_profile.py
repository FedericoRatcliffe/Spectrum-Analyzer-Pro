"""Perfil objetivo: el balance tonal tipico de un conjunto de referencias.

Una sola referencia dice poco. Un tema puede tener el grave corrido, un agudo
particular o una mezcla rara, y copiarlo lleva ese defecto al propio trabajo.
Con varios temas del mismo estilo lo que queda es la forma que comparten, y la
dispersion entre ellos define cuanto margen hay antes de que un desvio importe.

De ahi las dos cosas que guarda: la mediana por frecuencia, que es la forma a
la que apuntar, y un rango de tolerancia entre los percentiles 10 y 90, que
dice donde deja de ser una diferencia de estilo y empieza a ser un problema.

Un perfil de un solo archivo no tiene dispersion que medir, asi que en ese caso
la tolerancia es un margen fijo. Sirve igual para comparar, pero conviene saber
que ese margen es arbitrario y no salio de los datos.
"""
import json
from datetime import date
from pathlib import Path

import numpy as np

import spectro_reference as ref

PERFILES_DIR = Path('perfiles')
TOLERANCIA_BAJA = 10      # percentil inferior de la franja
TOLERANCIA_ALTA = 90      # percentil superior
MARGEN_FIJO_DB = 2.0      # ancho de la franja cuando hay menos de tres archivos
MIN_PARA_PERCENTILES = 3


def _franja(curvas):
    """Mediana y bordes de tolerancia de un conjunto de curvas.

    Con tres o mas se usan percentiles, que reflejan la dispersion real. Con
    menos no hay dispersion que medir y se abre un margen fijo: es una decision
    arbitraria y por eso queda anotada en el perfil.
    """
    apiladas = np.vstack(curvas)
    mediana = np.median(apiladas, axis=0)
    if len(curvas) >= MIN_PARA_PERCENTILES:
        bajo = np.percentile(apiladas, TOLERANCIA_BAJA, axis=0)
        alto = np.percentile(apiladas, TOLERANCIA_ALTA, axis=0)
        origen = f'percentiles {TOLERANCIA_BAJA}-{TOLERANCIA_ALTA}'
    else:
        bajo = mediana - MARGEN_FIJO_DB
        alto = mediana + MARGEN_FIJO_DB
        origen = f'margen fijo de {MARGEN_FIJO_DB:.0f} dB'
    return {'mediana': mediana, 'bajo': bajo, 'alto': alto, 'origen': origen}


def desde_espectros(espectros, nombre, archivos):
    """Arma el perfil a partir de espectros ya calculados.

    Cada curva se normaliza por la sonoridad de su propio tema antes de
    promediar. Sin eso el perfil terminaria describiendo que tan fuerte estaba
    masterizado cada archivo en vez de su balance.
    """
    curvas_mid, curvas_side, sonoridades, picos = [], [], [], []

    for spec in espectros:
        if spec is None:
            continue
        lufs = ref.integrated_from_spec(spec)
        offset = -lufs if lufs is not None else 0.0
        curvas = ref.tonal_balance(spec, offset)
        if curvas is None:
            continue
        curvas_mid.append(curvas['mid'])
        if curvas['side'] is not None:
            curvas_side.append(curvas['side'])
        if lufs is not None:
            sonoridades.append(lufs)
        if spec.get('true_peak_db') is not None:
            picos.append(spec['true_peak_db'])

    if not curvas_mid:
        return None

    return {
        'nombre': nombre,
        'archivos': [str(a) for a in archivos],
        'creado': date.today().isoformat(),
        'n': len(curvas_mid),
        'freqs': ref.log_points(),
        'mid': _franja(curvas_mid),
        'side': _franja(curvas_side) if curvas_side else None,
        'lufs': float(np.mean(sonoridades)) if sonoridades else None,
        'true_peak_db': float(np.mean(picos)) if picos else None,
    }


def construir(paths, nombre, progreso=None):
    """Calcula el espectro de cada archivo y arma el perfil.

    `progreso` recibe (hechos, total, nombre_actual) para que la ventana pueda
    mostrar avance: son varios segundos por tema.
    """
    paths = [Path(p) for p in paths]
    espectros = []
    for i, path in enumerate(paths):
        if progreso:
            progreso(i, len(paths), path.name)
        try:
            espectros.append(ref.average_spectrum(path))
        except Exception:  # pylint: disable=broad-except
            espectros.append(None)
    if progreso:
        progreso(len(paths), len(paths), '')
    return desde_espectros(espectros, nombre, paths)


def una_referencia(spec, path):
    """Perfil de un solo archivo, para que cargar una referencia siga andando.

    La pestana dibuja siempre contra un perfil; tratar la referencia suelta
    como un perfil de uno evita tener dos caminos que mantener.
    """
    return desde_espectros([spec], Path(path).stem, [path])


# --- guardado ----------------------------------------------------------------

def _a_json(perfil):
    """Convierte los arreglos a listas para que json pueda escribirlos."""
    crudo = dict(perfil)
    crudo['freqs'] = np.asarray(perfil['freqs']).tolist()
    for canal in ('mid', 'side'):
        if crudo.get(canal):
            crudo[canal] = {k: (np.asarray(v).tolist() if isinstance(v, np.ndarray) else v)
                            for k, v in perfil[canal].items()}
    return crudo


def _desde_json(crudo):
    perfil = dict(crudo)
    perfil['freqs'] = np.asarray(crudo['freqs'])
    for canal in ('mid', 'side'):
        if crudo.get(canal):
            perfil[canal] = {k: (np.asarray(v) if isinstance(v, list) else v)
                             for k, v in crudo[canal].items()}
    return perfil


def _nombre_archivo(nombre):
    limpio = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in nombre).strip()
    return f'{limpio or "perfil"}.json'


def guardar(perfil, carpeta=PERFILES_DIR):
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / _nombre_archivo(perfil['nombre'])
    destino.write_text(json.dumps(_a_json(perfil), indent=2, ensure_ascii=False),
                       encoding='utf-8')
    return destino


def cargar(path):
    return _desde_json(json.loads(Path(path).read_text(encoding='utf-8')))


def listar(carpeta=PERFILES_DIR):
    """(nombre, ruta) de los perfiles guardados, ordenados por nombre."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    salida = []
    for archivo in sorted(carpeta.glob('*.json')):
        try:
            nombre = json.loads(archivo.read_text(encoding='utf-8')).get('nombre')
        except (json.JSONDecodeError, OSError):
            continue
        salida.append((nombre or archivo.stem, archivo))
    return salida


def describir(perfil):
    """Linea corta para la interfaz."""
    if not perfil:
        return 'sin perfil'
    partes = [f"{perfil['nombre']} ({perfil['n']} tema" + ('s' if perfil['n'] != 1 else '') + ')']
    if perfil.get('lufs') is not None:
        partes.append(f"{perfil['lufs']:.1f} LUFS")
    if perfil.get('true_peak_db') is not None:
        partes.append(f"pico {perfil['true_peak_db']:+.1f} dBTP")
    return ' | '.join(partes)
