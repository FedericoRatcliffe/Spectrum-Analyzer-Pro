"""Deteccion de temas repetidos dentro de una biblioteca.

El problema real no es encontrar archivos identicos, que se resuelve con un
hash: es encontrar el mismo tema guardado dos veces con distinto formato,
distinto bitrate o distinto nombre. Ahi los bytes no coinciden en nada pero el
audio es el mismo.

La huella se arma desde el espectrograma que el analisis ya calculo: se reduce
a una grilla chica de bandas por tramos de tiempo y se normaliza. Dos copias
del mismo master dan grillas casi iguales aunque una venga de un MP3, porque la
forma del espectro sobrevive a la compresion. Dos temas distintos no, ni
cuando son del mismo artista.
"""
import numpy as np

BANDS = 16              # bandas logaritmicas de la huella
SLICES = 32             # tramos de tiempo, en fraccion de la duracion
LO_HZ = 80.0            # debajo de esto hay poca forma distintiva
HI_HZ = 12000.0         # arriba, lo que un MP3 recorta y arruinaria la huella
MATCH_THRESHOLD = 0.93  # correlacion a partir de la cual se consideran el mismo
DURATION_TOLERANCE = 0.04   # 4% de diferencia de duracion como maximo


def fingerprint(db, freqs, n_bands=BANDS, n_slices=SLICES):
    """Huella compacta del espectrograma: n_bands x n_slices, normalizada.

    Se queda entre 80 Hz y 12 kHz a proposito. Arriba de eso es justo donde un
    MP3 recorta, asi que incluirlo haria que el mismo tema en FLAC y en MP3
    dieran huellas distintas, que es lo contrario de lo que se busca.
    """
    lo = int(np.searchsorted(freqs, LO_HZ))
    hi = int(np.searchsorted(freqs, min(HI_HZ, freqs[-1])))
    if hi - lo < n_bands or db.shape[1] < n_slices:
        return None

    edges = np.geomspace(lo + 1, hi, n_bands + 1).astype(int)
    edges = np.unique(np.clip(edges, lo + 1, hi))
    if len(edges) < 2:
        return None

    # Tramos por fraccion de la duracion, no por segundos: asi dos copias del
    # mismo tema se alinean aunque una tenga unos cuadros de mas
    cortes = np.linspace(0, db.shape[1], n_slices + 1).astype(int)

    grid = np.empty((len(edges) - 1, n_slices))
    for b in range(len(edges) - 1):
        banda = db[edges[b]:edges[b + 1]]
        for s in range(n_slices):
            tramo = banda[:, cortes[s]:cortes[s + 1]]
            grid[b, s] = tramo.mean() if tramo.size else -120.0

    # Centrada y de norma uno: queda inmune al volumen y a la ganancia general
    flat = grid.ravel() - grid.mean()
    norm = np.linalg.norm(flat)
    if norm == 0:
        return None
    return (flat / norm).astype(np.float32)


def similarity(a, b):
    """Correlacion entre dos huellas, de -1 a 1."""
    if a is None or b is None or len(a) != len(b):
        return 0.0
    return float(np.dot(a, b))


def find_duplicates(entries, threshold=MATCH_THRESHOLD):
    """Agrupa los que son el mismo tema.

    `entries` son resumenes con 'fingerprint', 'duration' y 'name'. Devuelve
    una lista de grupos, cada uno con dos o mas indices.

    La duracion se usa como filtro previo: dos temas que no duran casi lo mismo
    no pueden ser el mismo, y descartarlos antes evita comparar de mas.
    """
    n = len(entries)
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            di, dj = entries[i].get('duration'), entries[j].get('duration')
            if not di or not dj:
                continue
            if abs(di - dj) / max(di, dj) > DURATION_TOLERANCE:
                continue
            if similarity(entries[i].get('fingerprint'),
                          entries[j].get('fingerprint')) >= threshold:
                ri, rj = raiz(i), raiz(j)
                if ri != rj:
                    padre[ri] = rj

    grupos = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(i)
    return [sorted(g) for g in grupos.values() if len(g) > 1]


def describe(groups, entries):
    """Texto legible de lo encontrado, para la barra de estado o la consola."""
    if not groups:
        return 'sin repetidos'
    total = sum(len(g) - 1 for g in groups)
    return f'{len(groups)} grupo(s) de repetidos, {total} archivo(s) de sobra'
