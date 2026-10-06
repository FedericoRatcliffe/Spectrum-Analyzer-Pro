# Perfil de referencia — Guy J (73 temas)

Medido el 2026-09-22 sobre `C:\Users\ratcl\Music\deemix Music\GUY J FULL` con el
analizador de espectro de este repo (`spectro_core`, `spectro_master`,
`spectro_loudness`, `spectro_reference`). 73 FLAC, sin errores de lectura.

**Para qué sirve.** Es la vara contra la que comparar una mezcla o master propio.
No dice "esto está bien o mal": dice en qué se diferencia un tema de lo que hace
Guy J en 73 lanzamientos, y a partir de ahí se decide qué mover.

---

## Cómo usar este archivo

1. **Normalizar a −14 LUFS antes de comparar el balance tonal.** Todas las tablas
   de dB por banda están corridas a −14 LUFS integrados. Si se compara sin
   normalizar, lo único que se mide es quién está más fuerte, no el balance.
2. **Comparar por banda, en dB, no por forma del gráfico.** Una diferencia de
   menos de 2 dB en una banda del cuerpo (50 Hz – 12.5 kHz) está dentro de la
   variación normal del propio catálogo y no justifica tocar nada.
3. **Mirar primero el desvío de la tabla, después la diferencia.** Las bandas con
   desvío de ~2 dB son firma: ahí Guy J hace siempre lo mismo y desviarse se nota.
   Las de desvío 5–7 dB (20–40 Hz y 16–20 kHz) varían tema a tema y no son regla.
4. **Esto es master comercial, no mezcla.** Los valores de sonoridad, pico y
   rango dinámico corresponden a un master terminado y limitado. Una mezcla
   pre-master no debería parecerse a esto en LUFS ni en pico; sí en balance
   tonal y en estéreo.

---

## El corpus

| | |
|---|---|
| Temas | 73 |
| Formato | FLAC PCM 16 bits / 44.1 kHz, los 73 |
| Corte espectral | 22.05 kHz en la mayoría (mediana), mínimo 19.0 kHz |
| Duración | mediana 8.1 min (rango 5.5 – 10.8) |
| Canales | estéreo, los 73 |

Ningún archivo muestra corte de transcode: el contenido llega al límite de
Nyquist. Son lossless reales.

---

## 1. Sonoridad y dinámica

| Métrica | Mediana | p10 – p90 | Mín – Máx |
|---|---|---|---|
| **LUFS integrado** | **−9.1** | −11.2 a −8.4 | −12.7 a −8.0 |
| **DR** (rango dinámico) | **8.8** | 7.9 a 10.1 | 7.0 a 12.0 |
| **Factor de cresta** | **10.1 dB** | 9.1 a 12.4 | 8.0 a 15.6 |
| **Pico real (dBTP)** | **−0.1** | −0.33 a +1.11 | −0.37 a +2.99 |
| Pico de muestra | −0.2 dBFS | −0.30 a 0.00 | −0.50 a 0.00 |
| **LRA** (rango de sonoridad) | **3.7 LU** | p25 2.8 – p75 5.3 | 1.4 a 17.4 |

**Lo que hay que leer acá:**

- **−9 LUFS es fuerte.** Spotify y YouTube (−14) le van a bajar unos 5 dB; Apple
  Music (−16), 7 dB. Guy J acepta eso: masteriza para club y para que suene
  sólido en el mix de un DJ set, no para ganar la normalización.
- **DR 8–9 con cresta de 10 dB es la combinación clave.** No es un master
  aplastado (eso sería DR 5–6 con cresta de 7), pero tampoco es audiófilo.
  Tiene el limitador puesto y el kick todavía respira.
- **El pico real está clavado en 0 dBTP.** 32 de 73 lo pasan, 10 pasan +1 dBTP.
  No lo cuidan demasiado, pero tampoco lo revientan.
- **LRA de 3.7 LU es bajo y es a propósito.** El tema entra, se establece y se
  mantiene. No hay caídas de 10 dB a la mitad. Los 8 temas con LRA > 8 son los
  que tienen intro larga en silencio o outro que se desarma.
- **4 de 73 tienen clipeo real** (mesetas de muestras al tope), el peor con 1622
  mesetas y +2.2 dBTP. Es decir: aun en el catálogo de referencia hay descuidos.

---

## 2. Balance tonal — tercios de octava a −14 LUFS

Energía total (central + lateral) por banda, en dB, con todas las curvas
alineadas por sonoridad a −14 LUFS.

| Hz | Mediana | p10 | p90 | Desvío | |
|---:|---:|---:|---:|---:|---|
| 20 | −57.9 | −64.9 | −49.3 | 7.0 | libre |
| 25 | −51.8 | −59.5 | −41.4 | 7.5 | libre |
| 31.5 | −41.8 | −49.2 | −30.3 | 7.4 | libre |
| 40 | −27.2 | −35.6 | −22.0 | 5.4 | transición |
| **50** | **−21.1** | −23.3 | −19.0 | **2.0** | **pico de graves** |
| 63 | −23.4 | −26.3 | −21.0 | 2.1 | firma |
| 80 | −25.4 | −28.6 | −23.2 | 2.2 | firma |
| 100 | −27.3 | −29.7 | −25.0 | 2.1 | firma |
| 125 | −29.7 | −31.6 | −26.6 | 2.1 | firma |
| 160 | −30.1 | −32.8 | −26.7 | 2.4 | firma |
| 200 | −30.5 | −34.5 | −27.0 | 2.9 | firma |
| 250 | −31.7 | −34.7 | −28.4 | 2.7 | firma |
| 315 | −31.1 | −34.3 | −28.4 | 2.4 | firma |
| 400 | −31.7 | −35.9 | −28.8 | 3.0 | firma |
| 500 | −33.2 | −36.8 | −29.9 | 2.7 | firma |
| 630 | −33.0 | −35.4 | −30.4 | 2.3 | firma |
| 800 | −34.5 | −36.8 | −30.6 | 2.3 | firma |
| 1000 | −35.1 | −37.9 | −32.3 | 2.4 | firma |
| 1250 | −35.2 | −38.2 | −33.1 | 2.1 | firma |
| 1600 | −36.6 | −39.4 | −34.2 | 2.1 | firma |
| 2000 | −37.4 | −40.4 | −35.2 | 2.0 | firma |
| 2500 | −38.5 | −40.9 | −36.5 | 1.8 | firma |
| **3150** | **−39.4** | −42.0 | −37.5 | **1.8** | **valle** |
| 4000 | −39.0 | −42.1 | −36.7 | 2.2 | firma |
| 5000 | −37.7 | −41.3 | −35.9 | 2.3 | firma |
| 6300 | −36.7 | −40.2 | −34.7 | 2.3 | repunte |
| 8000 | −36.3 | −39.4 | −33.9 | 2.3 | repunte |
| **10000** | **−36.6** | −39.4 | −34.1 | 2.2 | **meseta de brillo** |
| 12500 | −38.0 | −41.6 | −34.9 | 2.6 | firma |
| 16000 | −43.5 | −47.5 | −38.8 | 4.2 | libre |
| 20000 | −53.2 | −61.4 | −46.2 | 6.9 | libre |

### Reparto de energía por zona

| Zona | Rango | % de la energía | dB @ −14 LUFS |
|---|---|---:|---:|
| Sub | 20–60 Hz | **39.6 %** (28.0 – 56.5) | −19.1 |
| Bajo | 60–120 Hz | **27.5 %** (19.8 – 38.2) | −20.7 |
| Bajo-medio | 120–400 Hz | 15.2 % (9.9 – 23.6) | −23.1 |
| Medio | 400 Hz – 2 kHz | 8.5 % (4.6 – 15.6) | −25.7 |
| Medio-alto | 2–6 kHz | 2.2 % (1.3 – 3.4) | −31.6 |
| Agudo | 6–12 kHz | 2.1 % (1.1 – 3.7) | −31.8 |
| Aire | 12–20 kHz | 0.5 % (0.2 – 1.2) | −38.0 |

**Dos tercios de la energía viven abajo de 120 Hz.** No es un error de medición:
es progressive house y la energía está en el bajo. Una mezcla propia con el sub
en 20 % y el medio en 20 % va a sonar flaca y ruidosa al lado de esto, aunque
mida el mismo LUFS.

### Las cinco firmas del balance tonal

1. **El pico de graves está en 50 Hz.** 51 de 73 temas tienen ahí su banda más
   fuerte; 14 en 63 Hz, 4 en 80 Hz, 3 en 40 Hz. Prácticamente nadie abajo de 40.
2. **Pasa-altos alrededor de 35–40 Hz.** Respecto del pico de 50 Hz: 40 Hz está
   −6.1 dB, 31.5 Hz está −20.1 dB, 25 Hz está −31 dB, 20 Hz está −37 dB. La
   caída por debajo de 40 Hz es brutal y deliberada: no hay retumbe inaudible
   comiéndose el limitador.
3. **50 Hz está 14 dB arriba de 1 kHz** (p10 9.6, p90 17.7). Esa relación es el
   número más fácil de chequear en una mezcla propia.
4. **Pendiente global de −1.4 dB por octava** entre 100 Hz y 10 kHz (p10 −2.0,
   p90 −0.8). Más plana que la típica −3 dB/oct del ruido rosa: el catálogo es
   más brillante de lo que sugiere su cantidad de graves.
5. **Valle en 3.15 kHz y repunte de 6 a 10 kHz.** 3.15 kHz está 2.6 dB por
   debajo de 6.3 kHz; 4 kHz está 2.2 dB por debajo de 8 kHz. Deja el rango de
   dureza limpio y pone el brillo arriba, donde no fatiga. De 10 kHz a 16 kHz
   cae 6.6 dB: hay aire pero no es un master con el shelf de 16 k levantado.

---

## 3. Estéreo — lateral contra central por banda

0 dB significa que el lateral aporta tanto como el central; muy negativo,
prácticamente mono.

| Hz | Mediana | p10 | p90 |
|---:|---:|---:|---:|
| 20 | −18.1 | −27.1 | −12.1 |
| 25 | −22.3 | −32.6 | −12.8 |
| 31.5 | −29.0 | −38.7 | −18.4 |
| 40 | −37.2 | −44.1 | −27.6 |
| **50** | **−39.7** | −47.1 | −30.5 |
| 63 | −35.8 | −41.2 | −24.3 |
| 80 | −30.1 | −37.1 | −18.6 |
| 100 | −23.7 | −31.4 | −17.3 |
| 125 | −19.5 | −26.8 | −13.1 |
| 160 | −13.7 | −19.6 | −8.5 |
| **200** | **−9.2** | −13.4 | −5.0 |
| 250 | −8.1 | −11.0 | −3.8 |
| 315 | −6.7 | −9.6 | −2.9 |
| 400 | −5.6 | −9.1 | −2.9 |
| 500 | −5.0 | −7.8 | −2.5 |
| 630 | −4.6 | −7.7 | −2.4 |
| 800 | −4.2 | −6.9 | −1.8 |
| 1000 | −3.9 | −6.6 | −1.7 |
| 1250 | −4.5 | −6.9 | −2.0 |
| 1600 | −4.2 | −6.9 | −1.9 |
| 2000 | −4.5 | −7.0 | −1.5 |
| 2500 | −4.7 | −7.0 | −1.5 |
| 3150 | −4.7 | −7.3 | −1.4 |
| 4000 | −4.8 | −7.8 | −1.8 |
| 5000 | −4.8 | −8.7 | −1.6 |
| 6300 | −4.8 | −9.7 | −1.8 |
| 8000 | −4.5 | −9.7 | −1.3 |
| 10000 | −4.1 | −9.8 | −1.1 |
| 12500 | −4.1 | −9.9 | −1.1 |
| 16000 | −4.4 | −9.6 | +0.4 |
| 20000 | −4.6 | −10.7 | +0.2 |

> Los valores de 20 y 25 Hz (−18, −22) parecen anchos pero no significan nada:
> ahí hay 30–37 dB menos energía que en el pico, y la relación entre dos señales
> casi inexistentes es ruido. La zona que se juzga empieza en 31.5 Hz.

| Métrica | Mediana | p10 – p90 |
|---|---|---|
| Correlación entre canales | **0.89** | 0.82 – 0.94 |
| Pérdida de graves al sumar a mono | **−0.01 dB** | peor caso del catálogo: −0.60 dB |
| Primera banda con lateral > −12 dB | **200 Hz** | 25 Hz – 250 Hz |
| Ancho máximo alcanzado en cualquier banda | −1.3 dB | máximo global +6.0 dB |

### Las tres firmas del estéreo

1. **Mono duro hasta 125 Hz.** En 50 Hz el lateral está 40 dB por debajo del
   central. 66 de 73 temas dan "sub centrado" en el analizador. El bajo es un
   punto, no una nube.
2. **El estéreo abre recién en 200 Hz y se estabiliza en una meseta de −4 a −5 dB
   de 400 Hz para arriba.** No se ensancha más en los agudos: es tan ancho en
   1 kHz como en 10 kHz. Esa meseta plana es lo que hace que no colapse el
   estéreo en agudos ni suene con el hi-hat despegado del resto.
3. **El lateral nunca manda.** En ninguno de los 73 temas hay un tramo relevante
   donde el lateral supere al central. La pérdida al sumar a mono es de una
   centésima de dB: estos temas suenan igual en un sistema de club que suma el
   bajo a mono.

---

## 4. Procedimiento de diagnóstico para una mezcla propia

Dado un tema del usuario, seguir este orden. Los primeros puntos son los que más
cambian la percepción; los últimos son afinado.

### Paso 0 — medir
Correr el analizador sobre el archivo y anotar: LUFS, DR, cresta, pico real,
LRA, la curva de tercios de octava normalizada a −14 LUFS y la curva de ancho.

### Paso 1 — el eje grave (lo que más pesa)

| Se observa | Recomendación |
|---|---|
| Pico de graves arriba de 80 Hz | El bajo está en el bajo-medio, no en el sub. Guy J pone el peso en 50 Hz. Revisar la afinación del sub o si el kick manda solo armónicos. |
| Pico de graves abajo de 40 Hz | Energía inaudible que gasta headroom. Pasa-altos en 30–35 Hz. |
| 31.5 Hz a menos de 15 dB por debajo del pico | Retumbe. La referencia lo tiene 20 dB abajo. Bajar con pasa-altos, se recupera headroom para el limitador. |
| Relación 50 Hz − 1 kHz menor a 10 dB | Falta cuerpo. La referencia está en +14 dB. Es la causa más común de "mi tema suena chico al lado del de él". |
| Relación 50 Hz − 1 kHz mayor a 18 dB | Sobra grave: el limitador va a bombear y los medios van a desaparecer al bajarlo. |
| Sub (20–60 Hz) por debajo del 25 % de la energía | El bajo no está sosteniendo el tema. La referencia está en 40 %. |

### Paso 2 — mono y fase del grave

| Se observa | Recomendación |
|---|---|
| Lateral en 50 Hz arriba de −25 dB | El sub está ancho. Pasar a mono todo lo de abajo de 120 Hz. La referencia tiene −40 dB. |
| Pérdida al sumar a mono peor que −1 dB | Hay cancelación real: en club se pierde el cuerpo. Revisar capas de bajo desfasadas o un ensanchador puesto sobre el bus entero. |
| Correlación abajo de 0.7 | Demasiado ancho para el género. El catálogo vive en 0.82–0.94. |
| Alguna banda con lateral arriba del central | Nunca pasa en los 73 temas. Es un ensanchador excedido: bajarlo. |

### Paso 3 — el medio y el equilibrio general

| Se observa | Recomendación |
|---|---|
| Pendiente 100 Hz→10 kHz más pronunciada que −2.5 dB/oct | Suena apagado. La referencia está en −1.4. |
| Pendiente más plana que −0.5 dB/oct | Suena delgado o agresivo. |
| 200–400 Hz por encima de la referencia relativa | Barro en el bajo-medio, el clásico. |
| 3–4 kHz por encima de 6–8 kHz | Al revés que la referencia. Ahí vive la dureza y la fatiga; Guy J deja un valle de 2.5 dB. Bajar 3.15 kHz antes que subir agudos. |
| 6–10 kHz más de 3 dB por debajo de la referencia | Falta brillo, pero el brillo va en 6–10 k, no en 16 k. |
| 16 kHz a menos de 4 dB por debajo de 10 kHz | Más aire que la referencia. No es un error, pero delata un shelf de aire que en club no se escucha y en el limitador sí. |

### Paso 4 — estéreo de medios y agudos

| Se observa | Recomendación |
|---|---|
| Ancho que crece con la frecuencia (−8 dB en 1 k, −1 dB en 10 k) | Estéreo desparejo: los agudos se despegan. La referencia mantiene una meseta plana de −4 a −5 dB. |
| Ancho por debajo de −8 dB de 400 Hz para arriba | Mezcla angosta. Falta información lateral en pads y percusión. |
| Ancho arriba de −2 dB de forma sostenida | Más ancho que cualquiera de los 73. Riesgo de que se desarme en mono. |

### Paso 5 — master

| Se observa | Recomendación |
|---|---|
| DR menor a 7 | Master aplastado. La referencia está en 8–9 y no pierde fuerza. |
| DR mayor a 12 con LUFS arriba de −10 | Números incoherentes: revisar la medición. |
| Cresta menor a 8 dB | El limitador se comió los transitorios. La referencia está en 10 dB. |
| Pico real arriba de +1 dBTP | Va a distorsionar en conversores y en codificación con pérdida. 10 de 73 lo pasan, pero es descuido, no criterio. |
| LUFS más fuerte que −8 | Más fuerte que el tema más fuerte del catálogo. No hay nada que ganar: el streaming lo baja igual y solo queda el daño. |
| LUFS más flojo que −12 | Más flojo que 70 de 73. En un set de DJ va a quedar atrás. |
| LRA mayor a 8 LU | Más dinámico que el catálogo. Puede estar bien si hay intro larga; revisar que no sea un arreglo que se cae a la mitad. |
| Clipeo (mesetas de muestras al tope) | Corregir siempre. 4 de 73 lo tienen, pero es un defecto, no un estilo. |

### Paso 6 — cómo redactar la devolución

- Ordenar por impacto: grave → mono → medios → estéreo → master. Nunca arrancar
  por el aire de 16 kHz.
- Dar el número medido, el de referencia y la diferencia. "Tenés 50 Hz a −27 dB,
  la referencia está en −21, te faltan 6 dB de cuerpo" es accionable; "le falta
  grave" no.
- Ignorar diferencias menores a 2 dB en las bandas marcadas como firma, y
  menores a 5 dB en las marcadas como libres (20–40 Hz, 16–20 kHz).
- Decir explícitamente cuando algo está bien. Si el eje grave y el mono están en
  rango, decirlo antes de pasar a lo demás.

---

## 5. Excepciones documentadas

Estos temas rompen alguna regla del propio catálogo. Sirven para no tratar las
medianas como ley.

**Sub no centrado** (7 de 73):

- `14 - Release Me` — lateral a −0 dB en el sub, riesgo real al sumar a mono
- `52 - Need To Feel Loved (Guy J Remix Mixed)` — lateral a −1 dB
- `64 - Ligod` — lateral a −3 dB
- `07 - Million Years from Now`, `12 - I Lost My Head (PM Mix)`,
  `13 - Once In A Blue Moon`, `71 - Easy As Can Be` — algo anchos (−8 a −12 dB)

**Con clipeo** (4 de 73):

- `64 - Ligod` — 1622 mesetas, +2.2 dBTP
- `27 - Airborne` — 1319 mesetas, +1.5 dBTP
- `11 - Synthopia` — 177 mesetas, +1.1 dBTP
- `08 - Candyland` — 34 mesetas, +0.3 dBTP

**Los más dinámicos** (LUFS más flojos, DR más alto): `12 - I Lost My Head
(PM Mix)` (−12.7, DR 9.5), `66 - Dizzy Moments (Am Mix)` (−12.6, DR 11.5),
`64 - Ligod` (−12.2, DR 11.2).

**Los más fuertes:** `37 - Modulator` (−8.0), `45 - Cicada` (−8.0, DR 8.0),
`46 - Worlds Apart` (−8.1).

---

## 6. Qué no dice este perfil

- **No dice nada sobre arreglo, groove ni selección de sonidos.** Un tema puede
  calcar esta curva y no parecerse en nada.
- **No es un objetivo de EQ.** Ecualizar una mezcla hasta que coincida banda por
  banda con la mediana da un resultado peor que la mezcla original: la curva es
  el resultado de decisiones de arreglo, no su causa.
- **Es un promedio de temas enteros.** No distingue el drop del breakdown. Un
  tema con un breakdown largo sin bajo va a medir menos sub que la mediana sin
  que eso sea un defecto.
- **Son masters, no mezclas.** Para una mezcla pre-master: usar el balance tonal
  y el estéreo, ignorar LUFS, DR, cresta y pico.
- **Un solo artista.** Es el sonido de Guy J, no el del progressive house en
  general.

---

## Reproducir la medición

Los datos por tema están en `referencias/guy_j_datos.json` (73 entradas con
métricas de master, tercios de octava y ancho por banda). Para rehacerlo:

```
.venv/Scripts/python.exe spectro.py --help     # análisis desde la consola
python spek_gui.py                             # interfaz del analizador
```

Módulos usados: `spectro_core.analyze` (espectrograma, corte, métricas de
master), `spectro_loudness.integrated_lufs` (BS.1770-4),
`spectro_reference.average_spectrum` (espectro promedio con ventanas de 32768,
1.35 Hz por banda) y `spectro_reference.stereo_width`.
