# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A spectrum analyzer that decides whether a FLAC is really lossless, measures master quality, and has production tools (tonal balance, target profiles, EQ suggestions, matching a track to a profile). Windows-only in practice.

This repo was split out of `Deemix-Analizador-Espectro` (sibling folder). That repo keeps its own copy of these modules, because its downloader GUI imports `spectro_core` to verify each download. Fixes made here aren't synced there automatically.

The README (in Spanish) explains the detection method, metrics and thresholds in detail. Read it before changing a detector.

## Commands

Use the venv interpreter: `.venv\Scripts\python.exe` (Python 3.7+).

```
.venv\Scripts\python.exe -m pip install -r requirements.txt

.venv\Scripts\python.exe spek_gui.py                                    # window
.venv\Scripts\python.exe spectro.py "<file|folder>" [--scan] [-o out]   # CLI

.venv\Scripts\python.exe test_spectro.py             # fast tests, synthetic signals (~1 s)
.venv\Scripts\python.exe test_spectro.py --golden    # adds real reference files (~45 s)
.venv\Scripts\python.exe test_spectro.py TestLufs    # one class (plain unittest argv)
.venv\Scripts\python.exe test_spectro.py TestLufs.test_<name>   # one test

.venv\Scripts\python.exe -m PyInstaller --noconfirm "Analizador de espectro.spec"   # dist/, ~42 MB
```

Lint config is `.pylintrc` (pylint is not in requirements). The golden tests read hardcoded paths under `C:/Users/ratcl/Music/deemix Music` and skip themselves when those files are missing. If a change moves a golden value, find out why before you update it.

## Architecture

**`spectro_core.analyze(path)` is the hub.** It decodes with soundfile, runs a numpy STFT for the mid channel and the side channel, then calls the other modules on the arrays it already has:
- `spectro_master`: raw-sample metrics first (true peak, clipping, real bit depth, fake sample rate, DR), then spectral metrics (mono bass loss, correlation, DC).
- `spectro_loudness`: BS.1770 LUFS. It applies the K-filter **per band on the existing spectrogram**, not as time-domain biquads, so it never makes another pass over the samples.
- `spectro_dupes`: a 16x32 fingerprint taken from the dB spectrogram, limited to 80 Hz–12 kHz on purpose so MP3 and FLAC copies of the same master match.

It returns a dict (`db`, `side_db`, `freqs`, `times`, `verdict`, `master`, `fingerprint`, ...). `summary()` is the light version without arrays. `draw()` renders onto a matplotlib axis and is shared by the CLI and the GUI.

**Memory is the main constraint.** `analyze()` frees each big array (`del`) as soon as it is no longer needed and converts to dB in place. That keeps the peak near 600 MB on an 11-minute track. When you change it, keep the order of steps and don't keep extra copies alive. `spectro_batch` sets the number of worker processes from free RAM (Windows `GlobalMemoryStatusEx` through ctypes), not from the core count. Workers send back only `summary()`, never the spectrogram.

**No scipy, on purpose.** Dropping it took the exe from ~150 MB to 42 MB, and the `.spec` excludes it. `spectro_dsp` reimplements `firwin2` and `fftconvolve` in numpy, and `TestDsp` checks them against scipy only when scipy happens to be installed. Don't add scipy imports to runtime modules.

**Production chain** (the Produccion / Balance / Match tabs in `spek_gui.py`):
- `spectro_reference`: long-window (32768) averaged tonal curves and per-band stereo width, aligned by loudness rather than by peak.
- `spectro_profile`: builds a target profile from several references (median curve plus P10–P90 tolerance band, or a fixed margin with fewer than 3 files). Profiles are saved as JSON in `perfiles/`, relative to the CWD and gitignored.
- `spectro_balance`: the deviation in 8 named bands, plus EQ suggestions.
- `spectro_match`: a capped linear-phase FIR correction for mid and side separately, then gain to the target LUFS, then a true-peak limit. It writes a new file and never touches the original.

**GUI** is tkinter (with `tkinterdnd2` for drag-and-drop). Background threads push results to a `queue`, and the Tk thread drains it with `root.after`. `main()` calls `multiprocessing.freeze_support()`, which the frozen exe needs for `spectro_batch`. It accepts paths in argv, which is how files dropped on the exe's icon arrive.

**`ui_theme.py`** holds the colors and fonts. Each value is copied from `TicketOnlineFrontend/src/styles/_variables.scss` and annotated with the SCSS variable it comes from.

**`referencias/`** holds one-off reference profiles (Guy J, GMJ). Each has an `.md` write-up and a JSON of the data, extracted with `extraer_perfil.py`. That script is not part of the app.

## Conventions

- Code, identifiers, comments, UI strings and commit messages are in Spanish (rioplatense). Python source avoids accents and `ñ`; Markdown docs use them.
- Module docstrings explain *why*, often with measured numbers (thresholds, memory figures, rejected approaches such as spectral-hole detection). Keep that style, and update the numbers if a change invalidates them.
- Tests named `test_regresion_*` cover real bugs and note the symptom. Don't delete them as trivial.
- `LOSSLESS` means "nothing found". It is not proof. `TRANSCODE` is the strong verdict. Keep that asymmetry in UI wording.
