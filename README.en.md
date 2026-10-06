# Spectrum Analyzer Pro

[Español](README.md) · **English**

Inspects audio files and tells whether a FLAC is genuine or comes from a lossy
source. It also measures master quality and compares tonal balance against
reference profiles.

The interface, verdicts and code are in Spanish.

---

## Installation

Requires Python 3.7 or later.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## What it detects

It combines two independent signals to decide whether a file is truly
lossless:

1. **Low-pass cutoff.** Where the spectrum ends. A straight, horizontal edge
   at 16 or 19 kHz is not produced by any natural process: it is the
   fingerprint of a lossy encoder.
2. **Stereo collapse.** If the side channel disappears above a certain
   frequency, the codec used intensity stereo. This covers a blind spot of the
   first signal: HE-AAC with SBR rebuilds synthetic highs and can show a full
   spectrum up to Nyquist.

The verdicts are `LOSSLESS`, `SOSPECHOSO` (suspicious), `TRANSCODE` and
`DUDOSO` (inconclusive).

**The verdicts are not equally strong.** `TRANSCODE` is strong evidence.
`LOSSLESS` only means "nothing found", and a lossy file can get through: AAC
and Opus at high bitrates often skip the low-pass, and LAME with
`--lowpass 22` produces a 320 kbps MP3 with no visible step. Treat it as a
filter that tells you what to look at, not as a final verdict.

## Master quality

Besides the lossless question, it measures things the spectrogram doesn't
show:

| Metric | What it reveals |
|---|---|
| True peak (dBTP) | Clipping on playback, even if no sample reaches full scale |
| Clipping plateaus | A master pushed too hot |
| Dynamic range (DR) | Loudness war; DR5-7 is crushed, DR12+ has room to breathe |
| Real vs declared bit depth | A "24-bit" file that actually holds padded 16-bit audio |
| Fake sample rate | A "96 kHz" file that is upsampled 44.1 kHz |
| Mono bass loss | Inverted phase: the bass cancels on systems that sum to mono |
| Correlation / DC offset | Channels in opposition, recordings with an offset |
| Loudness (LUFS) | How much streaming services will turn it down when normalizing |

## Loudness

The measurement follows ITU-R BS.1770-4, the standard behind EBU R128, with
both gates the standard requires. It is calibrated against the exact values
that can be computed by hand for a sine wave: the error stays within
0.001 dB.

It is meant to be read alongside dynamic range. Spotify and YouTube normalize
to -14 LUFS, Apple Music to -16: a track that measures -9 LUFS will be turned
down 5 dB. At that point the compression added to make it loud no longer
helps; only the damage remains.

The standard filters in the time domain with two biquads. Here the K-filter
is applied to the spectrogram that is already computed, by multiplying each
band by the filter's response. It is equivalent in steady state and avoids
running a recursion over tens of millions of samples that numpy can't
vectorize.

## Duplicates

Finds the same track saved twice in different formats, bitrates or names,
which is exactly where a hash fails because the bytes have nothing in common.

The fingerprint is built by reducing the spectrogram to a normalized grid of
16 bands by 32 time slices. It is limited to 80 Hz–12 kHz on purpose: above
that is exactly where an MP3 cuts, so including it would make the same track
in FLAC and MP3 produce different fingerprints.

Measured on the same master as FLAC, MP3 320 and MP3 128, similarity is 1.00.
Between different tracks by the same artist and the same production, 0.84 at
most. The threshold is 0.93, comfortably between the two.

## Window

```
.venv\Scripts\python.exe spek_gui.py
```

Drag a file or folder onto it, or use the buttons. With a folder it builds a
sortable table; selecting a row draws its spectrogram. The **central /
lateral** (mid / side) selector switches channels: stereo collapse only shows
up in the side channel, because the mid view mixes both and hides it.
**Exportar CSV** dumps the whole table.

## Command line

```
python spectro.py "track.flac"         PNG spectrogram next to the audio
python spectro.py "folder"             recursive
python spectro.py "folder" --scan      verdicts only, no images
python spectro.py "folder" -o "output"
```

## Executable

```
.venv\Scripts\python.exe -m PyInstaller --noconfirm "Analizador de espectro.spec"
```

Produces a standalone `.exe` of about 42 MB in `dist/`, with no Python
required. Files or folders can be dragged onto its icon. Windows SmartScreen
warns the first time because it is unsigned.

---

## Tests

```
python test_spectro.py            fast, with synthetic signals (~1 s)
python test_spectro.py --golden   adds real reference files (~45 s)
```

The `test_regresion_*` cases cover bugs that actually happened and note the
symptom they had, so they don't get deleted for looking trivial.

---

## Structure

| File | Role |
|---|---|
| `spectro_core.py` | Decoding, STFT, detectors, verdict and drawing |
| `spectro_master.py` | Master quality metrics |
| `spectro_loudness.py` | Loudness in LUFS per BS.1770 |
| `spectro_dupes.py` | Acoustic fingerprint and duplicate detection |
| `spectro_batch.py` | Parallel analysis, limited by available memory |
| `spectro_reference.py` | Tonal balance curves and per-band stereo width |
| `spectro_profile.py` | Target profiles built from several references |
| `spectro_balance.py` | Per-band deviation from a profile and EQ suggestions |
| `spectro_match.py` | Bringing a track toward a profile: linear-phase EQ, loudness and limiter |
| `spectro_dsp.py` | FIR filters in numpy, to avoid depending on scipy |
| `ui_theme.py` | Window colors and fonts |
| `spek_gui.py` | Window |
| `spectro.py` | CLI |
| `test_spectro.py` | Tests |
| `referencias/` | Measured reference profiles (Guy J, GMJ) |

### About memory

An eleven-minute track takes hundreds of megabytes for each intermediate
array, so `analyze()` is written to free each one as soon as it is no longer
needed, and the peak ended up around 600 MB. That matters more than it seems:
the number of parallel processes is set by free RAM, not by core count,
because memory is the bottleneck. On a machine with 12 cores and 1.8 GB free,
3 processes fit, not 12.

---

## License

GPL-3.0. See `LICENSE.txt`.
