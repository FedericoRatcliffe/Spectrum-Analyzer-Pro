"""Analisis de varios archivos en paralelo, limitado por la memoria disponible.

El cuello de botella no es el procesador sino la RAM: cada analisis pica en
unos 600 MB, asi que en una maquina con poca memoria libre conviene un solo
proceso aunque sobren nucleos. Lanzar mas de los que entran no acelera nada;
empuja el sistema a disco y lo vuelve mas lento, o falla por falta de memoria.

Los procesos devuelven solo el resumen, nunca el espectrograma: mandar decenas
de megabytes por la tuberia entre procesos costaria mas de lo que ahorra.
"""
import ctypes
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from ctypes import wintypes
from pathlib import Path

PEAK_PER_WORKER_MB = 650    # pico medido por analisis, con un poco de margen
# Los picos de dos procesos casi nunca caen en el mismo instante: cada uno pasa
# buena parte del tiempo por debajo de su maximo. Cobrar el pico completo a
# cada proceso daba 1 solo en una maquina donde 2 funcionan y rinden 1.76x.
EXTRA_WORKER_FRACTION = 0.60
MAX_WORKERS = 4             # mas alla de esto el disco y la memoria mandan


class _MemoryStatus(ctypes.Structure):
    _fields_ = [('dwLength', wintypes.DWORD), ('dwMemoryLoad', wintypes.DWORD),
                ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]


def available_ram_mb():
    """RAM fisica libre en MB, o None si no se puede consultar."""
    if os.name != 'nt':
        return None
    try:
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if not ctypes.WinDLL('kernel32').GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.ullAvailPhys / 1024 / 1024
    except OSError:
        return None


def choose_workers(n_files):
    """Cuantos procesos lanzar sin pasarse de la memoria libre."""
    if n_files <= 1:
        return 1
    cpu = os.cpu_count() or 1
    free = available_ram_mb()
    if free is None:
        by_memory = 2   # sin dato, algo conservador
    else:
        # El primer proceso se cobra entero; los siguientes, solo su parte
        # probable de solapamiento
        extra = (free - PEAK_PER_WORKER_MB) / (PEAK_PER_WORKER_MB * EXTRA_WORKER_FRACTION)
        by_memory = 1 + max(0, int(extra))
    return max(1, min(by_memory, cpu, MAX_WORKERS, n_files))


def analyze_summary(path):
    """Analiza un archivo y devuelve solo el resumen, apto para mandar entre procesos.

    Tiene que estar a nivel de modulo para que se pueda serializar y ejecutar
    en un proceso hijo.
    """
    import spectro_core as core
    path = Path(path)
    return core.summary(core.analyze(path), path)


def run(paths, on_result, on_error, workers=None):
    """Analiza todo y va avisando por callback a medida que termina cada uno.

    Con un solo proceso corre en el hilo actual: levantar un pool para eso solo
    agregaria demora de arranque.
    """
    paths = list(paths)
    workers = workers or choose_workers(len(paths))

    if workers == 1:
        for path in paths:
            try:
                on_result(analyze_summary(path))
            except Exception as e:  # pylint: disable=broad-except
                on_error(path, str(e))
        return workers

    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(analyze_summary, str(p)): p for p in paths}
        for future in as_completed(pending):
            path = pending[future]
            try:
                on_result(future.result())
            except Exception as e:  # pylint: disable=broad-except
                on_error(path, str(e))
    return workers
