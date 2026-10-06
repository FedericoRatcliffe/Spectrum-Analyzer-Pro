"""Extrae metricas + curva tonal de cada tema y las vuelca a JSON.

No es parte del proyecto: es un trabajo de una sola vez para armar el perfil de
referencia de Guy J. Usa los mismos modulos que el analizador.

Uso: python referencias/extraer_perfil.py "<carpeta de audio>" salida.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import spectro_core as core
import spectro_reference as ref
import spectro_loudness as loud

# Centros de tercio de octava, de 20 Hz a 20 kHz
THIRD_OCT = np.array([20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250,
                      315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500,
                      3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000],
                     dtype=float)

MACRO = [('sub', 20, 60), ('bajo', 60, 120), ('bajo_medio', 120, 400),
         ('medio', 400, 2000), ('medio_alto', 2000, 6000),
         ('agudo', 6000, 12000), ('aire', 12000, 20000)]


def band_power(freqs, power, lo, hi):
    i = np.searchsorted(freqs, lo, 'left')
    j = np.searchsorted(freqs, hi, 'right')
    if j <= i:
        j = i + 1
    return float(power[i:j].sum())


def third_octave(freqs, power):
    """Potencia por banda de tercio de octava."""
    razon = 2 ** (1 / 6)
    return np.array([band_power(freqs, power, c / razon, c * razon)
                     for c in THIRD_OCT])


def lra(times_lufs, integrado):
    """Rango de sonoridad aproximado: p95 - p10 del corto plazo con compuerta."""
    if times_lufs is None or integrado is None:
        return None
    vals = times_lufs[1]
    vals = vals[vals > integrado - 20.0]
    if len(vals) < 10:
        return None
    return float(np.percentile(vals, 95) - np.percentile(vals, 10))


def one(path):
    path = Path(path)
    res = core.analyze(path)
    s = core.summary(res, path)
    m = res['master']

    spec = ref.average_spectrum(path)
    if spec is None:
        raise RuntimeError('espectro vacio')

    freqs = spec['freqs']
    mid_p = spec['mid']
    side_p = spec['side'] if spec['side'] is not None else np.zeros_like(mid_p)
    total_p = mid_p + side_p

    lufs = s['lufs'] if s['lufs'] is not None else ref.integrated_from_spec(spec)
    # Todas las curvas se llevan a -14 LUFS para poder promediarlas entre temas
    offset = (-14.0 - lufs) if lufs is not None else 0.0

    to3 = third_octave(freqs, total_p)
    mid3 = third_octave(freqs, mid_p)
    side3 = third_octave(freqs, side_p)

    with np.errstate(divide='ignore'):
        tercios_db = (10 * np.log10(np.maximum(to3, 1e-30)) + offset).tolist()
        ancho_db = (10 * np.log10(np.maximum(side3, 1e-30))
                    - 10 * np.log10(np.maximum(mid3, 1e-30))).tolist()

    macro = {}
    total_all = band_power(freqs, total_p, 20, 20000)
    for nombre, lo, hi in MACRO:
        p = band_power(freqs, total_p, lo, hi)
        macro[nombre] = {
            'pct': 100 * p / total_all if total_all > 0 else 0.0,
            'db': 10 * np.log10(max(p, 1e-30)) + offset,
        }

    width = ref.stereo_width(spec)
    st = ref.short_term_loudness(spec)

    return {
        'archivo': path.name,
        'duracion_s': s['duration'],
        'rate': s['rate'],
        'formato': s['subtype'],
        'canales': s['channels'],
        'corte_hz': s['cutoff'],
        'lufs': lufs,
        'dr': s['dr'],
        'crest_db': m['crest_db'],
        'true_peak_db': s['true_peak_db'],
        'sample_peak_db': m['sample_peak_db'],
        'clip_runs': s['clip_runs'],
        'correlacion': m['correlation'],
        'bass_loss_db': m['bass_loss_db'],
        'dc_db': m['dc_db'],
        'lra': lra(st, lufs),
        'mono_veredicto': ref.mono_verdict(width),
        'lateral_sobre_central': ref.describe_over_zero(ref.bands_over_zero(width)),
        'avisos': s['warnings'],
        'tercios_db': tercios_db,
        'ancho_db': ancho_db,
        'macro': macro,
    }


if __name__ == '__main__':
    carpeta = Path(sys.argv[1])
    salida = Path(sys.argv[2])
    archivos = sorted(carpeta.glob('*.flac'))
    datos = []
    for i, p in enumerate(archivos, 1):
        try:
            datos.append(one(p))
            print(f'[{i}/{len(archivos)}] ok  {p.name}', flush=True)
        except Exception as e:
            print(f'[{i}/{len(archivos)}] ERROR {p.name}: {e}', flush=True)
    salida.write_text(json.dumps(
        {'centros_tercio': THIRD_OCT.tolist(), 'temas': datos},
        ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'listo: {len(datos)} temas -> {salida}')
