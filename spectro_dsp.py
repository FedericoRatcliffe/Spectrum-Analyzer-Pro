"""Diseno y aplicacion de filtros FIR, en numpy.

Existen en scipy como `firwin2` y `fftconvolve`. Estan reimplementados aca por
una razon concreta: scipy pesa mas de cien megabytes empaquetado, y sacarlo del
ejecutable fue lo que lo llevo de unos 150 MB a 42. Traerlo de vuelta por dos
funciones no compensa.

Las dos estan verificadas contra scipy en los tests, que si lo tienen
disponible en el entorno de desarrollo.
"""
import numpy as np


def firwin2(numtaps, freq, gain, fs=2.0):
    """FIR de fase lineal a partir de una respuesta en frecuencia deseada.

    Muestreo en frecuencia: se arma la respuesta sobre una grilla densa, se le
    agrega el retardo lineal que corresponde al largo del filtro, se vuelve al
    tiempo y se le aplica una ventana para acotar los rizos de truncar.

    `freq` va de 0 a fs/2, empezando en 0 y terminando en fs/2. `numtaps`
    impar deja el retardo en un numero entero de muestras, que es lo que
    permite compensarlo sin interpolar.
    """
    if numtaps < 3 or numtaps % 2 == 0:
        raise ValueError('numtaps tiene que ser impar y al menos 3')
    freq = np.asarray(freq, dtype=np.float64)
    gain = np.asarray(gain, dtype=np.float64)
    nyq = fs / 2.0
    if freq[0] != 0 or not np.isclose(freq[-1], nyq):
        raise ValueError('freq tiene que ir de 0 a fs/2')

    # Grilla densa: cuanto mas fina, menos se aparta el filtro de lo pedido
    nfreqs = 1 + 2 ** int(np.ceil(np.log2(numtaps)))
    x = np.linspace(0.0, nyq, nfreqs)
    fx = np.interp(x, freq, gain)

    # Retardo lineal de (numtaps-1)/2 muestras: es lo que vuelve al filtro de
    # fase lineal, sin corrimiento de fase entre bandas
    shift = np.exp(-(numtaps - 1) / 2 * 1j * np.pi * x / nyq)
    respuesta = np.fft.irfft(fx * shift)

    return respuesta[:numtaps] * np.hamming(numtaps)


def fftconvolve(signal, kernel, block=None):
    """Convolucion por bloques con solapamiento y suma.

    Transformar la senal entera de una obligaria a una transformada del tamano
    del tema: en un archivo largo son cientos de megabytes en complejos. Por
    bloques el costo es el mismo y la memoria queda acotada.

    Devuelve la convolucion completa, de largo len(signal) + len(kernel) - 1.
    """
    signal = np.asarray(signal)
    kernel = np.asarray(kernel, dtype=np.float64)
    n, m = len(signal), len(kernel)
    # La salida sigue el tipo de la entrada: convertir un tema entero a doble
    # precision son cientos de megabytes, y para audio float32 ya da mas rango
    # dinamico del que entra en 24 bits
    tipo = np.float64 if signal.dtype == np.float64 else np.float32
    if n == 0 or m == 0:
        return np.zeros(0, dtype=signal.dtype)

    if block is None:
        # Bloque comodo: la transformada queda en una potencia de dos y cada
        # una procesa bastante mas muestras que el largo del filtro
        tamano_fft = 1 << max(13, int(np.ceil(np.log2(m * 4))))
    else:
        tamano_fft = 1 << int(np.ceil(np.log2(block + m - 1)))
    paso = tamano_fft - m + 1
    if paso <= 0:
        raise ValueError('el bloque tiene que superar el largo del filtro')

    kernel_fft = np.fft.rfft(kernel, tamano_fft)
    salida = np.zeros(n + m - 1, dtype=tipo)
    for inicio in range(0, n, paso):
        trozo = signal[inicio:inicio + paso]
        producto = np.fft.irfft(np.fft.rfft(trozo, tamano_fft) * kernel_fft,
                                tamano_fft).astype(tipo, copy=False)
        fin = min(inicio + len(producto), len(salida))
        salida[inicio:fin] += producto[:fin - inicio]
    return salida


def filtrar(signal, kernel):
    """Aplica el filtro y devuelve una senal del mismo largo, ya alineada.

    Un FIR de fase lineal retrasa todo por igual media ventana; descartar ese
    retardo es lo que deja la salida en fase con la entrada. Sin esto el tema
    procesado queda corrido unos milisegundos respecto del original y comparar
    antes y despues no tiene sentido.
    """
    retardo = (len(kernel) - 1) // 2
    completa = fftconvolve(signal, kernel)
    return completa[retardo:retardo + len(signal)]
