"""Sonoridad integrada en LUFS, segun ITU-R BS.1770-4 (el que usa EBU R128).

Es la medida con la que las plataformas normalizan: Spotify apunta a -14 LUFS,
YouTube a -14, Apple Music a -16. Saber cuanto mide un tema dice cuanto lo van
a bajar al reproducirlo, y comparada con el rango dinamico explica por que un
master aplastado no suena mas fuerte en streaming, solo peor.

Sobre el metodo: la norma filtra en el dominio del tiempo con dos biquads. Aca
el filtrado se aplica sobre el espectrograma que el analisis ya calculo,
multiplicando cada banda por la respuesta del filtro. Es equivalente en regimen
permanente y evita recorrer decenas de millones de muestras con una recursion
que numpy no puede vectorizar. La diferencia con un medidor de referencia queda
en el orden de la decima de dB, de sobra para lo que se usa aca.
"""
import numpy as np

ABSOLUTE_GATE_LUFS = -70.0   # por debajo de esto es silencio y no cuenta
RELATIVE_GATE_LU = -10.0     # respecto del nivel medio, descarta los pasajes flojos
BLOCK_SEC = 0.400            # ventana de la norma
SHORT_TERM_SEC = 3.0         # ventana de la sonoridad de corto plazo, segun R128
OFFSET_DB = -0.691           # calibracion de BS.1770

# Parametros del filtro K, del anexo de la norma
SHELF_F0 = 1681.974450955533
SHELF_GAIN_DB = 3.999843853973347
SHELF_Q = 0.7071752369554196
HIGHPASS_F0 = 38.13547087602444
HIGHPASS_Q = 0.5003270373238773


def _shelf_coeffs(rate):
    """Biquad de estante agudo, con las formulas del cookbook de RBJ."""
    A = 10 ** (SHELF_GAIN_DB / 40)
    w0 = 2 * np.pi * SHELF_F0 / rate
    alpha = np.sin(w0) / (2 * SHELF_Q)
    cos_w0 = np.cos(w0)
    sqrt_A = np.sqrt(A)

    b = np.array([
        A * ((A + 1) + (A - 1) * cos_w0 + 2 * sqrt_A * alpha),
        -2 * A * ((A - 1) + (A + 1) * cos_w0),
        A * ((A + 1) + (A - 1) * cos_w0 - 2 * sqrt_A * alpha),
    ])
    a = np.array([
        (A + 1) - (A - 1) * cos_w0 + 2 * sqrt_A * alpha,
        2 * ((A - 1) - (A + 1) * cos_w0),
        (A + 1) - (A - 1) * cos_w0 - 2 * sqrt_A * alpha,
    ])
    return b / a[0], a / a[0]


def _highpass_coeffs(rate):
    """Biquad pasa-altos que modela la respuesta de la cabeza."""
    w0 = 2 * np.pi * HIGHPASS_F0 / rate
    alpha = np.sin(w0) / (2 * HIGHPASS_Q)
    cos_w0 = np.cos(w0)

    b = np.array([(1 + cos_w0) / 2, -(1 + cos_w0), (1 + cos_w0) / 2])
    a = np.array([1 + alpha, -2 * cos_w0, 1 - alpha])
    return b / a[0], a / a[0]


def k_weight_power(freqs, rate):
    """Ganancia en potencia del filtro K para cada frecuencia.

    Los coeficientes se recalculan para el sample rate del archivo. Usar los de
    48 kHz en un archivo de 44.1 introduce un error chico pero evitable.
    """
    z = np.exp(-2j * np.pi * freqs / rate)
    response = np.ones(len(freqs), dtype=np.complex128)
    for b, a in (_shelf_coeffs(rate), _highpass_coeffs(rate)):
        num = b[0] + b[1] * z + b[2] * z * z
        den = a[0] + a[1] * z + a[2] * z * z
        response *= num / den
    return np.abs(response) ** 2


def frame_power(mid_mag, side_mag, freqs, rate, fft_size=4096):
    """Potencia con filtro K de cada cuadro del espectrograma.

    La suma de canales que pide la norma se arma desde central y lateral:
    con L = central + lateral y R = central - lateral, la suma de potencias de
    los dos canales es el doble de la suma de las potencias de central y
    lateral.
    """
    weight = k_weight_power(freqs, rate)

    # Parseval sobre media transformada: todas las bandas cuentan doble salvo
    # continua y Nyquist, que no tienen espejo
    mirror = np.full(len(freqs), 2.0)
    mirror[0] = 1.0
    if fft_size % 2 == 0:
        mirror[-1] = 1.0

    factor = (mirror * weight)[:, None]
    power = np.sum(mid_mag.astype(np.float64) ** 2 * factor, axis=0)
    if side_mag is not None:
        power = power + np.sum(side_mag.astype(np.float64) ** 2 * factor, axis=0)
        power *= 2      # de central/lateral a izquierda + derecha

    # De la energia de la ventana a potencia media de la senal: dividir por el
    # tamano de la transformada al cuadrado y compensar la ventana de Hann,
    # cuyo valor cuadratico medio es 3/8
    return power / (fft_size ** 2) / 0.375


def integrated_lufs(mid_mag, side_mag, freqs, rate, hop_sec, fft_size=4096):
    """Sonoridad integrada en LUFS, o None si no hay material suficiente.

    Aplica las dos compuertas de la norma: primero descarta el silencio con un
    umbral fijo, despues descarta lo que queda diez unidades por debajo del
    promedio, para que los pasajes flojos no bajen la medicion de un tema que
    en realidad es fuerte.
    """
    power = frame_power(mid_mag, side_mag, freqs, rate, fft_size)
    if len(power) == 0:
        return None

    # Los cuadros del espectrograma duran menos que la ventana de la norma, asi
    # que se agrupan hasta completar los 400 ms
    per_block = max(1, int(round(BLOCK_SEC / hop_sec)))
    n_blocks = len(power) // per_block
    if n_blocks < 1:
        blocks = np.array([power.mean()])
    else:
        blocks = power[:n_blocks * per_block].reshape(n_blocks, per_block).mean(axis=1)

    loudness = OFFSET_DB + 10 * np.log10(np.maximum(blocks, 1e-30))

    above = blocks[loudness > ABSOLUTE_GATE_LUFS]
    if len(above) == 0:
        return None

    relative = OFFSET_DB + 10 * np.log10(above.mean()) + RELATIVE_GATE_LU
    kept = above[OFFSET_DB + 10 * np.log10(np.maximum(above, 1e-30)) > relative]
    if len(kept) == 0:
        kept = above

    return float(OFFSET_DB + 10 * np.log10(kept.mean()))


def short_term(mid_mag, side_mag, freqs, rate, hop_sec, fft_size=4096,
               window_sec=SHORT_TERM_SEC):
    """Curva de sonoridad de corto plazo: (tiempos, LUFS) o None.

    Es la medida que define la norma para seguir la energia a lo largo del
    tema: ventana deslizante de tres segundos, sin ninguna compuerta. Sirve
    para comparar como respira un arreglo contra otro, donde el valor integrado
    no dice nada porque resume el tema entero en un numero.
    """
    power = frame_power(mid_mag, side_mag, freqs, rate, fft_size)
    if len(power) < 2 or hop_sec <= 0:
        return None

    ventana = max(1, int(round(window_sec / hop_sec)))
    if len(power) < ventana:
        return None

    # Media movil por suma acumulada: una ventana de tres segundos sobre miles
    # de cuadros seria un bucle innecesario
    acumulado = np.concatenate([[0.0], np.cumsum(power)])
    promedio = (acumulado[ventana:] - acumulado[:-ventana]) / ventana

    tiempos = (np.arange(len(promedio)) + ventana / 2) * hop_sec
    lufs = OFFSET_DB + 10 * np.log10(np.maximum(promedio, 1e-30))
    # El silencio absoluto daria valores irrisorios que aplastan el eje
    visible = lufs > ABSOLUTE_GATE_LUFS
    if not visible.any():
        return None
    return tiempos[visible], lufs[visible]


def streaming_gain(lufs, target=-14.0):
    """Cuanto va a mover la plataforma el volumen del tema, en dB.

    Negativo quiere decir que lo van a bajar. Spotify y YouTube apuntan a -14
    LUFS; Apple Music a -16.
    """
    if lufs is None:
        return None
    return target - lufs
