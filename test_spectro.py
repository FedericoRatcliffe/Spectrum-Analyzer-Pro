#!/usr/bin/env python3
"""Tests de regresion del analizador.

Uso:
    python test_spectro.py            # solo los rapidos, con senales sinteticas
    python test_spectro.py --golden   # agrega los archivos reales de referencia

Los casos con nombre `test_regresion_*` cubren bugs que realmente ocurrieron.
Cada uno lleva anotado que sintoma tenia el bug, para que quede claro por que
existe la prueba y no se borre por parecer trivial.
"""
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

import spectro_batch
import spectro_core as core
import spectro_dsp as dsp
import spectro_dupes as dupes
import spectro_match
import spectro_balance as bal
import spectro_profile as prof
import spectro_reference as ref
import spectro_loudness as loudness
import spectro_master as master

RATE = 44100


def noise(seconds=8.0, rate=RATE, seed=0):
    """Ruido blanco reproducible."""
    return np.random.default_rng(seed).standard_normal(int(seconds * rate)) * 0.1


def lowpass(signal, cutoff_hz, rate=RATE):
    """Pared vertical en el espectro, para tener un corte de frecuencia exacto."""
    spec = np.fft.rfft(signal)
    spec[np.fft.rfftfreq(len(signal), 1 / rate) > cutoff_hz] = 0
    return np.fft.irfft(spec, len(signal))


def highpass(signal, cutoff_hz, rate=RATE):
    """Complemento del pasa-bajos, para senales de prueba sin contenido grave."""
    return signal - lowpass(signal, cutoff_hz, rate)


def quantize16(signal):
    """Lleva a 16 bits y vuelve, para que aparezca el ruido de cuantizacion."""
    peak = np.abs(signal).max() or 1.0
    scaled = np.round(signal / peak * 32767).astype(np.int16)
    return scaled.astype(np.float64) / 32767 * peak


def temp_path(suffix='.flac'):
    """Ruta temporal con su descriptor ya cerrado.

    mkstemp devuelve un descriptor abierto: olvidarse de cerrarlo deja el
    archivo tomado en Windows y despues no se puede borrar.
    """
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(name)


def write_temp(data, rate=RATE, subtype='PCM_16', suffix='.flac'):
    path = temp_path(suffix)
    sf.write(str(path), data, rate, subtype=subtype)
    return path


# --- deteccion del corte -----------------------------------------------------

class TestCorte(unittest.TestCase):
    def test_encuentra_el_corte_donde_esta(self):
        for objetivo in (10000, 16000, 19000):
            señal = lowpass(noise(), objetivo)
            mag, freqs, _ = core.stft_mag(señal.astype(np.float32), RATE)
            db = core.to_db(mag, mag.max())
            medido = core.detect_cutoff(db, freqs)
            self.assertAlmostEqual(medido, objetivo, delta=300,
                                   msg=f'corte buscado {objetivo}, medido {medido}')

    def test_sin_corte_llega_a_nyquist(self):
        mag, freqs, _ = core.stft_mag(noise().astype(np.float32), RATE)
        db = core.to_db(mag, mag.max())
        self.assertGreater(core.detect_cutoff(db, freqs), 21000)

    def test_perfil_da_lo_mismo_que_el_espectrograma_entero(self):
        # analyze() usa el perfil por banda para ahorrar memoria; tiene que
        # coincidir con calcularlo sobre el espectrograma completo en dB
        mag, freqs, _ = core.stft_mag(lowpass(noise(), 15000).astype(np.float32), RATE)
        ref = float(mag.max())
        por_perfil = core.cutoff_from_profile(core.to_db(core.band_profile(mag), ref), freqs)
        por_entero = core.detect_cutoff(core.to_db(mag, ref), freqs)
        self.assertEqual(por_perfil, por_entero)

    def test_clasificacion_por_bitrate(self):
        casos = [(22050, 'LOSSLESS'), (20200, 'SOSPECHOSO'), (18000, 'TRANSCODE'),
                 (16800, 'TRANSCODE'), (5000, 'DUDOSO')]
        for corte, esperado in casos:
            self.assertEqual(core.classify_cutoff(corte, RATE)[0], esperado,
                             msg=f'{corte} Hz deberia dar {esperado}')


# --- colapso del estereo -----------------------------------------------------

class TestEstereo(unittest.TestCase):
    def _par(self, corte_lateral, seconds=8.0):
        mid = noise(seconds, seed=1)
        side = lowpass(noise(seconds, seed=2), corte_lateral)
        return quantize16(mid + side), quantize16(mid - side)

    def test_detecta_el_colapso_en_su_frecuencia(self):
        for objetivo in (6000, 9000, 13000):
            izq, der = self._par(objetivo)
            data = np.column_stack([izq, der]).astype(np.float32)
            mid_mag, freqs, _ = core.stft_mag(data.mean(axis=1), RATE)
            side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
            medido = core.detect_stereo_collapse(mid_mag, side_mag, freqs, 22050)
            self.assertIsNotNone(medido, f'no detecto el colapso de {objetivo} Hz')
            self.assertAlmostEqual(medido, objetivo, delta=600)

    def test_regresion_no_lo_tapa_el_ruido_de_cuantizacion(self):
        """El detector exigia que TODA la banda estuviera muerta.

        En un archivo de 16 bits el ruido de cuantizacion levanta el canal
        lateral cerca de Nyquist, donde la musica ya se apago, y esa franja
        invalidaba la deteccion entera: nunca disparaba en archivos reales.
        """
        izq, der = self._par(8000)
        data = np.column_stack([izq, der]).astype(np.float32)
        mid_mag, freqs, _ = core.stft_mag(data.mean(axis=1), RATE)
        side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
        self.assertIsNotNone(
            core.detect_stereo_collapse(mid_mag, side_mag, freqs, 22050),
            'volvio a fallar con ruido de cuantizacion de 16 bits')

    def test_no_dispara_con_estereo_sano(self):
        izq = noise(seed=1)
        der = noise(seed=2)
        data = np.column_stack([izq, der]).astype(np.float32)
        mid_mag, freqs, _ = core.stft_mag(data.mean(axis=1), RATE)
        side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
        self.assertIsNone(core.detect_stereo_collapse(mid_mag, side_mag, freqs, 22050))

    def test_material_casi_mono_no_se_juzga(self):
        # Sin diferencia entre canales la prueba no significa nada y debe abstenerse
        mono = noise(seed=3)
        data = np.column_stack([mono, mono * 0.999]).astype(np.float32)
        mid_mag, freqs, _ = core.stft_mag(data.mean(axis=1), RATE)
        side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
        self.assertIsNone(core.detect_stereo_collapse(mid_mag, side_mag, freqs, 22050))


# --- pico real ---------------------------------------------------------------

class TestPicoReal(unittest.TestCase):
    def test_regresion_no_infla_el_pico_por_los_bordes(self):
        """El sobremuestreo por bloques repicaba en los extremos (Gibbs).

        Ese repique sumaba mas de 1 dB al pico real y el aviso saltaba en todos
        los archivos, incluso en los que no llegaban ni a 0 dBFS.
        """
        t = np.arange(int(6 * RATE)) / RATE
        # Senoidal grave: entre muestras casi no sube respecto del pico muestreado
        señal = np.sin(2 * np.pi * 100 * t) * 0.5
        muestra = 20 * np.log10(np.abs(señal).max())
        real = master.true_peak_db(señal, RATE)
        self.assertLess(real - muestra, 0.15,
                        f'pico real {real:.2f} dB contra muestra {muestra:.2f} dB')

    def test_detecta_pico_entre_muestras(self):
        # Senoidal a un cuarto del muestreo, desfasada: las muestras caen a los
        # costados del maximo real, que queda por encima
        t = np.arange(int(4 * RATE))
        señal = np.sin(2 * np.pi * t / 4 + np.pi / 4) * 0.9
        self.assertGreater(master.true_peak_db(señal, RATE),
                           20 * np.log10(np.abs(señal).max()))


# --- clipeo ------------------------------------------------------------------

class TestClipeo(unittest.TestCase):
    def test_cuenta_mesetas_y_no_muestras_sueltas(self):
        data = np.zeros((1000, 1), dtype=np.float32)
        data[10] = 1.0                 # suelta: no es meseta
        data[100:104] = 1.0            # meseta de 4
        data[500:503] = -1.0           # meseta de 3, negativa
        total, runs = master.clipping(data)
        self.assertEqual(total, 8)
        self.assertEqual(runs, 2)

    def test_regresion_meseta_a_caballo_de_dos_bloques(self):
        """El conteo pasó a ir por bloques para bajar la memoria.

        Una meseta que cruza el limite entre bloques se veria como dos trozos
        cortos, o se perderia, si no se arrastra el estado de un bloque al otro.
        """
        chunk = 256
        data = np.zeros((chunk * 3, 1), dtype=np.float32)
        data[chunk - 2:chunk + 2] = 1.0     # 4 muestras cruzando el borde
        total, runs = master.clipping(data, chunk=chunk)
        self.assertEqual(total, 4)
        self.assertEqual(runs, 1, 'la meseta a caballo se conto mal')

    def test_por_bloques_da_igual_que_de_una(self):
        rng = np.random.default_rng(7)
        data = np.sign(rng.standard_normal((5000, 2))).astype(np.float32)
        data *= (rng.random((5000, 2)) > 0.5)
        self.assertEqual(master.clipping(data, chunk=5000),
                         master.clipping(data, chunk=64))


# --- compatibilidad mono -----------------------------------------------------

class TestMono(unittest.TestCase):
    def _mags(self, izq, der):
        data = np.column_stack([izq, der]).astype(np.float32)
        mid_mag, freqs, _ = core.stft_mag(data.mean(axis=1), RATE)
        side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
        return data, mid_mag, side_mag, freqs

    def test_graves_en_fase_no_pierden_nada(self):
        bajo = lowpass(noise(seed=4), 100)
        _, mid_mag, side_mag, freqs = self._mags(bajo, bajo)
        self.assertGreater(master.mono_bass_loss(mid_mag, side_mag, freqs), -0.5)

    def test_graves_invertidos_se_cancelan(self):
        bajo = lowpass(noise(seed=4), 100)
        _, mid_mag, side_mag, freqs = self._mags(bajo, -bajo)
        perdida = master.mono_bass_loss(mid_mag, side_mag, freqs)
        self.assertLess(perdida, -20, f'perdida medida {perdida:.1f} dB')

    def test_correlacion(self):
        x = noise(2.0, seed=5)
        y = noise(2.0, seed=6)
        iguales = np.column_stack([x, x]).astype(np.float32)
        opuestos = np.column_stack([x, -x]).astype(np.float32)
        distintos = np.column_stack([x, y]).astype(np.float32)
        self.assertAlmostEqual(master.channel_correlation(iguales), 1.0, places=4)
        self.assertAlmostEqual(master.channel_correlation(opuestos), -1.0, places=4)
        self.assertAlmostEqual(master.channel_correlation(distintos), 0.0, places=2)

    def test_correlacion_por_bloques_no_cambia_el_resultado(self):
        x = noise(3.0, seed=5)
        data = np.column_stack([x, x * 0.5 + noise(3.0, seed=6) * 0.5]).astype(np.float32)
        esperado = float(np.corrcoef(data[:, 0], data[:, 1])[0, 1])
        self.assertAlmostEqual(master.channel_correlation(data), esperado, places=5)


# --- metadatos del archivo ---------------------------------------------------

class TestArchivo(unittest.TestCase):
    def test_detecta_24_bits_que_en_realidad_son_16(self):
        # Valores enteros de 16 bits divididos por 2^15: al escribirlos en 24
        # bits quedan multiplicados por 256 exactos, que es justo el relleno de
        # ceros que hay que detectar
        k = np.random.default_rng(8).integers(-20000, 20000, RATE)
        k[0] = 12345    # impar, para que los ceros al final sean exactamente 16
        x = k.astype(np.float64) / 32768.0
        real = write_temp(np.column_stack([x, x]), subtype='PCM_24')
        try:
            usados, declarados = master.effective_bits(real, 'PCM_24')
            self.assertEqual(declarados, 24)
            self.assertEqual(usados, 16, 'no vio que el contenido es de 16 bits')
        finally:
            real.unlink(missing_ok=True)

    def test_un_24_bits_genuino_se_reconoce(self):
        x = noise(1.0, seed=12)
        real = write_temp(np.column_stack([x, x]), subtype='PCM_24')
        try:
            usados, declarados = master.effective_bits(real, 'PCM_24')
            self.assertEqual((usados, declarados), (24, 24))
        finally:
            real.unlink(missing_ok=True)

    def test_samplerate_estirado(self):
        self.assertEqual(master.fake_samplerate(96000, 21000), 44100)
        self.assertIsNone(master.fake_samplerate(96000, 40000))
        self.assertIsNone(master.fake_samplerate(44100, 21000))


# --- veredicto ---------------------------------------------------------------

class TestVeredicto(unittest.TestCase):
    def test_el_estereo_colapsado_pesa_mas_que_un_corte_limpio(self):
        verdict, _, signals = core.combine('LOSSLESS', 'espectro completo', 8000.0)
        self.assertEqual(verdict, 'TRANSCODE')
        self.assertEqual(len(signals), 1)

    def test_sin_senales_manda_el_corte(self):
        for entrada in ('LOSSLESS', 'SOSPECHOSO', 'TRANSCODE', 'DUDOSO'):
            verdict, detalle, signals = core.combine(entrada, 'texto', None)
            self.assertEqual(verdict, entrada)
            self.assertEqual(detalle, 'texto')
            self.assertEqual(signals, [])

    def test_todo_veredicto_tiene_color(self):
        for corte in (22050, 20200, 18000, 5000):
            verdict = core.classify_cutoff(corte, RATE)[0]
            self.assertIn(verdict, core.VERDICT_COLORS)


# --- dibujado y resumen ------------------------------------------------------

class TestSalida(unittest.TestCase):
    def test_reduccion_temporal_conserva_los_picos(self):
        db = np.full((10, 1000), -100.0)
        db[5, 777] = -3.0     # un transitorio aislado no debe desaparecer
        chico, tiempos = core.downsample_time(db, np.arange(1000.0), max_cols=100)
        self.assertLessEqual(chico.shape[1], 100)
        self.assertEqual(chico.shape[1], len(tiempos))
        self.assertAlmostEqual(chico[5].max(), -3.0)

    def test_no_reduce_si_ya_entra(self):
        db = np.zeros((4, 50))
        chico, tiempos = core.downsample_time(db, np.arange(50.0), max_cols=100)
        self.assertEqual(chico.shape, db.shape)
        self.assertEqual(len(tiempos), 50)

    def test_las_columnas_del_csv_existen_en_el_resumen(self):
        datos = np.column_stack([noise(2.0, seed=9), noise(2.0, seed=10)])
        ruta = write_temp(datos)
        try:
            resumen = core.summary(core.analyze(ruta), ruta)
            for clave, _ in core.CSV_COLUMNS:
                self.assertIn(clave, resumen, f'el CSV pide "{clave}" y no esta')
        finally:
            ruta.unlink(missing_ok=True)

    def test_el_resumen_no_arrastra_los_arreglos_grandes(self):
        datos = np.column_stack([noise(2.0, seed=9), noise(2.0, seed=10)])
        ruta = write_temp(datos)
        try:
            resumen = core.summary(core.analyze(ruta), ruta)
            for pesado in ('db', 'side_db', 'freqs', 'times'):
                self.assertNotIn(pesado, resumen,
                                 f'"{pesado}" en el resumen dispara la memoria del lote')
        finally:
            ruta.unlink(missing_ok=True)


# --- sonoridad ---------------------------------------------------------------

class TestLufs(unittest.TestCase):
    """Calibracion contra los valores exactos que da la norma.

    Para una senoidal identica en los dos canales el resultado se puede
    calcular a mano: pico - 3.01 (de pico a eficaz) + 3.01 (dos canales) mas la
    ganancia del filtro K a esa frecuencia, menos el 0.691 de la norma.
    """

    def _medir(self, amp_db, freq=1000.0, seconds=12.0, estereo=True):
        t = np.arange(int(seconds * RATE)) / RATE
        x = (np.sin(2 * np.pi * freq * t) * 10 ** (amp_db / 20)).astype(np.float32)
        data = np.column_stack([x, x] if estereo else [x, np.zeros_like(x)])
        mid_mag, freqs, times = core.stft_mag(data.mean(axis=1), RATE)
        side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
        return loudness.integrated_lufs(mid_mag, side_mag, freqs, RATE,
                                        float(times[1] - times[0]))

    def _exacto(self, amp_db, freq):
        k = 10 * np.log10(loudness.k_weight_power(np.array([freq]), RATE))[0]
        return amp_db + k + loudness.OFFSET_DB

    def test_calibracion(self):
        for amp, freq in [(0.0, 1000.0), (-20.0, 1000.0), (-6.0, 1000.0),
                          (-10.0, 4000.0), (-10.0, 100.0)]:
            with self.subTest(amp=amp, freq=freq):
                self.assertAlmostEqual(self._medir(amp, freq),
                                       self._exacto(amp, freq), delta=0.05)

    def test_un_canal_da_tres_db_menos(self):
        dos = self._medir(-20.0)
        uno = self._medir(-20.0, estereo=False)
        self.assertAlmostEqual(dos - uno, 3.01, delta=0.05)

    def test_forma_del_filtro_k(self):
        # Atenua graves y levanta agudos unos 4 dB, que es lo que define al filtro
        g = 10 * np.log10(loudness.k_weight_power(
            np.array([20.0, 100.0, 1000.0, 10000.0]), RATE))
        self.assertLess(g[0], -10)
        self.assertLess(g[1], 0)
        self.assertAlmostEqual(g[3], 4.0, delta=0.3)
        self.assertLess(g[1], g[2])
        self.assertLess(g[2], g[3])

    def test_la_compuerta_ignora_el_silencio(self):
        # Un tramo fuerte seguido de silencio tiene que medir como el tramo solo
        t = np.arange(int(10 * RATE)) / RATE
        tono = np.sin(2 * np.pi * 1000 * t) * 0.1
        con_silencio = np.concatenate([tono, np.zeros(int(10 * RATE))])

        def medir(x):
            data = np.column_stack([x, x]).astype(np.float32)
            mid_mag, freqs, times = core.stft_mag(data.mean(axis=1), RATE)
            side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
            return loudness.integrated_lufs(mid_mag, side_mag, freqs, RATE,
                                            float(times[1] - times[0]))

        self.assertAlmostEqual(medir(tono), medir(con_silencio), delta=0.3)

    def test_ganancia_de_streaming(self):
        self.assertAlmostEqual(loudness.streaming_gain(-9.0), -5.0, places=6)
        self.assertAlmostEqual(loudness.streaming_gain(-20.0), 6.0, places=6)
        self.assertIsNone(loudness.streaming_gain(None))


# --- repetidos ---------------------------------------------------------------

class TestRepetidos(unittest.TestCase):
    def _huella(self, señal):
        mag, freqs, _ = core.stft_mag(señal.astype(np.float32), RATE)
        return dupes.fingerprint(core.to_db(mag, mag.max()), freqs)

    def test_el_mismo_audio_da_la_misma_huella(self):
        x = noise(12.0, seed=20)
        self.assertAlmostEqual(dupes.similarity(self._huella(x), self._huella(x)),
                               1.0, places=5)

    def test_sobrevive_a_un_recorte_de_agudos(self):
        """La huella se queda debajo de 12 kHz justamente para esto.

        Si tomara todo el espectro, el mismo tema en FLAC y en MP3 daria huellas
        distintas, que es lo contrario de lo que se busca.
        """
        x = noise(12.0, seed=21)
        parecido = dupes.similarity(self._huella(x), self._huella(lowpass(x, 16000)))
        self.assertGreater(parecido, dupes.MATCH_THRESHOLD)

    def test_el_volumen_no_cambia_la_huella(self):
        x = noise(12.0, seed=22)
        self.assertGreater(dupes.similarity(self._huella(x), self._huella(x * 0.2)),
                           0.99)

    def test_audio_distinto_da_huella_distinta(self):
        a = self._huella(noise(12.0, seed=23))
        b = self._huella(lowpass(noise(12.0, seed=24), 4000))
        self.assertLess(dupes.similarity(a, b), dupes.MATCH_THRESHOLD)

    def test_agrupa_por_transitividad(self):
        h = self._huella(noise(12.0, seed=25))
        otra = self._huella(lowpass(noise(12.0, seed=26), 3000))
        entradas = [
            dict(name='a', duration=200.0, fingerprint=h),
            dict(name='b', duration=200.5, fingerprint=h),
            dict(name='c', duration=201.0, fingerprint=h),
            dict(name='d', duration=200.0, fingerprint=otra),
        ]
        grupos = dupes.find_duplicates(entradas)
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0], [0, 1, 2], 'no junto las tres copias en un grupo')

    def test_duraciones_muy_distintas_no_se_comparan(self):
        h = self._huella(noise(12.0, seed=27))
        entradas = [dict(name='corto', duration=100.0, fingerprint=h),
                    dict(name='largo', duration=400.0, fingerprint=h)]
        self.assertEqual(dupes.find_duplicates(entradas), [])

    def test_sin_repetidos_no_inventa_grupos(self):
        entradas = [dict(name='a', duration=200.0, fingerprint=self._huella(noise(12.0, seed=28))),
                    dict(name='b', duration=200.0,
                         fingerprint=self._huella(lowpass(noise(12.0, seed=29), 2000)))]
        self.assertEqual(dupes.find_duplicates(entradas), [])
        self.assertEqual(dupes.describe([], entradas), 'sin repetidos')


# --- referencia de produccion ------------------------------------------------

class TestReferencia(unittest.TestCase):
    def _archivo(self, izq, der):
        return write_temp(np.column_stack([izq, der]))

    def test_el_suavizado_conserva_la_forma(self):
        # Ruido rosa: baja 3 dB por octava, y eso tiene que seguir viendose
        rng = np.random.default_rng(30)
        n = RATE * 4
        espectro = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / RATE)
        espectro[1:] /= np.sqrt(f[1:])
        x = np.fft.irfft(espectro, n)
        x = x / np.abs(x).max() * 0.5

        ruta = self._archivo(x, x)
        try:
            curvas = ref.tonal_balance(ref.average_spectrum(ruta))
        finally:
            ruta.unlink(missing_ok=True)

        def nivel(hz):
            return curvas['mid'][np.argmin(np.abs(curvas['freqs'] - hz))]

        # Una decada arriba tiene que haber caido unos 10 dB
        self.assertAlmostEqual(nivel(200) - nivel(2000), 10.0, delta=3.0)

    def test_resolucion_en_el_grave(self):
        """La FFT grande existe para esto: que el grave no salga escalonado."""
        paso = ref.FFT_SIZE
        bandas_bajo_100 = int(100 / (RATE / paso))
        self.assertGreater(bandas_bajo_100, 50,
                           'muy pocas bandas debajo de 100 Hz para un eje log')

    def test_sub_centrado_contra_sub_ancho(self):
        bajo = lowpass(noise(6.0, seed=31), 90)
        # Filtrado: con ruido blanco el lateral tendria contenido grave propio
        # y el sub nunca podria medirse centrado
        agudo = highpass(noise(6.0, seed=32), 300) * 0.3

        centrado = self._archivo(bajo + agudo, bajo - agudo)      # grave en fase
        ancho = self._archivo(bajo + agudo, -bajo - agudo)        # grave invertido
        try:
            w_ok = ref.stereo_width(ref.average_spectrum(centrado))
            w_mal = ref.stereo_width(ref.average_spectrum(ancho))
        finally:
            centrado.unlink(missing_ok=True)
            ancho.unlink(missing_ok=True)

        grave = w_ok['freqs'] <= 80
        self.assertLess(w_ok['width'][grave].max(), -12, 'no vio el sub centrado')
        self.assertGreater(w_mal['width'][grave].max(), 0, 'no vio el sub invertido')
        self.assertIn('centrado', ref.mono_verdict(w_ok))
        self.assertIn('ancho', ref.mono_verdict(w_mal))

    def test_regresion_el_veredicto_ignora_bandas_vacias(self):
        """El veredicto lo decidia una zona sin contenido musical.

        Debajo de 25 Hz casi ningun tema tiene energia, y ahi la relacion entre
        lateral y central es el cociente de dos ruidos: daba numeros al azar que
        se llevaban puesto el resultado.
        """
        bajo = lowpass(noise(6.0, seed=33), 90)
        # Sin nada debajo de 25 Hz, que es el caso que rompia
        sin_infra = bajo - lowpass(bajo, 25)
        ruta = self._archivo(sin_infra, sin_infra * 0.98)
        try:
            w = ref.stereo_width(ref.average_spectrum(ruta))
        finally:
            ruta.unlink(missing_ok=True)
        self.assertIn('centrado', ref.mono_verdict(w),
                      'una banda vacia volvio a decidir el veredicto')

    def test_mono_no_tiene_ancho(self):
        x = noise(4.0, seed=34)
        ruta = write_temp(x.reshape(-1, 1))
        try:
            spec = ref.average_spectrum(ruta)
            self.assertIsNone(ref.stereo_width(spec))
            self.assertEqual(ref.mono_verdict(None), 'archivo mono')
        finally:
            ruta.unlink(missing_ok=True)

    def test_escala_comparable_con_dbfs(self):
        # Una senoidal a media escala no puede dar niveles positivos enormes
        t = np.arange(RATE * 4) / RATE
        x = np.sin(2 * np.pi * 1000 * t) * 0.5
        ruta = self._archivo(x, x)
        try:
            curvas = ref.tonal_balance(ref.average_spectrum(ruta))
        finally:
            ruta.unlink(missing_ok=True)
        self.assertLess(curvas['mid'].max(), 6.0,
                        'la escala volvio a quedar sin normalizar')


    def test_sonoridad_desde_el_espectro_coincide(self):
        """La referencia se carga suelta y nunca pasa por el analisis.

        Si su sonoridad no se puede sacar del propio espectro, las curvas se
        superponen desalineadas y la comparacion no sirve para nada.
        """
        t = np.arange(RATE * 8) / RATE
        x = (np.sin(2 * np.pi * 1000 * t) * 0.25).astype(np.float32)
        # Mono en los dos caminos: un archivo estereo suma los dos canales y da
        # 3 dB mas, asi que comparar uno contra otro media cosas distintas
        ruta = write_temp(x.reshape(-1, 1))
        try:
            spec = ref.average_spectrum(ruta)
            desde_espectro = ref.integrated_from_spec(spec)

            mid_mag, freqs, times = core.stft_mag(x, RATE)
            por_analisis = loudness.integrated_lufs(
                mid_mag, None, freqs, RATE, float(times[1] - times[0]))
        finally:
            ruta.unlink(missing_ok=True)
        self.assertAlmostEqual(desde_espectro, por_analisis, delta=1.0)

    def test_corto_plazo_sigue_los_cambios_de_nivel(self):
        # Veinte segundos: la ventana de corto plazo dura tres, y con un archivo
        # corto quedan tan pocos puntos que los promedios salen vacios
        t = np.arange(RATE * 20) / RATE
        tono = np.sin(2 * np.pi * 1000 * t)
        tono[len(tono) // 2:] *= 10 ** (-10 / 20)   # segunda mitad 10 dB abajo
        x = (tono * 0.4).astype(np.float32)
        ruta = self._archivo(x, x)
        try:
            curva = ref.short_term_loudness(ref.average_spectrum(ruta))
        finally:
            ruta.unlink(missing_ok=True)
        self.assertIsNotNone(curva)
        tiempos, lufs = curva
        # Lejos del salto en los dos sentidos, para no medir la transicion
        antes = lufs[(tiempos > 2.0) & (tiempos < 7.0)].mean()
        despues = lufs[tiempos > 15.0].mean()
        self.assertAlmostEqual(antes - despues, 10.0, delta=1.5)


class TestLateralSobreCentral(unittest.TestCase):
    def _mags(self, izq, der):
        data = np.column_stack([izq, der]).astype(np.float32)
        mid_mag, freqs, _ = core.stft_mag(data.mean(axis=1), RATE)
        side_mag, _, _ = core.stft_mag((data[:, 0] - data[:, 1]) / 2, RATE)
        return mid_mag, side_mag, freqs

    def test_no_avisa_con_estereo_sano(self):
        x = noise(6.0, seed=50)
        y = noise(6.0, seed=51) * 0.4
        self.assertEqual(core.bands_side_over_mid(*self._mags(x + y, x - y)), [])

    def test_regresion_ve_el_grave_invertido(self):
        """El ancho minimo estaba en hertz y se perdia el caso mas grave.

        Doscientos hertz son nada en agudos pero mas que toda la zona del sub,
        que mide unos ciento treinta. Con un tema de grave fuera de fase el
        aviso no aparecia justo donde mas importaba.
        """
        bajo = lowpass(noise(6.0, seed=52), 120)
        agudo = highpass(noise(6.0, seed=53), 400) * 0.3
        # El grave va al lateral: se cancela al sumar a mono
        tramos = core.bands_side_over_mid(*self._mags(bajo + agudo, -bajo + agudo))
        self.assertTrue(tramos, 'no vio el grave invertido')
        desde, hasta = tramos[0]
        self.assertLess(desde, 60)
        self.assertGreater(hasta, 90)
        self.assertIn('lateral supera', core.describe_side_over_mid(tramos))

    def test_una_banda_suelta_no_alcanza(self):
        # Un pico angosto no es un problema de compatibilidad mono
        t = np.arange(int(6 * RATE)) / RATE
        base = noise(6.0, seed=54)
        tono = np.sin(2 * np.pi * 9000 * t) * 0.02
        tramos = core.bands_side_over_mid(*self._mags(base + tono, base - tono))
        self.assertEqual(tramos, [], 'una banda suelta no deberia avisar')

    def test_texto_vacio_sin_tramos(self):
        self.assertEqual(core.describe_side_over_mid([]), '')


class TestEjeLogaritmico(unittest.TestCase):
    def _espectrograma(self):
        mag, freqs, _ = core.stft_mag(noise(4.0, seed=40).astype(np.float32), RATE)
        return core.to_db(mag, mag.max()), freqs

    def test_forma_y_bordes(self):
        db, freqs = self._espectrograma()
        bandas, bordes = core.to_log_bands(db, freqs, n_bands=120)
        self.assertEqual(bandas.shape, (120, db.shape[1]))
        # pcolormesh con celdas planas necesita un borde mas que filas
        self.assertEqual(len(bordes), 121)
        self.assertTrue(np.all(np.diff(bordes) > 0), 'los bordes deben crecer')

    def test_conserva_los_picos(self):
        db, freqs = self._espectrograma()
        db[500, 10] = 0.0    # un maximo aislado no puede desaparecer
        bandas, _ = core.to_log_bands(db, freqs, n_bands=120)
        self.assertAlmostEqual(bandas[:, 10].max(), 0.0)

    def test_la_pendiente_baja_el_grave_y_sube_el_agudo(self):
        """Sin inclinar, el grave satura en blanco en la vista logaritmica.

        La musica cae unos tres decibeles por octava, asi que en un eje
        logaritmico el grave ocupa un tercio del grafico todo al tope de la
        paleta y no se distingue el bombo del bajo.
        """
        db, freqs = self._espectrograma()
        inclinado = core.tilt(db, freqs)
        grave = (freqs >= 20) & (freqs <= 100)
        agudo = (freqs >= 5000) & (freqs <= 10000)
        self.assertLess(np.median(inclinado[grave]), np.median(db[grave]) - 8)
        self.assertGreater(np.median(inclinado[agudo]), np.median(db[agudo]) + 4)

    def test_la_pendiente_no_toca_el_eje(self):
        db, freqs = self._espectrograma()
        inclinado = core.tilt(db, freqs)
        i = int(np.argmin(np.abs(freqs - core.TILT_PIVOT_HZ)))
        self.assertAlmostEqual(float(inclinado[i, 0]), float(db[i, 0]), delta=0.2)

    def test_ninguna_banda_queda_vacia(self):
        db, freqs = self._espectrograma()
        bandas, _ = core.to_log_bands(db, freqs, n_bands=300)
        self.assertFalse(np.isnan(bandas).any(), 'una banda quedo sin datos')


# --- perfil objetivo ---------------------------------------------------------

def pink(seconds=4.0, seed=0, rate=RATE):
    """Ruido rosa: cae 3 dB por octava, parecido a la forma de la musica."""
    n = int(seconds * rate)
    espectro = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / rate)
    espectro[1:] /= np.sqrt(f[1:])
    x = np.fft.irfft(espectro, n)
    return x / np.abs(x).max() * 0.4


def campana(x, centro_hz, ganancia_db, ancho_oct=0.25, rate=RATE):
    """Suma una campana de ganancia conocida, para tener un desvio medible."""
    espectro = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / rate)
    with np.errstate(divide='ignore'):
        octavas = np.log2(np.maximum(f, 1e-6) / centro_hz)
    forma = np.exp(-0.5 * (octavas / ancho_oct) ** 2)
    return np.fft.irfft(espectro * 10 ** (ganancia_db * forma / 20), len(x))


class TestPerfil(unittest.TestCase):
    def _archivo(self, x, ganancia=1.0):
        señal = np.column_stack([x, x]) * ganancia
        return write_temp(señal)

    def test_detecta_un_desvio_conocido(self):
        """Ruido rosa contra el mismo ruido con +4 dB en 3 kHz.

        Es la prueba de fondo: si el perfil no ve un desvio que pusimos a mano,
        tampoco va a ver los de una mezcla real.

        Se mide algo menos de 4 dB y no es un error: ver
        `test_la_sonoridad_absorbe_parte_del_realce`.
        """
        base = [self._archivo(pink(seed=s)) for s in (60, 61, 62)]
        desviado = self._archivo(campana(pink(seed=60), 3000, 4.0))
        try:
            perfil = prof.construir(base, 'base')
            curvas = ref.tonal_balance(
                ref.average_spectrum(desviado),
                -ref.integrated_from_spec(ref.average_spectrum(desviado)))
        finally:
            for r in base + [desviado]:
                r.unlink(missing_ok=True)

        f = perfil['freqs']
        i = int(np.argmin(np.abs(f - 3000)))
        medido = curvas['mid'][i] - perfil['mid']['mediana'][i]
        self.assertAlmostEqual(medido, 4.0, delta=1.0,
                               msg=f'desvio de +4 dB medido como {medido:+.2f}')

    def test_la_sonoridad_absorbe_parte_del_realce(self):
        """Un realce ancho se mide mas chico de lo que es, y con razon.

        Las curvas se alinean por sonoridad. Subir una banda sube tambien la
        sonoridad del tema, asi que al alinear se resta parte de lo mismo que
        se quiere medir: cuanto mas ancha la campana, mas se absorbe.

        Queda anotado porque importa al traducir desvios a ganancias de EQ: la
        diferencia hay que leerla como forma, no como valor absoluto.
        """
        base_x = pink(seed=65)
        base = self._archivo(base_x)
        anchos = {}
        rutas = []
        try:
            spec_base = ref.average_spectrum(base)
            curva_base = ref.tonal_balance(spec_base, -ref.integrated_from_spec(spec_base))
            for ancho in (0.25, 1.0):
                r = self._archivo(campana(base_x, 3000, 4.0, ancho))
                rutas.append(r)
                spec = ref.average_spectrum(r)
                curva = ref.tonal_balance(spec, -ref.integrated_from_spec(spec))
                i = int(np.argmin(np.abs(curva['freqs'] - 3000)))
                anchos[ancho] = curva['mid'][i] - curva_base['mid'][i]
        finally:
            base.unlink(missing_ok=True)
            for r in rutas:
                r.unlink(missing_ok=True)

        # La angosta se acerca a los 4 dB; la ancha se absorbe bastante mas
        self.assertGreater(anchos[0.25], anchos[1.0] + 0.8)
        self.assertLess(anchos[1.0], 3.0)

    def test_regresion_normaliza_por_sonoridad(self):
        """Dos copias del mismo audio a distinto volumen tienen que dar la misma curva.

        Sin normalizar por sonoridad, el perfil terminaria describiendo que tan
        fuerte estaba masterizado cada archivo en vez de su balance, y la franja
        de tolerancia se abriria por una diferencia que no es de balance.
        """
        x = pink(seed=63)
        fuerte = self._archivo(x)
        flojo = self._archivo(x, ganancia=10 ** (-9 / 20))   # 9 dB mas abajo
        try:
            perfil = prof.construir([fuerte, flojo], 'niveles')
        finally:
            fuerte.unlink(missing_ok=True)
            flojo.unlink(missing_ok=True)

        ancho = perfil['mid']['alto'] - perfil['mid']['bajo']
        # Con N=2 la franja es el margen fijo; lo que importa es que las dos
        # curvas coincidan, o sea que la mediana no se haya corrido
        self.assertAlmostEqual(float(np.median(ancho)), 2 * prof.MARGEN_FIJO_DB,
                               delta=0.01)

    def test_la_tolerancia_sale_de_los_datos_con_tres_o_mas(self):
        con_tres = [self._archivo(pink(seed=s)) for s in (70, 71, 72)]
        con_dos = con_tres[:2]
        try:
            self.assertIn('percentiles', prof.construir(con_tres, 'a')['mid']['origen'])
            self.assertIn('margen fijo', prof.construir(con_dos, 'b')['mid']['origen'])
        finally:
            for r in con_tres:
                r.unlink(missing_ok=True)

    def test_guardar_y_cargar_no_pierde_nada(self):
        import tempfile as tmp
        archivos = [self._archivo(pink(seed=s)) for s in (80, 81, 82)]
        carpeta = Path(tmp.mkdtemp())
        try:
            perfil = prof.construir(archivos, 'ida y vuelta')
            ruta = prof.guardar(perfil, carpeta)
            vuelto = prof.cargar(ruta)

            self.assertEqual(vuelto['nombre'], perfil['nombre'])
            self.assertEqual(vuelto['n'], perfil['n'])
            for canal in ('mid', 'side'):
                if perfil[canal]:
                    for clave in ('mediana', 'bajo', 'alto'):
                        self.assertTrue(np.allclose(vuelto[canal][clave],
                                                    perfil[canal][clave]))
            self.assertEqual([n for n, _ in prof.listar(carpeta)], ['ida y vuelta'])
        finally:
            for r in archivos:
                r.unlink(missing_ok=True)
            for r in carpeta.glob('*'):
                r.unlink(missing_ok=True)
            carpeta.rmdir()

    def test_una_referencia_es_un_perfil_de_uno(self):
        ruta = self._archivo(pink(seed=90))
        try:
            perfil = prof.una_referencia(ref.average_spectrum(ruta), ruta)
        finally:
            ruta.unlink(missing_ok=True)
        self.assertEqual(perfil['n'], 1)
        self.assertIn('margen fijo', perfil['mid']['origen'])
        self.assertIsNotNone(perfil['lufs'])
        self.assertIsNotNone(perfil['true_peak_db'])

    def test_sin_archivos_legibles_no_hay_perfil(self):
        roto = temp_path()
        roto.write_bytes(b'no es audio')
        try:
            self.assertIsNone(prof.construir([roto], 'vacio'))
        finally:
            roto.unlink(missing_ok=True)

    def test_regresion_el_pico_real_coincide_con_el_analisis(self):
        """El perfil y el analisis median el mismo pico de formas distintas.

        El perfil lo saca del recorrido por bloques que ya hace. Guardando una
        cantidad fija de bloques para medirlos al final erraba hasta medio
        decibel contra el analisis: dos numeros distintos para la misma cosa en
        la misma herramienta.
        """
        t = np.arange(int(4 * RATE)) / RATE
        x = (np.sin(2 * np.pi * 997 * t) * 0.8).astype(np.float32)
        ruta = self._archivo(x)
        try:
            del_perfil = ref.average_spectrum(ruta)['true_peak_db']
            del_analisis = core.analyze(ruta)['master']['true_peak_db']
        finally:
            ruta.unlink(missing_ok=True)
        self.assertAlmostEqual(del_perfil, del_analisis, delta=0.05)


# --- balance por bandas ------------------------------------------------------

class TestBalance(unittest.TestCase):
    def _archivo(self, x):
        return write_temp(np.column_stack([x, x]))

    def _contra_perfil(self, x, semillas=(60, 61, 62)):
        base = [self._archivo(pink(seed=s)) for s in semillas]
        propio = self._archivo(x)
        try:
            perfil = prof.construir(base, 'base')
            spec = ref.average_spectrum(propio)
            curvas = ref.tonal_balance(spec, -ref.integrated_from_spec(spec))
        finally:
            for r in base + [propio]:
                r.unlink(missing_ok=True)
        return bal.deviation(curvas, perfil), perfil

    def test_regresion_el_centrado_recupera_el_realce(self):
        """Sin centrar, un realce de +4 dB se mide como +2.9.

        Las curvas se alinean por sonoridad y subir una banda sube la sonoridad
        del tema, asi que al alinear se resta parte de lo mismo que se quiere
        medir. Sin corregirlo, las ganancias de EQ sugeridas saldrian cortas y
        el resto del espectro se leeria bajo.
        """
        dev, perfil = self._contra_perfil(campana(pink(seed=60), 3000, 4.0, 0.5))
        i = int(np.argmin(np.abs(dev['freqs'] - 3000)))
        self.assertAlmostEqual(dev['diferencia'][i], 4.0, delta=1.0,
                               msg=f"medido {dev['diferencia'][i]:+.2f}")

    def test_sin_desvio_todo_queda_dentro(self):
        dev, _ = self._contra_perfil(pink(seed=60))
        filas = bal.band_report(dev)
        fuera = [f['banda'] for f in filas if f['estado'] == 'fuera']
        self.assertEqual(fuera, [], f'marco fuera de tolerancia: {fuera}')
        self.assertEqual(bal.eq_suggestions(filas), [])

    def test_el_realce_aparece_en_su_banda(self):
        dev, _ = self._contra_perfil(campana(pink(seed=60), 3000, 5.0, 0.5))
        filas = {f['banda']: f for f in bal.band_report(dev)}
        # 3 kHz cae en Upper-mid
        self.assertGreater(filas['Upper-mid']['desvio_db'], 2.0)
        self.assertEqual(filas['Upper-mid']['estado'], 'fuera')
        self.assertLess(abs(filas['Sub']['desvio_db']), 2.0)

    def test_la_sugerencia_corrige_al_reves(self):
        dev, _ = self._contra_perfil(campana(pink(seed=60), 3000, 5.0, 0.5))
        sugerencias = bal.eq_suggestions(bal.band_report(dev))
        upper = [s for s in sugerencias if s['banda'] == 'Upper-mid']
        self.assertTrue(upper, 'no sugirio nada para la banda desviada')
        self.assertLess(upper[0]['ganancia_db'], 0, 'un realce se corrige bajando')
        self.assertEqual(upper[0]['tipo'], 'bell')

    def test_la_ganancia_esta_acotada(self):
        filas = [{'banda': 'Mid', 'desde': 500, 'hasta': 2000, 'desvio_db': 12.0,
                  'estado': 'fuera', 'ancho_db': None}]
        s = bal.eq_suggestions(filas)[0]
        self.assertEqual(s['ganancia_db'], -bal.MAX_GANANCIA_DB)
        self.assertTrue(s['recortada'], 'no aviso que la correccion se recorto')

    def test_nunca_mas_de_ocho_movimientos(self):
        filas = [{'banda': n, 'desde': d, 'hasta': h, 'desvio_db': 3.0,
                  'estado': 'fuera', 'ancho_db': None}
                 for n, d, h in bal.BANDAS]
        self.assertLessEqual(len(bal.eq_suggestions(filas)), bal.MAX_BANDAS_EQ)

    def test_los_extremos_van_como_shelf(self):
        filas = [{'banda': n, 'desde': d, 'hasta': h, 'desvio_db': 3.0,
                  'estado': 'fuera', 'ancho_db': None}
                 for n, d, h in bal.BANDAS]
        tipos = {s['banda']: s['tipo'] for s in bal.eq_suggestions(filas)}
        self.assertEqual(tipos['Sub'], 'low shelf')
        self.assertEqual(tipos['Air'], 'high shelf')
        self.assertEqual(tipos['Mid'], 'bell')

    def test_regresion_la_etiqueta_no_redondea_a_cero(self):
        """'500 Hz - 2 kHz' se mostraba como '0-2 kHz'.

        Pasar los dos extremos a kilohertz porque uno supera los mil dejaba el
        otro en cero.
        """
        self.assertEqual(bal.etiqueta_rango(500, 2000), '500 Hz - 2 kHz')
        self.assertEqual(bal.etiqueta_hz(3162), '3.2 kHz')
        self.assertEqual(bal.etiqueta_hz(60), '60 Hz')

    def test_el_suavizado_no_corre_la_curva(self):
        freqs = ref.log_points()
        curva = np.full(len(freqs), 3.0)
        suave = bal.suavizar(curva, freqs)
        self.assertTrue(np.allclose(suave, 3.0, atol=0.01),
                        'una curva plana no deberia moverse al suavizar')

    def test_resumen_de_sonoridad(self):
        perfil = {'lufs': -9.0, 'true_peak_db': -0.5}
        filas = bal.loudness_summary({'lufs': -11.0, 'true_peak_db': 0.5}, perfil)
        por_que = {f['que']: f for f in filas}
        self.assertAlmostEqual(por_que['Sonoridad']['diferencia'], -2.0)
        self.assertAlmostEqual(por_que['Pico real']['diferencia'], 1.0)


# --- filtros y match ---------------------------------------------------------

class TestDsp(unittest.TestCase):
    """Los reemplazos de scipy tienen que dar lo mismo que scipy."""

    def test_firwin2_coincide_con_scipy(self):
        try:
            from scipy.signal import firwin2 as referencia
        except ImportError:
            self.skipTest('scipy no esta en este entorno')
        propio = dsp.firwin2(255, [0, 1000, 5000, 22050], [1.0, 2.0, 0.5, 0.5],
                             fs=44100)
        suyo = referencia(255, [0, 1000, 5000, 22050], [1.0, 2.0, 0.5, 0.5],
                          fs=44100)
        self.assertTrue(np.allclose(propio, suyo, atol=1e-12),
                        f'maxima diferencia {np.abs(propio - suyo).max():.2e}')

    def test_convolucion_por_bloques_coincide_con_la_directa(self):
        senal = np.random.default_rng(3).standard_normal(5000)
        nucleo = dsp.firwin2(129, [0, 4000, 22050], [1.0, 0.3, 0.3], fs=44100)
        self.assertTrue(np.allclose(dsp.fftconvolve(senal, nucleo),
                                    np.convolve(senal, nucleo), atol=1e-9))

    def test_filtrar_no_corre_la_senal(self):
        """Un FIR de fase lineal retrasa media ventana y ese retardo se descuenta.

        Si no se descontara, el tema procesado quedaria corrido unos
        milisegundos y compararlo con el original no tendria sentido.
        """
        senal = np.random.default_rng(4).standard_normal(4000)
        impulso = np.zeros(201)
        impulso[100] = 1.0
        salida = dsp.filtrar(senal, impulso)
        self.assertEqual(len(salida), len(senal))
        self.assertTrue(np.allclose(salida, senal, atol=1e-9))


class TestMatch(unittest.TestCase):
    def _archivo(self, x, ganancia=1.0):
        return write_temp(np.column_stack([x, x]) * ganancia)

    def _perfil(self, semillas=(70, 71, 72)):
        rutas = [self._archivo(pink(seed=s)) for s in semillas]
        try:
            return prof.construir(rutas, 'base'), rutas
        except Exception:
            for r in rutas:
                r.unlink(missing_ok=True)
            raise

    def test_corrige_un_desvio_conocido(self):
        """Con la correccion al maximo, el realce de +4 dB tiene que desaparecer.

        Es la prueba que cierra la cadena: el perfil lo mide, el filtro lo
        corrige y volver a medir el archivo escrito lo confirma.
        """
        perfil, rutas = self._perfil()
        desviado = self._archivo(campana(pink(seed=70), 3000, 4.0))
        salida = spectro_match.destino(desviado)
        try:
            data, rate, informe = spectro_match.procesar(
                desviado, perfil, amount=1.0, taps=4095, sub_mono=False)
            spectro_match.guardar(data, rate, salida)
            curvas = ref.tonal_balance(ref.average_spectrum(salida), 0.0)
            dev = bal.deviation(curvas, perfil, 'mid')
        finally:
            for r in rutas + [desviado, salida]:
                Path(r).unlink(missing_ok=True)

        i = int(np.argmin(np.abs(dev['freqs'] - 3000)))
        residuo = float(dev['diferencia'][i])
        self.assertLess(abs(residuo), 1.0,
                        f'quedo un desvio de {residuo:+.2f} dB en 3 kHz')

    def test_una_entrada_mono_sigue_siendo_mono(self):
        """Los dos canales iguales no tienen lateral, y el proceso no lo inventa.

        Importa porque el filtro del canal lateral y el pasa-altos del sub se
        aplican igual: si alguno metiera ruido, aparecerian diferencias entre
        canales que en el original no estaban.
        """
        perfil, rutas = self._perfil()
        mono = self._archivo(pink(seed=73))
        try:
            data, _rate, _informe = spectro_match.procesar(
                mono, perfil, amount=1.0, taps=4095, sub_mono=True)
        finally:
            for r in rutas + [mono]:
                r.unlink(missing_ok=True)

        lateral = (data[:, 0] - data[:, 1]) / 2
        nivel = 20 * np.log10(max(float(np.abs(lateral).max()), 1e-15))
        self.assertLess(nivel, -100, f'aparecio lateral en {nivel:.1f} dB')

    def test_nunca_pasa_del_techo_de_pico_real(self):
        """El limitador tiene que cumplir, tambien cuando la ganancia lo exige.

        Se inyectan picos y se pide una sonoridad alta: sin eso la
        normalizacion deja el tema tan abajo que el limitador no llega a
        actuar y la prueba pasaria sin haber probado nada.
        """
        perfil, rutas = self._perfil()
        x = pink(seed=74)
        x[np.arange(40) * (len(x) // 40)] = 0.95
        picudo = self._archivo(x)
        try:
            for objetivo in (-14.0, -9.0):
                data, rate, informe = spectro_match.procesar(
                    picudo, perfil, amount=0.5, taps=4095, sub_mono=False,
                    target_lufs=objetivo, techo_db=-1.0)
                medido = master.true_peak_db(data.mean(axis=1), rate)
                self.assertLessEqual(medido, -1.0 + 0.01,
                                     f'a {objetivo} LUFS quedo en {medido:+.3f} dBTP')
                self.assertAlmostEqual(informe['true_peak_final'], medido, delta=0.01)
        finally:
            for r in rutas + [picudo]:
                r.unlink(missing_ok=True)


# --- lote --------------------------------------------------------------------

class TestLote(unittest.TestCase):
    def test_regresion_los_errores_se_informan(self):
        """Un archivo que fallaba desaparecia de la cuenta sin decir nada.

        El aviso de error se mostraba y medio segundo despues lo pisaba el
        resumen final, asi que el lote quedaba corto sin explicacion.
        """
        bueno = write_temp(np.column_stack([noise(1.0, seed=11)] * 2))
        roto = temp_path()
        roto.write_bytes(b'esto no es audio')
        try:
            ok, fallos = [], []
            spectro_batch.run([bueno, roto], ok.append,
                              lambda p, e: fallos.append(p), workers=1)
            self.assertEqual(len(ok), 1)
            self.assertEqual(len(fallos), 1, 'el archivo roto no se informo')
        finally:
            bueno.unlink(missing_ok=True)
            roto.unlink(missing_ok=True)

    def test_los_procesos_se_eligen_por_memoria(self):
        self.assertEqual(spectro_batch.choose_workers(1), 1)
        self.assertGreaterEqual(spectro_batch.choose_workers(50), 1)
        self.assertLessEqual(spectro_batch.choose_workers(50), spectro_batch.MAX_WORKERS)

    def test_nunca_mas_procesos_que_archivos(self):
        self.assertLessEqual(spectro_batch.choose_workers(2), 2)


# --- archivos reales (opcional) ----------------------------------------------

MUSICA = Path('C:/Users/ratcl/Music/deemix Music')

# Valores verificados a mano contra cada archivo. Si un cambio los mueve, hay
# que entender por que antes de actualizarlos.
GOLDEN = {
    'GUY J FULL/76 - Guy J - Placebo.flac':
        dict(verdict='LOSSLESS', cutoff=21845, stereo=None, dr=8, clip_runs=0),
    'GUY J FULL/12 - Guy J - I Lost My Head (PM Mix).flac':
        dict(verdict='TRANSCODE', cutoff=19003, stereo=None, dr=10, clip_runs=0),
    'GUY J FULL/11 - Guy J - Synthopia.flac':
        dict(verdict='LOSSLESS', cutoff=22050, stereo=None, dr=9, clip_runs=177),
    '_TEST ANALIZADOR/TEST - estereo por intensidad 8kHz.flac':
        dict(verdict='TRANSCODE', cutoff=21845, stereo=7817, dr=9, clip_runs=0),
    '_TEST ANALIZADOR/TEST - estereo por intensidad 14000Hz.flac':
        dict(verdict='TRANSCODE', cutoff=21845, stereo=13822, dr=9, clip_runs=0),
}


class TestArchivosReales(unittest.TestCase):
    """Compara contra archivos concretos con valores ya verificados."""

    def test_golden(self):
        faltan = [n for n in GOLDEN if not (MUSICA / n).exists()]
        if faltan:
            self.skipTest(f'no estan los archivos de referencia ({len(faltan)} faltan)')

        for nombre, esperado in GOLDEN.items():
            with self.subTest(archivo=nombre):
                r = core.analyze(MUSICA / nombre)
                self.assertEqual(r['verdict'], esperado['verdict'])
                self.assertAlmostEqual(r['cutoff'], esperado['cutoff'], delta=60)
                if esperado['stereo'] is None:
                    self.assertIsNone(r['stereo_hz'])
                else:
                    self.assertAlmostEqual(r['stereo_hz'], esperado['stereo'], delta=60)
                self.assertAlmostEqual(r['master']['dr'], esperado['dr'], delta=0.5)
                self.assertEqual(r['master']['clip_runs'], esperado['clip_runs'])


def main():
    golden = '--golden' in sys.argv
    if golden:
        sys.argv.remove('--golden')
    else:
        # Por defecto se saltean: son archivos de cientos de MB y varios minutos
        TestArchivosReales.test_golden = unittest.skip(
            'usa --golden para correrlos')(TestArchivosReales.test_golden)
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()
