"""Metricas de calidad del master, independientes de si el archivo es lossless.

Responden preguntas que el espectrograma no contesta: si el master esta
clipeado, si esta aplastado por la guerra del volumen, si un archivo declarado
de 24 bits en realidad guarda 16, y si un sample rate alto es real o es un 44.1
estirado. Los dos ultimos son fraudes mas comunes que el transcode y no dejan
ninguna huella visible en el espectro.
"""
import numpy as np

CLIP_THRESHOLD = 0.9995     # a partir de aca una muestra cuenta como tocando el techo
CLIP_RUN = 3                # muestras seguidas al tope para hablar de clipeo real
TRUE_PEAK_WARN = 1.0         # dBTP a partir del cual el aviso es accionable
DR_BLOCK_SEC = 3.0          # ventana del medidor de rango dinamico
DR_TOP_FRACTION = 0.20      # porcion mas fuerte que define el nivel de referencia
BASS_HI_HZ = 150.0          # techo de la banda de graves que suele sumarse a mono
BASS_LOSS_WARN = -3.0       # dB perdidos al sumar a mono que ya son audibles
CORRELATION_WARN = -0.10    # correlacion negativa: canales en oposicion
DC_WARN_DB = -60.0          # continua por encima de esto merece aviso

SUBTYPE_BITS = {
    'PCM_S8': 8, 'PCM_U8': 8, 'PCM_16': 16, 'PCM_24': 24, 'PCM_32': 32,
    'FLOAT': 32, 'DOUBLE': 64,
}


def _db(x):
    return 20 * np.log10(max(float(x), 1e-12))


def true_peak_db(mono, rate, oversample=4):
    """Pico entre muestras, estimado sobremuestreando solo donde importa.

    Un archivo puede no tener ninguna muestra al tope y aun asi superar 0 dBFS
    al reconstruirse en el conversor. Sobremuestrear el tema entero seria caro,
    asi que solo se procesan los bloques que ya estan cerca del pico global.
    """
    block = 65536
    peak = np.abs(mono).max()
    if peak <= 0:
        return -np.inf

    best = peak
    for start in range(0, len(mono), block // 2):
        chunk = mono[start:start + block]
        if len(chunk) < 64 or np.abs(chunk).max() < peak * 0.7:
            continue  # lejos del pico: no puede ganar
        spec = np.fft.rfft(chunk)
        up = np.fft.irfft(spec, len(chunk) * oversample) * oversample
        # Cortar el bloque crea un salto en sus extremos y la reconstruccion
        # repica ahi (Gibbs), lo que inflaba el pico mas de 1 dB. Se descarta
        # el cuarto de cada punta; el solape del 50% cubre lo descartado.
        quarter = len(up) // 4
        best = max(best, np.abs(up[quarter:-quarter]).max())
    return _db(best)


def clipping(data, chunk=1 << 22):
    """(muestras al tope, corridas de muestras al tope).

    Una muestra suelta en el techo puede ser casualidad; tres o mas seguidas
    son una meseta, que es la firma de un master pasado de nivel.

    Se recorre por bloques: comparar el tema entero de una creaba copias
    temporales de su mismo tamano, y en un tema largo eran cientos de MB justo
    cuando las muestras crudas todavia estan en memoria.
    """
    total = 0
    runs = 0
    for ch in range(data.shape[1]):
        carry = 0   # largo de la corrida que venia del bloque anterior
        for start in range(0, len(data), chunk):
            seg = data[start:start + chunk, ch]
            flags = (seg >= CLIP_THRESHOLD) | (seg <= -CLIP_THRESHOLD)
            total += int(flags.sum())
            if not flags.any():
                if carry >= CLIP_RUN:
                    runs += 1
                carry = 0
                continue

            edges = np.diff(np.concatenate([[0], flags.view(np.int8), [0]]))
            starts = np.where(edges == 1)[0]
            ends = np.where(edges == -1)[0]
            lengths = ends - starts

            # La primera corrida puede continuar la que cerraba el bloque previo
            if len(starts) and starts[0] == 0:
                lengths = lengths.copy()
                lengths[0] += carry
            elif carry >= CLIP_RUN:
                runs += 1

            # La ultima puede seguir en el bloque siguiente: se arrastra
            if len(ends) and ends[-1] == len(seg):
                carry = int(lengths[-1])
                lengths = lengths[:-1]
            else:
                carry = 0
            runs += int((lengths >= CLIP_RUN).sum())
        if carry >= CLIP_RUN:
            runs += 1
    return total, runs


def dynamic_range(data, rate):
    """Rango dinamico al estilo del medidor DR, en dB.

    Compara el pico contra el nivel eficaz de los bloques mas fuertes. Un
    master moderno aplastado da 5-7; uno con aire da 12 o mas.
    """
    block = int(DR_BLOCK_SEC * rate)
    if len(data) < block * 2:
        return None

    n_blocks = len(data) // block
    values = []
    for ch in range(data.shape[1]):
        # Bloque por bloque en vez de reformar el canal entero: cada operacion
        # trabaja sobre tres segundos de audio y no sobre el tema completo
        rms_list = np.empty(n_blocks)
        peak_list = np.empty(n_blocks)
        for i in range(n_blocks):
            seg = data[i * block:(i + 1) * block, ch]
            rms_list[i] = np.sqrt(np.mean(seg ** 2, dtype=np.float64))
            peak_list[i] = np.abs(seg).max()

        rms = np.sort(rms_list[rms_list > 0])
        if len(rms) < 2:
            continue
        top = rms[-max(1, int(len(rms) * DR_TOP_FRACTION)):]
        # El segundo pico, no el primero: evita que un transitorio aislado mande
        peaks = np.sort(peak_list)
        peak2 = peaks[-2] if len(peaks) > 1 else peaks[-1]
        values.append(_db(peak2) - _db(np.sqrt((top ** 2).mean())))
    return float(np.mean(values)) if values else None


def effective_bits(path, subtype):
    """(bits realmente usados, bits declarados).

    Se lee como entero de 32 bits: libsndfile alinea a la izquierda, asi que
    los ceros al final delatan cuanta resolucion hay de verdad. Un archivo de
    24 bits que arrastra 16 ceros es un 16 bits rellenado.
    """
    import soundfile as sf

    declared = SUBTYPE_BITS.get(subtype)
    if subtype in ('FLOAT', 'DOUBLE') or declared is None:
        return None, declared

    # Por bloques: leer el archivo entero como enteros sumaba otros 218 MB al
    # pico de memoria de un tema largo, encima de todo lo que ya esta cargado
    acumulado = 0
    for block in sf.blocks(str(path), blocksize=1 << 20, dtype='int32', always_2d=True):
        nz = block[block != 0]
        if len(nz):
            # a int64 antes del valor absoluto: abs(-2**31) no entra en int32
            acumulado |= int(np.bitwise_or.reduce(np.abs(nz.astype(np.int64))))
    if acumulado == 0:
        return None, declared

    # Bit menos significativo activo en todo el archivo
    trailing = (acumulado & -acumulado).bit_length() - 1
    return 32 - trailing, declared


def mono_bass_loss(mid_mag, side_mag, freqs, lo_hz=20.0, hi_hz=BASS_HI_HZ):
    """Cuanta energia de graves se pierde al sumar a mono, en dB (<= 0).

    La suma a mono es exactamente el canal central, asi que lo que vive en el
    lateral se cancela. Muchos sistemas de club suman el bajo a mono: un tema
    con los graves fuera de fase pierde ahi el cuerpo que tenia en cabina.

    0 dB es perfecto, -3 dB significa que la mitad de los graves estaba en el
    lateral y desaparece.
    """
    lo = int(np.searchsorted(freqs, lo_hz))
    hi = int(np.searchsorted(freqs, hi_hz))
    if hi <= lo:
        return None
    mid_p = float(np.sum(mid_mag[lo:hi].astype(np.float64) ** 2))
    side_p = float(np.sum(side_mag[lo:hi].astype(np.float64) ** 2))
    if mid_p + side_p <= 0:
        return None
    # Con cancelacion perfecta el central queda en cero y el logaritmo daria
    # -inf, que ademas se imprimiria asi en la interfaz. Se acota en -99 dB,
    # que ya significa "no queda nada".
    return max(10 * np.log10(max(mid_p, 1e-30) / (mid_p + side_p)), -99.0)


def channel_correlation(data):
    """Correlacion entre canales, de -1 a 1, o None si no es estereo.

    Cerca de 1 es material casi mono, cerca de 0 estereo amplio, y negativo
    quiere decir canales en oposicion de fase.
    """
    if data.shape[1] != 2:
        return None
    n = len(data)
    if n == 0:
        return None

    # Por bloques y acumulando en float64: convertir los canales enteros a
    # float64 de una copiaria cientos de MB, y acumular en float32 sobre
    # decenas de millones de muestras pierde precision
    sum_l = sum_r = sll = srr = slr = 0.0
    for start in range(0, n, 1 << 21):
        left = data[start:start + (1 << 21), 0].astype(np.float64)
        right = data[start:start + (1 << 21), 1].astype(np.float64)
        sum_l += float(left.sum())
        sum_r += float(right.sum())
        sll += float(np.dot(left, left))
        srr += float(np.dot(right, right))
        slr += float(np.dot(left, right))

    sll -= sum_l * sum_l / n
    srr -= sum_r * sum_r / n
    slr -= sum_l * sum_r / n
    if sll <= 0 or srr <= 0:
        return None
    return slr / np.sqrt(sll * srr)


def dc_offset_db(data):
    """Nivel de la componente continua, en dBFS. Delata una grabacion torcida."""
    return _db(np.abs(data.mean(axis=0, dtype=np.float64)).max())


def fake_samplerate(rate, cutoff_hz):
    """Sample rate declarado alto pero sin contenido que lo justifique.

    Devuelve el rate de origen probable, o None. Un 96 kHz real lleva energia
    bastante por encima de 22 kHz; si se corta justo ahi, es un 44.1 estirado.
    """
    if rate <= 48000 or cutoff_hz <= 0:
        return None
    for base in (44100, 48000):
        if rate > base * 1.5 and cutoff_hz < (base / 2) * 1.02:
            return base
    return None


def raw_metrics(path, data, rate, subtype, mono):
    """Todo lo que se calcula sobre las muestras crudas.

    Se separa de `finish` para que quien llama pueda soltar el arreglo de
    muestras enseguida: en un tema largo son cientos de megabytes que no
    conviene tener vivos mientras se calculan los espectrogramas.
    """
    rms = float(np.sqrt(np.mean(mono ** 2, dtype=np.float64)))
    return {
        'sample_peak_db': _db(np.abs(data).max()),
        'true_peak_db': true_peak_db(mono, rate),
        'clipping': clipping(data),
        'dr': dynamic_range(data, rate),
        'bits': effective_bits(path, subtype),
        'crest_db': _db(np.abs(mono).max()) - _db(rms) if rms > 0 else None,
        'correlation': channel_correlation(data),
        'dc_db': dc_offset_db(data),
    }


def finish(raw, mid_mag, side_mag, freqs, rate, cutoff_hz):
    """Completa las metricas con lo que sale de los espectrogramas."""
    sample_peak = raw['sample_peak_db']
    tp = raw['true_peak_db']
    clipped, runs = raw['clipping']
    dr = raw['dr']
    real_bits, declared_bits = raw['bits']
    crest = raw['crest_db']
    correlation = raw['correlation']
    dc = raw['dc_db']
    fake_rate = fake_samplerate(rate, cutoff_hz)

    bass_loss = None
    if mid_mag is not None and side_mag is not None:
        bass_loss = mono_bass_loss(mid_mag, side_mag, freqs)

    warnings = []
    if runs > 0:
        warnings.append(f'{runs} mesetas de clipeo ({clipped} muestras al tope)')
    # Casi todo master moderno pasa de 0 dBTP, asi que avisar ahi seria ruido.
    # Recien arriba de +1 el riesgo de distorsion al reproducir es real.
    if tp > TRUE_PEAK_WARN:
        warnings.append(f'pico real {tp:+.1f} dBTP, puede distorsionar al reproducir')
    if dr is not None and dr < 7:
        warnings.append(f'rango dinamico DR{dr:.0f}, master muy aplastado')
    if real_bits and declared_bits and real_bits < declared_bits:
        warnings.append(f'declara {declared_bits} bits pero usa {real_bits}')
    if fake_rate:
        warnings.append(f'{rate} Hz sin contenido propio, parece {fake_rate} Hz estirado')
    if bass_loss is not None and bass_loss < BASS_LOSS_WARN:
        warnings.append(f'graves fuera de fase: pierde {abs(bass_loss):.1f} dB al sumar a mono')
    if correlation is not None and correlation < CORRELATION_WARN:
        warnings.append(f'correlacion entre canales {correlation:+.2f}, hay oposicion de fase')
    if dc > DC_WARN_DB:
        warnings.append(f'componente continua en {dc:.0f} dBFS')

    return {
        'sample_peak_db': sample_peak, 'true_peak_db': tp,
        'clipped_samples': clipped, 'clip_runs': runs,
        'dr': dr, 'crest_db': crest,
        'real_bits': real_bits, 'declared_bits': declared_bits,
        'fake_samplerate': fake_rate,
        'bass_loss_db': bass_loss, 'correlation': correlation, 'dc_db': dc,
        'warnings': warnings,
    }
