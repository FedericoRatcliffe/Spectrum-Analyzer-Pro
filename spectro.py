#!/usr/bin/env python3
"""Analizador de espectro por linea de comandos, con deteccion de transcodes.

Uso:
    python spectro.py "tema.flac"              # espectrograma de un archivo
    python spectro.py "C:/carpeta"             # escanea una carpeta (recursivo)
    python spectro.py "carpeta" --scan         # solo veredictos, sin imagenes
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import spectro_core as core
import spectro_dupes


def render(path, result, out_path):
    """Dibuja el espectrograma y lo guarda como PNG."""
    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=110)
    fig.patch.set_facecolor(core.CHART_BG)
    tope = core.draw(ax, result, path.name)

    fig.colorbar(
        plt.cm.ScalarMappable(cmap=core.SPEK_CMAP,
                              norm=plt.Normalize(core.DB_FLOOR, tope)),
        ax=ax, label='dBFS', pad=0.01,
    ).ax.tick_params(colors=core.CHART_DIM, labelsize=8)

    fig.tight_layout()
    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description='Analizador de espectro y detector de transcodes.')
    parser.add_argument('target', help='Archivo de audio o carpeta a analizar')
    parser.add_argument('--scan', action='store_true', help='Solo veredictos, sin generar imagenes')
    parser.add_argument('-o', '--out', help='Carpeta donde dejar los PNG (por defecto, junto al audio)')
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f'No existe: {target}')
        return 1

    if target.is_file():
        files = [target]
    else:
        files = sorted(p for p in target.rglob('*') if p.suffix.lower() in core.AUDIO_EXTS)

    if not files:
        print(f'No se encontro audio en {target}')
        return 1

    out_dir = Path(args.out) if args.out else None
    counts = {}
    resumenes = []

    for path in files:
        try:
            result = core.analyze(path)
        except Exception as e:  # pylint: disable=broad-except
            print(f'  ERROR      {path.name}: {e}')
            counts['ERROR'] = counts.get('ERROR', 0) + 1
            continue

        verdict = result['verdict']
        counts[verdict] = counts.get(verdict, 0) + 1
        resumenes.append(core.summary(result, path))
        print(f'  {verdict:<11}{path.name}')
        m = result['master']
        bits = f"{m['real_bits']} bit" if m['real_bits'] else result['subtype']
        dr = f" | DR{m['dr']:.0f}" if m['dr'] is not None else ''
        if m['lufs'] is not None:
            dr += f" | {m['lufs']:.1f} LUFS"
        print(f"             {result['detail']} | {result['rate']} Hz | {bits}{dr}"
              f" | pico real {m['true_peak_db']:+.1f} dBTP")
        for signal in result['signals'] + m['warnings']:
            print(f'             mas: {signal}')

        if not args.scan:
            target_dir = out_dir or path.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            png = target_dir / f'{path.stem}.spectro.png'
            render(path, result, png)
            print(f'             {png}')

    if len(files) > 1:
        print('\nResumen: ' + ', '.join(f'{v} {k}' for k, v in sorted(counts.items())))
        grupos = spectro_dupes.find_duplicates(resumenes)
        if grupos:
            print(f'\n{spectro_dupes.describe(grupos, resumenes)}:')
            for numero, grupo in enumerate(grupos, start=1):
                print(f'  #{numero}')
                for i in grupo:
                    print(f'       {resumenes[i]["name"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
