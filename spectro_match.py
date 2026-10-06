"""Acercar un tema a su perfil objetivo: EQ de fase lineal, sonoridad y limite.

Lo que hace es una correccion, no una mezcla. Igualar la curva de un tema a la
de un perfil lo deja midiendo parecido, y eso no es lo mismo que sonar mejor:
si el problema esta en como conviven los elementos, moverlos a todos juntos con
un EQ no lo resuelve. Por eso la cantidad arranca en la mitad y la correccion
esta acotada, y por eso el archivo original nunca se toca.

La cadena, en orden:

  1. Diferencia contra el perfil, por separado para central y lateral.
  2. Acotada y multiplicada por la cantidad elegida.
  3. Filtros FIR de fase lineal, que corrigen la amplitud sin mover la fase
     entre bandas. Un filtro de fase minima desalinea los transitorios.
  4. Opcionalmente, el lateral se corta por debajo del sub para que los graves
     queden centrados.
  5. Ganancia hasta la sonoridad objetivo.
  6. Limite de pico real, con la verificacion al final.
"""
import numpy as np
import soundfile as sf

import spectro_balance
import spectro_dsp
import spectro_loudness
import spectro_master
import spectro_reference as ref

MAX_CORRECCION_DB = 6.0   # tope de la curva de correccion, antes de la cantidad
TAPS = 8191               # largo del FIR: mas taps, mas resolucion en el grave
SUB_MONO_HZ = 120.0
TECHO_DBTP = -1.0
LOOKAHEAD_MS = 2.0
RELEASE_MS = 60.0
OVERSAMPLE = 4


def curva_correccion(curvas, perfil, canal, amount=0.5,
                     max_db=MAX_CORRECCION_DB):
    """Ganancia en dB por frecuencia para acercar el tema al perfil.

    Se suaviza a un tercio de octava: a un sexto la curva tiene detalle que no
    corresponde a nada que se pueda corregir, y perseguirlo convierte al filtro
    en un peine.
    """
    dev = spectro_balance.deviation(curvas, perfil, canal)
    if dev is None:
        return None, None
    correccion = spectro_balance.suavizar(-dev['diferencia'], dev['freqs'])
    correccion = np.clip(correccion, -max_db, max_db) * amount
    return dev['freqs'], correccion


def _kernel(freqs, correccion_db, rate, taps=TAPS):
    """FIR de fase lineal que aplica esa curva de ganancia."""
    nyq = rate / 2.0
    # Se extiende a continua y a Nyquist con el valor de los extremos, para que
    # el filtro no invente un corte donde la curva simplemente se termina
    ejes = np.concatenate([[0.0], freqs, [nyq]])
    ganancias = np.concatenate([[correccion_db[0]], correccion_db,
                                [correccion_db[-1]]])
    dentro = ejes <= nyq
    ejes, ganancias = ejes[dentro], ganancias[dentro]
    if ejes[-1] < nyq:
        ejes = np.append(ejes, nyq)
        ganancias = np.append(ganancias, ganancias[-1])
    return spectro_dsp.firwin2(taps, ejes, 10 ** (ganancias / 20), fs=rate)


def _kernel_highpass(corte_hz, rate, taps=TAPS):
    """Pasa-altos de fase lineal, para sacar el grave del canal lateral."""
    nyq = rate / 2.0
    ejes = [0.0, corte_hz * 0.5, corte_hz, corte_hz * 1.5, nyq]
    return spectro_dsp.firwin2(taps, ejes, [0.0, 0.0, 0.5, 1.0, 1.0], fs=rate)


def envolvente_true_peak(x, rate, oversample=OVERSAMPLE, bloque=1 << 16):
    """Pico real de cada muestra, mirando tambien entre muestras.

    Se sobremuestrea por bloques y se toma el maximo de cada grupo, asi queda
    una envolvente al sample rate original que ya incluye lo que pasa entre
    muestras. Sobremuestrear el tema entero de una seria varias veces su
    tamano en memoria.
    """
    salida = np.empty(len(x), dtype=np.float64)
    borde = 64
    for inicio in range(0, len(x), bloque):
        fin = min(inicio + bloque, len(x))
        desde = max(0, inicio - borde)
        hasta = min(len(x), fin + borde)
        trozo = x[desde:hasta].astype(np.float64)
        if len(trozo) < 8:
            salida[inicio:fin] = np.abs(x[inicio:fin])
            continue
        # Interpolacion por ceros en frecuencia: reconstruye la senal continua
        arriba = np.fft.irfft(np.fft.rfft(trozo), len(trozo) * oversample) * oversample
        recorte = arriba[(inicio - desde) * oversample:(fin - desde) * oversample]
        grupos = np.abs(recorte).reshape(-1, oversample)
        salida[inicio:fin] = grupos.max(axis=1)
    return salida


def limitar(data, rate, techo_db=TECHO_DBTP, lookahead_ms=LOOKAHEAD_MS,
            release_ms=RELEASE_MS):
    """Baja la ganancia donde haga falta para no pasar del techo de pico real.

    Mira hacia adelante para empezar a bajar antes del pico y evitar el chasquido
    de una caida abrupta, y suelta despacio para no bombear.

    Al final se vuelve a medir y, si quedo algo por encima, se aplica un ajuste
    fijo: la garantia de no pasarse tiene que ser una garantia, no una
    aproximacion.
    """
    techo = 10 ** (techo_db / 20)
    mono = data.mean(axis=1) if data.ndim > 1 else data
    envolvente = np.maximum(envolvente_true_peak(mono, rate),
                            np.abs(data).max(axis=1) if data.ndim > 1 else np.abs(data))

    necesaria = np.minimum(1.0, techo / np.maximum(envolvente, 1e-12))
    if necesaria.min() >= 1.0:
        return data, 0.0

    # Minimo movil hacia adelante: la ganancia ya tiene que estar baja cuando
    # llega el pico
    adelanto = max(1, int(lookahead_ms * rate / 1000))
    extendida = np.concatenate([necesaria, np.ones(adelanto)])
    ventana = np.lib.stride_tricks.sliding_window_view(extendida, adelanto)
    ganancia = ventana.min(axis=1)[:len(necesaria)]

    # Soltada de un polo: subir de golpe despues de un pico se escucha
    alfa = float(np.exp(-1.0 / (release_ms * rate / 1000)))
    suave = np.empty_like(ganancia)
    actual = 1.0
    for i, g in enumerate(ganancia):
        actual = g if g < actual else alfa * actual + (1 - alfa) * g
        suave[i] = actual

    salida = data * (suave[:, None] if data.ndim > 1 else suave)

    # Verificacion: si el limitador dejo algo arriba, se baja todo lo justo
    final = spectro_master.true_peak_db(
        salida.mean(axis=1) if salida.ndim > 1 else salida, rate)
    ajuste = 0.0
    if final > techo_db:
        ajuste = techo_db - final
        salida = salida * 10 ** (ajuste / 20)
    return salida, ajuste


def procesar(path, perfil, amount=0.5, taps=TAPS, sub_mono=True,
             sub_hz=SUB_MONO_HZ, target_lufs=None, techo_db=TECHO_DBTP,
             progreso=None):
    """Corre la cadena completa y devuelve (audio, rate, informe).

    No escribe nada: quien llama decide si guarda.
    """
    def aviso(paso, texto):
        if progreso:
            progreso(paso, texto)

    aviso(0, 'leyendo el archivo')
    data, rate = sf.read(str(path), always_2d=True, dtype='float32')
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)

    aviso(1, 'midiendo el espectro')
    spec = ref.average_spectrum(path)
    lufs_original = ref.integrated_from_spec(spec)
    curvas = ref.tonal_balance(spec, -lufs_original if lufs_original else 0.0)

    aviso(2, 'disenando los filtros')
    mid = data.mean(axis=1)
    side = (data[:, 0] - data[:, 1]) / 2

    informe = {'lufs_original': lufs_original, 'correcciones': {}}
    for canal, señal in (('mid', mid), ('side', side)):
        freqs, correccion = curva_correccion(curvas, perfil, canal, amount)
        if freqs is None:
            continue
        informe['correcciones'][canal] = (freqs, correccion)
        aviso(3, f'filtrando el canal {"central" if canal == "mid" else "lateral"}')
        filtrada = spectro_dsp.filtrar(señal, _kernel(freqs, correccion, rate, taps))
        if canal == 'mid':
            mid = filtrada
        else:
            side = filtrada

    if sub_mono:
        aviso(4, f'centrando el grave debajo de {sub_hz:.0f} Hz')
        side = spectro_dsp.filtrar(side, _kernel_highpass(sub_hz, rate, taps))

    aviso(5, 'reconstruyendo los canales')
    salida = np.column_stack([mid + side, mid - side]).astype(np.float32)
    del mid, side, data

    aviso(6, 'ajustando la sonoridad')
    objetivo = target_lufs if target_lufs is not None else perfil.get('lufs')
    informe['lufs_objetivo'] = objetivo
    if objetivo is not None:
        medido = _lufs_de(salida, rate)
        informe['lufs_antes_de_ganancia'] = medido
        if medido is not None:
            salida = salida * 10 ** ((objetivo - medido) / 20)

    aviso(7, 'limitando el pico real')
    salida, ajuste = limitar(salida, rate, techo_db)
    informe['ajuste_extra_db'] = ajuste
    informe['true_peak_final'] = spectro_master.true_peak_db(
        salida.mean(axis=1), rate)
    informe['lufs_final'] = _lufs_de(salida, rate)

    aviso(8, 'listo')
    return salida, rate, informe


def _lufs_de(data, rate):
    """Sonoridad integrada de un arreglo en memoria."""
    import spectro_core as core
    mid = data.mean(axis=1)
    mid_mag, freqs, times = core.stft_mag(mid.astype(np.float32), rate)
    side_mag, _, _ = core.stft_mag(
        ((data[:, 0] - data[:, 1]) / 2).astype(np.float32), rate)
    if len(times) < 2:
        return None
    return spectro_loudness.integrated_lufs(mid_mag, side_mag, freqs, rate,
                                            float(times[1] - times[0]))


def destino(path, sufijo='_match'):
    """Ruta de salida. Nunca la del original: el archivo de entrada no se toca."""
    from pathlib import Path
    path = Path(path)
    return path.with_name(f'{path.stem}{sufijo}.wav')


def guardar(data, rate, path):
    sf.write(str(path), data, rate, subtype='PCM_24')
    return path
