"""Nucleo de analisis: decodifica audio, busca huellas de encoding lossy y dicta veredicto.

Compartido por la CLI (spectro.py) y la GUI (spek_gui.py). Usa solo numpy para
la STFT, asi el ejecutable empaquetado no arrastra scipy.

Se apoya en dos senales independientes:

  1. Corte pasa-bajos - donde termina el espectro. Es la senal principal y la
     que detecta el caso comun.
  2. Colapso del estereo - arriba de cierta frecuencia el canal lateral
     desaparece porque el codec uso estereo por intensidad, guardando una sola
     senal mas un panorama. Un master real conserva diferencia entre canales en
     todo el rango. Dispara poco, pero cubre un punto ciego del corte: HE-AAC
     con SBR reconstruye agudos sinteticos y puede mostrar espectro completo.

Se probo tambien detectar huecos espectrales (bandas puestas en cero por el
codec). Medido contra el mismo master en FLAC, MP3 320 y MP3 128, no separa
FLAC de 320 (1.75% contra 1.92% de celdas agujereadas) porque a ese bitrate el
encoder no pone bandas en cero: degrada por cuantizacion. Se descarto.
"""
import numpy as np
import soundfile as sf
from matplotlib.colors import LinearSegmentedColormap

import spectro_dupes
import spectro_loudness
import spectro_master

AUDIO_EXTS = {'.flac', '.wav', '.aiff', '.aif', '.ogg', '.opus', '.mp3', '.m4a'}

# Paleta estilo Spek: negro -> azul -> verde -> amarillo -> rojo -> blanco
SPEK_CMAP = LinearSegmentedColormap.from_list('spek', [
    (0.00, '#000000'), (0.15, '#1a1050'), (0.30, '#2060a0'),
    (0.45, '#20a070'), (0.60, '#a0d020'), (0.75, '#f0c020'),
    (0.90, '#e04020'), (1.00, '#ffffff'),
])

# Colores del grafico, alineados al sistema de diseno de la ticketera. Van
# aca y no importados de ui_theme para que este modulo no arrastre tkinter:
# lo cargan tambien los procesos del analisis en paralelo y la CLI.
CHART_TEXT = '#EAF5FF'      # $text-main
CHART_DIM = '#7AA8C0'       # $text-muted
CHART_BORDER = '#0A2C45'    # $border ya mezclado
CHART_BG = '#061625'        # $bg-card

DB_FLOOR = -120.0   # piso de la escala de color
NOISE_DB = -90.0    # umbral para considerar que hay senal real en una banda
LOUD_WARN_LUFS = -9.0       # mas fuerte que esto y el streaming lo baja bastante
SIDE_DEAD_DB = -40.0        # canal lateral tan debil que es estereo por intensidad
SIDE_ALIVE_DB = -25.0       # material con estereo real en graves y medios
MIN_DEAD_FRACTION = 0.80    # proporcion de bandas muertas para dar el aviso
MIN_DEAD_SPAN_HZ = 3000.0   # ancho minimo de la zona muerta, para no marcar un borde
SIDE_CONTENT_DB = 45.0      # una banda a mas de esto bajo el pico no se juzga

# Los mismos semanticos del sistema de diseno de la ticketera ($green, $yellow,
# $red, $color-a), para que la tabla, el grafico y el descargador hablen el
# mismo idioma de color
VERDICT_COLORS = {
    'LOSSLESS': '#22D09A',
    'SOSPECHOSO': '#F5B800',
    'TRANSCODE': '#F16C6C',
    'DUDOSO': '#5B7CF5',
}


def load_audio(path):
    """Devuelve (muestras 2D (n, canales), samplerate, subtipo) sin mezclar canales.

    En float32 y no float64: alcanza de sobra para un piso de -120 dB y parte
    al medio la memoria, que en un tema de once minutos son cientos de MB por
    cada arreglo intermedio.
    """
    data, rate = sf.read(str(path), always_2d=True, dtype='float32')
    return data, rate, sf.info(str(path)).subtype


def stft_mag(samples, rate, fft_size=4096, overlap=0.5):
    """STFT con ventana Hann. Devuelve magnitudes lineales, freqs y tiempos."""
    hop = int(fft_size * (1 - overlap))
    samples = np.ascontiguousarray(samples)
    if len(samples) < fft_size:
        samples = np.pad(samples, (0, fft_size - len(samples)))

    n_frames = 1 + (len(samples) - fft_size) // hop
    # Vista sin copia sobre las ventanas solapadas
    frames = np.lib.stride_tricks.as_strided(
        samples,
        shape=(n_frames, fft_size),
        strides=(samples.strides[0] * hop, samples.strides[0]),
    )

    window = np.hanning(fft_size).astype(samples.dtype, copy=False)
    mag = np.empty((fft_size // 2 + 1, n_frames), dtype=samples.dtype)
    # Por bloques para no materializar todas las ventanas a la vez
    for start in range(0, n_frames, 512):
        chunk = frames[start:start + 512] * window
        mag[:, start:start + chunk.shape[0]] = np.abs(np.fft.rfft(chunk, axis=1)).T

    freqs = np.fft.rfftfreq(fft_size, 1 / rate)
    times = np.arange(n_frames) * hop / rate
    return mag, freqs, times


def to_db(mag, ref):
    """Pasa magnitudes lineales a dB relativos a una referencia comun."""
    return 20 * np.log10(np.maximum(mag / max(ref, 1e-12), 1e-12))


def to_db_inplace(mag, ref):
    """Igual que to_db pero reescribiendo el arreglo recibido.

    Un espectrograma de un tema largo pesa mas de cien megabytes; tener a la
    vez la version lineal y la version en dB duplicaba ese costo sin necesidad,
    porque la lineal no se vuelve a usar.
    """
    np.divide(mag, max(ref, 1e-12), out=mag)
    np.maximum(mag, 1e-12, out=mag)
    np.log10(mag, out=mag)
    mag *= 20
    return mag


def band_profile(mag, percentile=95):
    """Percentil temporal de cada banda, en magnitud lineal."""
    return np.percentile(mag, percentile, axis=1)


def compute_spectrogram(samples, rate, fft_size=4096, overlap=0.5):
    """Espectrograma en dB normalizado a su propio pico."""
    mag, freqs, times = stft_mag(samples, rate, fft_size, overlap)
    return to_db(mag, mag.max()), freqs, times


# --- senal 1: corte pasa-bajos ----------------------------------------------

def cutoff_from_profile(profile_db, freqs):
    """Frecuencia mas alta del perfil que sostiene energia sobre el ruido."""
    active = np.where(profile_db > NOISE_DB)[0]
    if len(active) == 0:
        return 0.0
    return float(freqs[active[-1]])


def detect_cutoff(db, freqs, percentile=95):
    """Frecuencia mas alta que sostiene energia sobre el piso de ruido.

    Usa un percentil alto en el eje del tiempo para que un pasaje silencioso
    no arrastre el resultado hacia abajo.

    El paso a dB es monotono, asi que el percentil se puede tomar en lineal y
    convertir despues solo el perfil: son dos mil valores en vez del
    espectrograma entero. Eso permite calcular el corte antes de materializar
    la version en dB.
    """
    return cutoff_from_profile(np.percentile(db, percentile, axis=1), freqs)


# --- senal 2: colapso del estereo -------------------------------------------

def detect_stereo_collapse(mid_mag, side_mag, freqs, cutoff_hz):
    """Frecuencia desde la cual el canal lateral se apaga, o None.

    Compara la potencia media de lado contra medio banda por banda. Si el
    material es casi mono no hay nada que juzgar y devuelve None.
    """
    # El acumulador va en float64 aunque los datos sean float32: son catorce
    # mil cuadros de valores muy chicos y la suma se degrada
    mid_p = np.mean(mid_mag ** 2, axis=1, dtype=np.float64)
    side_p = np.mean(side_mag ** 2, axis=1, dtype=np.float64)
    ratio = 10 * np.log10(np.maximum(side_p, 1e-30) / np.maximum(mid_p, 1e-30))

    # Hace falta estereo real en graves y medios para que la prueba signifique algo
    lo = int(np.searchsorted(freqs, 200))
    hi = int(np.searchsorted(freqs, 2000))
    if hi <= lo or np.median(ratio[lo:hi]) < SIDE_ALIVE_DB:
        return None

    top = int(np.searchsorted(freqs, cutoff_hz)) if cutoff_hz > 0 else len(freqs)
    start = int(np.searchsorted(freqs, 3000))
    span = int(np.ceil(MIN_DEAD_SPAN_HZ / (freqs[1] - freqs[0])))
    if top - start < span:
        return None

    # No se exige que TODA la zona este muerta: en un archivo de 16 bits el ruido
    # de cuantizacion levanta el ratio cerca de Nyquist, donde la musica ya se
    # apago. Basta con que la gran mayoria de las bandas lo esten.
    dead = (ratio[start:top] < SIDE_DEAD_DB).astype(float)
    counts = np.arange(len(dead), 0, -1)
    frac_dead = np.cumsum(dead[::-1])[::-1] / counts

    # El criterio global por si solo marca el borde demasiado abajo: unas pocas
    # bandas vivas al principio se diluyen en el promedio. Se exige ademas que
    # la zona inmediatamente superior este muerta, y asi el numero informado
    # cae donde realmente empieza el colapso.
    local = int(np.ceil(1000.0 / (freqs[1] - freqs[0])))
    csum = np.concatenate([[0.0], np.cumsum(dead)])
    local_frac = (csum[local:] - csum[:-local]) / local
    n = len(local_frac)

    ok = np.where(
        (frac_dead[:n] >= MIN_DEAD_FRACTION)
        & (local_frac >= MIN_DEAD_FRACTION)
        & (counts[:n] >= span)
    )[0]
    if len(ok) == 0:
        return None
    return float(freqs[start + ok[0]])


def bands_side_over_mid(mid_mag, side_mag, freqs, min_octavas=1 / 3):
    """Tramos donde el canal lateral supera al central, en (desde, hasta) Hz.

    Es el riesgo concreto al sumar a mono: en esas bandas la diferencia entre
    canales pesa mas que lo que tienen en comun, asi que al sumarlos se
    cancela justamente lo que mas suena ahi.

    Solo se miran bandas con contenido real. En las zonas vacias la relacion
    entre lateral y central es el cociente de dos ruidos y puede dar cualquier
    cosa, algo que ya nos habia arruinado un veredicto antes.
    """
    if side_mag is None:
        return []
    mid_p = np.mean(mid_mag ** 2, axis=1, dtype=np.float64)
    side_p = np.mean(side_mag ** 2, axis=1, dtype=np.float64)
    total = mid_p + side_p

    # Una banda cuenta si no esta muy por debajo del pico del tema
    piso = total.max() * 10 ** (-SIDE_CONTENT_DB / 10)
    excede = (side_p > mid_p) & (total > piso) & (freqs >= 20)
    if not excede.any():
        return []

    # Tramos contiguos, quedandose con los suficientemente anchos para que no
    # sea una banda suelta. El ancho se mide en octavas y no en hertz: con un
    # minimo fijo en hertz, doscientos son casi nada en agudos pero mas que
    # toda la zona del sub, que mide unos ciento treinta. Asi se perdia el
    # caso mas grave, que es justo el del grave fuera de fase.
    razon = 2 ** min_octavas
    bordes = np.diff(np.concatenate([[0], excede.view(np.int8), [0]]))
    inicios = np.where(bordes == 1)[0]
    finales = np.where(bordes == -1)[0]
    return [(float(freqs[i]), float(freqs[f - 1]))
            for i, f in zip(inicios, finales)
            if freqs[i] > 0 and freqs[f - 1] / freqs[i] >= razon]


def describe_side_over_mid(tramos):
    """Texto corto de los tramos donde el lateral manda, o cadena vacia."""
    if not tramos:
        return ''
    def etiqueta(hz):
        return f'{hz/1000:.1f} kHz' if hz >= 1000 else f'{hz:.0f} Hz'
    partes = [f'{etiqueta(a)}-{etiqueta(b)}' for a, b in tramos[:3]]
    extra = '...' if len(tramos) > 3 else ''
    return f'lateral supera al central en {", ".join(partes)}{extra}'


# --- veredicto ---------------------------------------------------------------

def classify_cutoff(cutoff_hz, rate):
    """Traduce solo la frecuencia de corte a un veredicto preliminar."""
    khz = cutoff_hz / 1000
    nyquist_khz = (rate / 2) / 1000

    if khz >= nyquist_khz * 0.95:
        return 'LOSSLESS', f'espectro completo hasta {khz:.1f} kHz (Nyquist {nyquist_khz:.1f})'
    if khz >= 20.5:
        return 'LOSSLESS', f'corte en {khz:.1f} kHz, por encima del rango audible'
    if khz >= 19.0:
        return 'SOSPECHOSO', f'corte en {khz:.1f} kHz, compatible con MP3 320 o AAC alto'
    # Umbrales medidos: LAME filtra en ~16 kHz a 128, ~18 a 192, ~19 a 256
    if khz >= 17.5:
        return 'TRANSCODE', f'corte en {khz:.1f} kHz, tipico de MP3 192-256'
    if khz >= 15.0:
        return 'TRANSCODE', f'corte en {khz:.1f} kHz, tipico de MP3 128-192'
    if khz >= 10.0:
        return 'TRANSCODE', f'corte en {khz:.1f} kHz, tipico de MP3 128 o menos'
    return 'DUDOSO', f'corte en {khz:.1f} kHz, material muy filtrado o grabacion antigua'


def combine(cutoff_verdict, cutoff_detail, stereo_hz):
    """Cruza las dos senales en un veredicto unico."""
    signals = []
    if stereo_hz is not None:
        signals.append(f'canal lateral muerto desde {stereo_hz/1000:.1f} kHz (estereo por intensidad)')

    verdict, detail = cutoff_verdict, cutoff_detail

    if stereo_hz is not None and verdict in ('LOSSLESS', 'SOSPECHOSO'):
        # El estereo por intensidad no aparece en una cadena lossless, asi que
        # pesa mas que un corte de aspecto limpio. Se conserva la descripcion
        # del corte: leerla junto al aviso muestra por que el veredicto cambio
        # aunque el espectro se vea entero.
        verdict = 'TRANSCODE'

    return verdict, detail, signals


def analyze(path):
    """Corre el analisis completo. Devuelve un dict con todo lo que hace falta."""
    # El orden de esta funcion esta puesto para que nunca convivan mas arreglos
    # grandes de los necesarios: cada uno se libera apenas deja de hacer falta.
    # En una maquina con poca RAM eso es la diferencia entre analizar y no.
    data, rate, subtype = load_audio(path)
    mid = data.mean(axis=1)
    duration = len(mid) / rate
    channels = data.shape[1]

    # Primero todo lo que necesita las muestras crudas, para poder soltarlas
    raw = spectro_master.raw_metrics(path, data, rate, subtype, mid)
    side = (data[:, 0] - data[:, 1]) / 2 if channels == 2 else None
    del data

    mid_mag, freqs, times = stft_mag(mid, rate)
    del mid
    side_mag = stft_mag(side, rate)[0] if side is not None else None
    del side

    # El corte sale del perfil por banda, sin materializar el espectrograma en
    # dB todavia: asi las magnitudes lineales siguen disponibles para el resto
    ref = float(mid_mag.max())
    cutoff = cutoff_from_profile(to_db(band_profile(mid_mag), ref), freqs)

    stereo_hz = None
    if side_mag is not None:
        stereo_hz = detect_stereo_collapse(mid_mag, side_mag, freqs, cutoff)

    verdict, detail, signals = combine(*classify_cutoff(cutoff, rate), stereo_hz)
    master = spectro_master.finish(raw, mid_mag, side_mag, freqs, rate, cutoff)

    # Tramos donde el lateral pesa mas que el central: lo que se cancela al
    # sumar a mono. Complementa la perdida de graves, que es un solo numero
    # para una sola banda.
    lateral_manda = bands_side_over_mid(mid_mag, side_mag, freqs)
    master['side_over_mid'] = lateral_manda
    aviso = describe_side_over_mid(lateral_manda)
    if aviso:
        master['warnings'].append(aviso)

    # La sonoridad sale del mismo espectrograma, filtrando por banda en vez de
    # recorrer las muestras con la recursion que pide la norma
    hop_sec = float(times[1] - times[0]) if len(times) > 1 else 0.0
    master['lufs'] = spectro_loudness.integrated_lufs(
        mid_mag, side_mag, freqs, rate, hop_sec) if hop_sec else None
    master['streaming_gain_db'] = spectro_loudness.streaming_gain(master['lufs'])
    if master['lufs'] is not None and master['lufs'] > LOUD_WARN_LUFS:
        master['warnings'].append(
            f"{master['lufs']:.1f} LUFS, el streaming lo va a bajar "
            f"{abs(master['streaming_gain_db']):.1f} dB")

    # Conversion en el mismo arreglo: la version lineal ya no se usa y tener
    # las dos a la vez duplicaba el arreglo mas grande del analisis
    db = to_db_inplace(mid_mag, ref)
    side_db = to_db_inplace(side_mag, ref) if side_mag is not None else None
    huella = spectro_dupes.fingerprint(db, freqs)

    # Los detectores ya usaron la resolucion completa; lo que queda es para
    # dibujar, y dibujar nunca necesita mas columnas que pixeles. Un tema de
    # once minutos pasa de 437 MB a 49 MB, lo que vuelve viable tener varios
    # en cache sin arriesgar quedarse sin memoria.
    # El lateral se reduce primero, con los tiempos originales: los dos
    # arreglos tienen la misma forma, asi que les toca el mismo agrupamiento
    if side_db is not None:
        side_db = downsample_time(side_db, times)[0]
    db, times = downsample_time(db, times)

    return {
        'db': db, 'side_db': side_db, 'freqs': freqs, 'times': times,
        'cutoff': cutoff, 'rate': rate, 'subtype': subtype,
        'verdict': verdict, 'detail': detail, 'signals': signals,
        'stereo_hz': stereo_hz,
        'master': master,
        'fingerprint': huella,
        'channels': channels,
        'duration': duration,
    }


def summary(result, path):
    """Version liviana del resultado, sin los arreglos del espectrograma.

    Analizar una carpeta grande y quedarse con los espectrogramas completos
    seria decenas de megabytes por tema. La tabla solo necesita esto.
    """
    m = result['master']
    return {
        'path': path,
        'name': path.name,
        'verdict': result['verdict'],
        'detail': result['detail'],
        'signals': result['signals'],
        'cutoff': result['cutoff'],
        'rate': result['rate'],
        'subtype': result['subtype'],
        'channels': result['channels'],
        'duration': result['duration'],
        'dr': m['dr'],
        'lufs': m['lufs'],
        'streaming_gain_db': m['streaming_gain_db'],
        'fingerprint': result['fingerprint'],
        'true_peak_db': m['true_peak_db'],
        'clip_runs': m['clip_runs'],
        'real_bits': m['real_bits'],
        'declared_bits': m['declared_bits'],
        'warnings': m['warnings'],
    }


CSV_COLUMNS = [
    ('name', 'archivo'), ('verdict', 'veredicto'), ('detail', 'detalle'),
    ('cutoff', 'corte_hz'), ('rate', 'samplerate'), ('subtype', 'formato'),
    ('channels', 'canales'), ('duration', 'duracion_s'), ('dr', 'dr'),
    ('lufs', 'lufs'), ('streaming_gain_db', 'ganancia_streaming_db'),
    ('true_peak_db', 'pico_real_dbtp'), ('clip_runs', 'mesetas_clipeo'),
    ('real_bits', 'bits_reales'), ('declared_bits', 'bits_declarados'),
]


def downsample_time(db, times, max_cols=1600):
    """Agrupa columnas de tiempo tomando el maximo de cada bloque.

    Mantiene visible cualquier transitorio y baja el costo de dibujado de
    decenas de millones de celdas a menos de cuatro millones.
    """
    n = db.shape[1]
    if n <= max_cols:
        return db, times
    block = int(np.ceil(n / max_cols))
    usable = (n // block) * block
    trimmed = db[:, :usable].reshape(db.shape[0], -1, block)
    return trimmed.max(axis=2), times[:usable:block]


TILT_DB_OCT = 3.0       # pendiente que compensa la caida natural del espectro
TILT_PIVOT_HZ = 1000.0  # frecuencia que queda sin tocar al aplicar la pendiente
LOG_BANDS = 260         # bandas del espectrograma en vista logaritmica
LOG_LO_HZ = 20.0


def to_log_bands(db, freqs, n_bands=LOG_BANDS, lo_hz=LOG_LO_HZ):
    """Reagrupa el espectrograma en bandas espaciadas logaritmicamente.

    Un eje logaritmico no se puede dibujar con imshow, que supone paso
    constante. Reagrupar primero y dibujar despues sale mucho mas barato que
    pasar a pcolormesh sobre las dos mil bandas originales.

    La resolucion del grave sigue siendo la de la transformada de 4096: abajo
    de cien hertz hay siete bandas y estirarlas no inventa detalle. Para mirar
    el grave en serio esta la pestana de produccion, que usa ventanas ocho
    veces mas grandes.
    """
    bordes = np.geomspace(max(lo_hz, freqs[1]), freqs[-1], n_bands + 1)
    indices = np.searchsorted(freqs, bordes)
    # Cada banda se queda con al menos una de la transformada
    indices[1:] = np.maximum(indices[1:], indices[:-1] + 1)
    indices = np.clip(indices, 0, len(freqs) - 1)

    salida = np.empty((n_bands, db.shape[1]), dtype=db.dtype)
    for i in range(n_bands):
        lo, hi = indices[i], max(indices[i + 1], indices[i] + 1)
        salida[i] = db[lo:hi].max(axis=0)
    return salida, bordes


def tilt(db, freqs, db_por_octava=TILT_DB_OCT):
    """Inclina el espectrograma para compensar su caida natural.

    La musica pierde del orden de tres decibeles por octava, asi que en un eje
    logaritmico el grave se va al tope de la paleta y los agudos al piso, y en
    el grave no se distingue el bombo del bajo porque los dos estan en blanco.
    Sumando la misma pendiente al reves, las bandas quedan en un rango parecido
    y se ve la estructura.

    No cambia el analisis: es solo como se pinta. Baja el grave unos diecisiete
    decibeles y sube los agudos unos trece, tomando mil hertz como eje.
    """
    correccion = db_por_octava * np.log2(np.maximum(freqs, 1.0) / TILT_PIVOT_HZ)
    # Se deja tal cual, sin volver a referir al pico: la pendiente baja el pico
    # original, que esta en el grave, asi que renormalizar sumaria trece
    # decibeles a todo y saturaria mas en vez de menos
    return db + correccion[:, None]


def draw(ax, result, title, channel='mid', yscale='linear'):
    """Dibuja el espectrograma sobre un Axes de matplotlib ya existente.

    channel 'side' muestra el canal lateral (L-R), donde el colapso de estereo
    se ve como una pared. Comparte la referencia en dB con el central, asi que
    las dos vistas son comparables sin recalibrar la vista.
    """
    source = result['side_db'] if channel == 'side' and result.get('side_db') is not None else result['db']
    db, times = downsample_time(source, result['times'])
    freqs, cutoff = result['freqs'], result['cutoff']

    ax.clear()
    ax.set_facecolor('#000000')
    # En vista logaritmica se inclina el espectro: sin eso el grave ocupa un
    # tercio del grafico todo en blanco y no se lee nada ahi
    if yscale == 'log':
        db = tilt(db, freqs)
    tope = 0.0
    if yscale == 'log':
        banda_db, bordes = to_log_bands(db, freqs)
        # pcolormesh con celdas planas quiere bordes, no centros, en los dos
        # ejes: uno mas que columnas y que filas
        paso = (times[1] - times[0]) if len(times) > 1 else 1.0
        bordes_t = np.concatenate([times - paso / 2, [times[-1] + paso / 2]])
        ax.pcolormesh(bordes_t, bordes / 1000, banda_db, cmap=SPEK_CMAP,
                      vmin=DB_FLOOR, vmax=tope, shading='flat', rasterized=True)
        ax.set_yscale('log')
        ax.set_ylim(bordes[0] / 1000, bordes[-1] / 1000)
        ax.set_yticks([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20])
        ax.set_yticklabels(['0.02', '0.05', '0.1', '0.2', '0.5', '1',
                            '2', '5', '10', '20'])
    else:
        ax.imshow(
            db, cmap=SPEK_CMAP, vmin=DB_FLOOR, vmax=tope, origin='lower', aspect='auto',
            extent=[times[0], times[-1], freqs[0] / 1000, freqs[-1] / 1000],
            interpolation='nearest',
        )

    if cutoff > 0 and channel == 'mid':
        ax.axhline(cutoff / 1000, color='#ffffff', linestyle='--', linewidth=1.0, alpha=0.65)
        ax.text(
            times[-1] * 0.995, cutoff / 1000 + 0.35, f'{cutoff/1000:.1f} kHz',
            color='#ffffff', fontsize=9, ha='right', va='bottom',
        )

    # Donde muere el canal lateral, si es que muere
    if result.get('stereo_hz'):
        # Trazo oscuro debajo del rojo: sobre la zona amarilla del espectro el
        # punteado claro se perdia. El borde oscuro lo separa de cualquier fondo
        ax.axhline(result['stereo_hz'] / 1000, color='#1a0d0d',
                   linestyle='-', linewidth=2.6, alpha=0.55)
        ax.axhline(result['stereo_hz'] / 1000, color='#ff5a5a',
                   linestyle=':', linewidth=1.5, alpha=1.0)
        # Con recuadro propio: en la vista central la etiqueta cae sobre la
        # parte amarilla del espectro y en rojo pelado no se leia
        ax.text(
            times[-1] * 0.005, result['stereo_hz'] / 1000 + 0.35, 'lateral muerto',
            color='#ffffff', fontsize=8, ha='left', va='bottom',
            bbox=dict(boxstyle='round,pad=0.28', facecolor='#1a0d0d',
                      edgecolor='#f87171', linewidth=0.8, alpha=0.92),
        )

    ax.set_xlabel('Tiempo (s)', color=CHART_DIM, fontsize=9)
    ax.set_ylabel('Frecuencia (kHz)', color=CHART_DIM, fontsize=9)
    ax.tick_params(colors=CHART_DIM, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(CHART_BORDER)

    # El titulo sube para dejar lugar al veredicto y, si lo hay, al renglon de
    # senales que va debajo de el
    ax.set_title(title, color=CHART_TEXT, fontsize=11,
                 pad=38 if result.get('signals') else 22, loc='left')
    ax.text(
        0.0, 1.055 if result.get('signals') else 1.015,
        f"{result['verdict']} - {result['detail']}", transform=ax.transAxes,
        color=VERDICT_COLORS[result['verdict']], fontsize=9, ha='left', va='bottom',
    )
    if result.get('signals'):
        ax.text(
            0.0, 1.015, ' | '.join(result['signals']), transform=ax.transAxes,
            color=CHART_DIM, fontsize=8, ha='left', va='bottom',
        )
    return tope
