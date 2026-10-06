# Spectrum Analyzer Pro

Inspecciona archivos de audio y dice si un FLAC es genuino o viene de una
fuente con pérdida, además de medir la calidad del máster y comparar el
balance tonal contra perfiles de referencia.

---

## Instalación

Hace falta Python 3.7 o superior.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Qué detecta

Cruza dos señales independientes para decidir si un archivo es lossless de
verdad:

1. **Corte pasa-bajos.** Dónde termina el espectro. Un borde recto y horizontal
   a 16 o 19 kHz no lo produce ningún proceso natural: es la huella de un
   encoder con pérdida.
2. **Colapso del estéreo.** Si el canal lateral desaparece por encima de cierta
   frecuencia, el codec usó estéreo por intensidad. Esto cubre un punto ciego
   de la señal anterior: HE-AAC con SBR reconstruye agudos sintéticos y puede
   mostrar un espectro completo hasta Nyquist.

Los veredictos son `LOSSLESS`, `SOSPECHOSO`, `TRANSCODE` y `DUDOSO`.

**Los dos veredictos no valen lo mismo.** `TRANSCODE` es evidencia fuerte.
`LOSSLESS` solo significa "no encontré nada", y hay formas de que un archivo
con pérdida pase: AAC y Opus a bitrate alto muchas veces no aplican pasa-bajos,
y LAME con `--lowpass 22` produce un MP3 320 sin escalón visible. Conviene
tratarlo como un filtro que indica qué mirar, no como un veredicto final.

## Calidad del máster

Aparte de la cuestión lossless, mide cosas que el espectrograma no muestra:

| Métrica | Qué delata |
|---|---|
| Pico real (dBTP) | Saturación al reproducir, aunque ninguna muestra llegue al tope |
| Mesetas de clipeo | Máster pasado de nivel |
| Rango dinámico (DR) | Guerra del volumen; DR5-7 es aplastado, DR12+ tiene aire |
| Bits reales vs declarados | Un "24 bits" que en realidad guarda 16 rellenado |
| Sample rate falso | Un "96 kHz" que es un 44.1 estirado |
| Graves a mono | Fase invertida: los graves se cancelan en sistemas que suman a mono |
| Correlación / continua | Canales en oposición, grabación con offset |
| Sonoridad (LUFS) | Cuánto va a bajarlo el streaming al normalizar |

## Sonoridad

La medición sigue ITU-R BS.1770-4, el estándar de EBU R128, con las dos
compuertas que pide la norma. Calibrada contra los valores exactos que se
pueden calcular a mano para una senoidal: el error queda en 0.001 dB.

Sirve para leer un máster junto al rango dinámico. Spotify y YouTube normalizan
a -14 LUFS, Apple Music a -16: un tema que mide -9 LUFS lo van a bajar 5 dB, y
ahí la compresión que le metieron para que sonara fuerte no le sirve de nada,
solo le queda el daño.

La norma filtra en el dominio del tiempo con dos biquads. Acá el filtro K se
aplica sobre el espectrograma que ya está calculado, multiplicando cada banda
por la respuesta del filtro. Es equivalente en régimen permanente y evita
recorrer decenas de millones de muestras con una recursión que numpy no puede
vectorizar.

## Repetidos

Encuentra el mismo tema guardado dos veces con distinto formato, bitrate o
nombre, que es donde un hash no sirve porque los bytes no coinciden en nada.

La huella se arma reduciendo el espectrograma a una grilla de 16 bandas por 32
tramos de la duración, normalizada. Se queda entre 80 Hz y 12 kHz a propósito:
arriba de eso es justo donde un MP3 recorta, así que incluirlo haría que el
mismo tema en FLAC y en MP3 dieran huellas distintas.

Medido sobre el mismo máster en FLAC, MP3 320 y MP3 128, la similitud da 1.00.
Entre temas distintos del mismo artista y la misma producción, 0.84 como
máximo. El umbral está en 0.93, cómodo entre los dos.

## Ventana

```
.venv\Scripts\python.exe spek_gui.py
```

Se le puede arrastrar un archivo o una carpeta encima, o usar los botones.
Con una carpeta arma una tabla ordenable; al elegir una fila dibuja su
espectrograma. El selector **central / lateral** cambia de canal: el colapso de
estéreo solo se ve en el lateral, porque la vista central mezcla los dos y lo
oculta. **Exportar CSV** vuelca la tabla entera.

## Línea de comandos

```
python spectro.py "tema.flac"          espectrograma en PNG junto al audio
python spectro.py "carpeta"            recursivo
python spectro.py "carpeta" --scan     solo veredictos, sin imágenes
python spectro.py "carpeta" -o "salida"
```

## Ejecutable

```
.venv\Scripts\python.exe -m PyInstaller --noconfirm "Analizador de espectro.spec"
```

Deja un `.exe` autónomo de unos 42 MB en `dist/`, sin necesidad de Python. Se
le pueden arrastrar archivos o carpetas sobre el ícono. Windows SmartScreen
avisa la primera vez porque no está firmado.

---

## Tests

```
python test_spectro.py            rápidos, con señales sintéticas (~1 s)
python test_spectro.py --golden   agrega archivos reales de referencia (~45 s)
```

Los casos `test_regresion_*` cubren bugs que ocurrieron de verdad y llevan
anotado el síntoma que tenían, para que no se borren por parecer triviales.

---

## Estructura

| Archivo | Rol |
|---|---|
| `spectro_core.py` | Decodificación, STFT, detectores, veredicto y dibujado |
| `spectro_master.py` | Métricas de calidad del máster |
| `spectro_loudness.py` | Sonoridad en LUFS según BS.1770 |
| `spectro_dupes.py` | Huella acústica y detección de repetidos |
| `spectro_batch.py` | Análisis en paralelo, limitado por memoria disponible |
| `spectro_reference.py` | Curvas de balance tonal y ancho estéreo por banda |
| `spectro_profile.py` | Perfiles objetivo a partir de varias referencias |
| `spectro_balance.py` | Desvío por bandas contra un perfil y sugerencias de EQ |
| `spectro_match.py` | Acercar un tema a un perfil: EQ de fase lineal, sonoridad y limitador |
| `spectro_dsp.py` | Filtros FIR en numpy, para no depender de scipy |
| `ui_theme.py` | Colores y fuentes de la ventana |
| `spek_gui.py` | Ventana |
| `spectro.py` | CLI |
| `test_spectro.py` | Tests |
| `referencias/` | Perfiles de referencia medidos (Guy J, GMJ) |

### Sobre la memoria

Un tema de once minutos ocupa cientos de megabytes por cada arreglo intermedio,
así que `analyze()` está escrito para liberar cada uno apenas deja de hacer
falta y el pico quedó en unos 600 MB. Eso importa más de lo que parece: la
cantidad de procesos en paralelo la decide la RAM libre y no la cantidad de
núcleos, porque el cuello de botella es la memoria. En una máquina con 12
núcleos y 1.8 GB libres entran 3 procesos, no 12.

---

## Licencia

GPL-3.0. Ver `LICENSE.txt`.
