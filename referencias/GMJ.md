# Perfil de referencia — GMJ (36 temas)

Medido el 2026-09-24 sobre `C:\Users\Fede\Desktop\Descarga Musica\Descargas deemix\GMJ FULL`
con el analizador de espectro de este repo (`spectro_core`, `spectro_master`,
`spectro_loudness`, `spectro_reference`). 44 FLAC, sin errores de lectura; el
perfil se arma con 36 (ver "El corpus").

**Para qué sirve.** Igual que [GUY_J.md](GUY_J.md): es una vara contra la que
comparar una mezcla o master propio. Cada sección dice además en qué se
diferencia GMJ de Guy J, porque las dos referencias se van a usar juntas.

**La conclusión corta.** En balance tonal, GMJ y Guy J son casi el mismo
perfil: ninguna banda del cuerpo difiere más de 2 dB entre medianas. Lo que los
separa es otra cosa: GMJ corta el subgrave más fuerte, tiene el grave más mono,
abre mucho más los medios en estéreo y pone el limitador en −0.3 dBTP casi sin
excepción.

---

## Cómo usar este archivo

1. **Normalizar a −14 LUFS antes de comparar el balance tonal.** Todas las
   tablas de dB por banda están corridas a −14 LUFS integrados, igual que las de
   Guy J, así que se pueden comparar columna contra columna.
2. **Comparar por banda, en dB.** Menos de 2 dB de diferencia en una banda
   marcada como firma está dentro de la variación del propio catálogo.
3. **Mirar primero el desvío.** Bandas con desvío de 1–2 dB son firma; las de
   5–9 dB (20–40 Hz) varían tema a tema y no son regla.
4. **Usarlo con Guy J.** Donde las dos referencias coinciden, es regla del
   género. Donde difieren (sección 4), una mezcla que cae entre las dos está
   dentro del estilo.
5. **Esto es master comercial, no mezcla.** LUFS, pico, DR y cresta son de un
   master terminado. Una mezcla pre-master se compara en balance tonal y estéreo.

---

## El corpus

| | |
|---|---|
| Archivos en la carpeta | 44 |
| **Usados en el perfil** | **36**: temas de GMJ, colaboraciones GMJ & Matter y remixes hechos por GMJ |
| Fuera del perfil | 7 remixes de temas de GMJ hechos por otros productores (sección 6) y 1 duplicado |
| Formato | FLAC PCM 16 bits / 44.1 kHz, estéreo, los 44 |
| Corte espectral | 22.05 kHz en la mayoría, mínimo 20.7 kHz (Valinor) |
| Duración | mediana 7.6 min (p10 7.0 – p90 8.6); Baharat es un edit de 3.2 min |

- `07` y `22` (Jerome Isma-Ae — Baharat, GMJ & Matter Remix) son **el mismo
  archivo byte a byte**. Se cuenta una sola vez; conviene borrar uno.
- Los 7 remixes de otros (Alex O'Rion ×3, Paul Kardos, Paul Angelo & Don
  Argento, Matter) están en `gmj_datos.json` pero no entran en las medianas: son
  el sonido de otro productor sobre material de GMJ.

Ningún corte de transcode: son lossless reales.

---

## 1. Sonoridad y dinámica

| Métrica | Mediana | p10 – p90 | Mín – Máx | Guy J |
|---|---|---|---|---|
| **LUFS integrado** | **−9.1** | −9.9 a −8.4 | −13.3 a −7.7 | −9.1 |
| **DR** | **8.4** | 7.6 a 9.8 | 7.2 a 11.5 | 8.8 |
| **Factor de cresta** | **10.1 dB** | 8.9 a 11.4 | 8.6 a 17.4 | 10.1 dB |
| **Pico real (dBTP)** | **−0.30** | −0.32 a −0.04 | −0.35 a +0.44 | −0.10 |
| Pico de muestra | −0.30 dBFS | −0.30 a −0.08 | −0.39 a 0.00 | −0.20 |
| **LRA** | **3.2 LU** | 2.3 a 5.0 | 1.7 a 14.6 | 3.7 LU |

**Lo que hay que leer acá:**

- **Sonoridad, DR y cresta: iguales a Guy J.** −9.1 LUFS, cresta de 10 dB, DR
  8–9. El mismo punto de master: fuerte para club, con el kick respirando.
- **El techo del limitador está en −0.3 dBTP.** 29 de 36 temas tienen el pico
  de muestra clavado en −0.30 dBFS, y solo 2 pasan 0 dBTP (máximo +0.44, Lost
  on Origin). Guy J pasa 0 dBTP en 32 de 73. Con GMJ como referencia, **un pico
  real arriba de −0.3 dBTP es descuido**. Ojo: 5 de los 7 remixes de otros
  productores también salen en −0.30, así que puede ser el estándar de
  mastering del sello más que una decisión de GMJ.
- **LRA de 3.2 LU,** algo más bajo que Guy J. Solo Valinor pasa 8 LU (14.6): es
  un tema ambiental, sin sub (ver sección 5).
- **3 de 36 tienen clipeo:** Eldarin (121 mesetas), Mood Medicine (97) y Preta
  (12). Los tres con pico de muestra en 0.0 dBFS: son masters distintos del
  resto, no el techo de −0.3.

---

## 2. Balance tonal — tercios de octava a −14 LUFS

Energía total (central + lateral) por banda, en dB, alineada a −14 LUFS.
"Dif." es la mediana de GMJ menos la de Guy J. El desvío es el aproximado a
partir de p10–p90.

| Hz | Mediana | p10 | p90 | Desvío | Guy J | Dif. | |
|---:|---:|---:|---:|---:|---:|---:|---|
| 20 | −64.1 | −70.2 | −55.9 | 5.6 | −57.9 | −6.2 | libre |
| 25 | −59.7 | −66.8 | −43.6 | 9.0 | −51.8 | **−7.9** | libre |
| 31.5 | −47.1 | −55.3 | −35.2 | 7.9 | −41.8 | **−5.3** | libre |
| 40 | −26.7 | −35.9 | −22.2 | 5.3 | −27.2 | +0.5 | transición |
| **50** | **−20.8** | −22.7 | −18.4 | **1.7** | −21.1 | +0.4 | **pico de graves** |
| 63 | −22.8 | −24.3 | −21.2 | 1.2 | −23.3 | +0.5 | firma |
| 80 | −24.6 | −26.4 | −23.0 | 1.3 | −25.4 | +0.7 | firma |
| 100 | −27.2 | −29.7 | −25.5 | 1.6 | −27.3 | +0.1 | firma |
| 125 | −30.2 | −32.1 | −28.5 | 1.4 | −29.6 | −0.6 | firma |
| 160 | −31.8 | −34.6 | −28.6 | 2.3 | −30.1 | −1.7 | firma |
| 200 | −32.3 | −35.3 | −30.2 | 2.0 | −30.5 | −1.8 | firma |
| 250 | −32.4 | −37.1 | −29.6 | 2.9 | −31.7 | −0.7 | firma |
| 315 | −31.6 | −35.8 | −28.7 | 2.8 | −31.1 | −0.5 | firma |
| 400 | −32.1 | −35.2 | −28.6 | 2.6 | −31.7 | −0.4 | firma |
| 500 | −32.6 | −36.2 | −29.8 | 2.5 | −33.2 | +0.7 | firma |
| 630 | −32.4 | −34.5 | −29.9 | 1.8 | −33.0 | +0.6 | firma |
| 800 | −33.4 | −36.1 | −30.6 | 2.2 | −34.5 | +1.1 | firma |
| 1000 | −34.2 | −36.8 | −31.3 | 2.1 | −35.1 | +0.9 | firma |
| 1250 | −35.2 | −37.3 | −32.9 | 1.7 | −35.2 | 0.0 | firma |
| 1600 | −36.6 | −39.0 | −34.1 | 1.9 | −36.5 | −0.1 | firma |
| 2000 | −37.9 | −39.6 | −35.5 | 1.6 | −37.4 | −0.5 | firma |
| 2500 | −38.7 | −40.3 | −37.4 | 1.1 | −38.5 | −0.2 | firma |
| **3150** | **−38.9** | −40.0 | −37.2 | **1.1** | −39.4 | +0.4 | **valle** |
| 4000 | −38.2 | −39.9 | −36.9 | 1.1 | −39.0 | +0.8 | firma |
| 5000 | −37.2 | −39.2 | −35.8 | 1.3 | −37.7 | +0.5 | firma |
| 6300 | −36.1 | −38.0 | −35.4 | 1.0 | −36.7 | +0.6 | repunte |
| 8000 | −36.1 | −37.6 | −34.5 | 1.2 | −36.3 | +0.2 | repunte |
| **10000** | **−36.0** | −37.4 | −34.3 | 1.2 | −36.6 | +0.6 | **meseta de brillo** |
| 12500 | −36.8 | −39.0 | −35.0 | 1.6 | −38.0 | +1.2 | firma |
| 16000 | −41.5 | −44.0 | −38.2 | 2.3 | −43.5 | +2.0 | aire |
| 20000 | −52.7 | −57.6 | −45.0 | 4.9 | −53.2 | +0.6 | libre |

**GMJ es más consistente que Guy J de 2 kHz para arriba.** El desvío entre 2.5
y 10 kHz es de 1.0–1.3 dB (Guy J: 1.8–2.3). Los agudos salen casi idénticos de
tema a tema; es la zona donde menos margen hay para desviarse.

### Reparto de energía por zona

| Zona | Rango | % de la energía | dB @ −14 LUFS | Guy J |
|---|---|---:|---:|---:|
| Sub | 20–60 Hz | **42.3 %** (28.4 – 56.1) | −18.6 | 39.6 % |
| Bajo | 60–120 Hz | **28.7 %** (23.2 – 36.1) | −20.3 | 27.5 % |
| Bajo-medio | 120–400 Hz | 12.1 % (7.1 – 18.1) | −24.0 | 15.2 % |
| Medio | 400 Hz – 2 kHz | 8.8 % (5.2 – 16.5) | −25.5 | 8.5 % |
| Medio-alto | 2–6 kHz | 2.2 % (1.8 – 3.5) | −31.2 | 2.2 % |
| Agudo | 6–12 kHz | 2.3 % (1.7 – 3.4) | −31.3 | 2.1 % |
| Aire | 12–20 kHz | 0.7 % (0.4 – 1.3) | −36.5 | 0.5 % |

**Siete de cada diez partes de la energía están abajo de 120 Hz** (Guy J: dos
tercios). Lo que GMJ tiene de más en el grave lo saca del bajo-medio
(120–400 Hz), no del medio.

### Las cinco firmas del balance tonal

1. **Pico de graves en 50 Hz.** 31 de 36 temas; 3 en 63 Hz y 2 en 40 Hz. Nadie
   arriba de 63 Hz (Guy J tiene algunos en 80 Hz).
2. **Pasa-altos más empinado que Guy J.** Respecto del pico: 40 Hz a −7.6 dB,
   **31.5 Hz a −27.6**, 25 Hz a −38.6, 20 Hz a −43.5. Guy J tiene 31.5 Hz a
   −20.2. Entre 40 y 31.5 Hz GMJ cae 20 dB en un tercio de octava: es un filtro
   de pendiente alta en 35 Hz, no una caída natural. Es la diferencia tonal más
   clara entre los dos.
3. **50 Hz está 13 dB arriba de 1 kHz** (p10 9.8, p90 18.1; Guy J 14.1). Misma
   relación que Guy J dentro del margen.
4. **Bajo-medio un poco más limpio:** 160 y 200 Hz 1.7–1.8 dB por debajo de
   Guy J. Es el único ajuste del cuerpo que se acerca a los 2 dB.
5. **Valle en 3.15 kHz y brillo en 6–10 kHz, igual que Guy J.** 3.15 kHz está
   2.3 dB por debajo de 6.3 kHz; 4 kHz 2.3 dB por debajo de 8 kHz. De 10 a
   16 kHz cae 5.7 dB (Guy J 6.6): un poco más de aire. Pendiente 100 Hz → 10 kHz
   de −1.3 dB/oct contra −1.6 de Guy J medido del mismo modo (ajuste lineal
   sobre los tercios; la guía de Guy J da −1.4 con otro ajuste).

---

## 3. Estéreo — lateral contra central por banda

0 dB: el lateral aporta tanto como el central. Muy negativo: prácticamente mono.

| Hz | Mediana | p10 | p90 | Guy J | |
|---:|---:|---:|---:|---:|---|
| 20 | −15.1 | −22.2 | −9.1 | −18.1 | ruido |
| 25 | −17.8 | −28.8 | −11.8 | −22.3 | ruido |
| 31.5 | −28.2 | −38.2 | −19.9 | −29.0 | |
| 40 | −41.4 | −45.5 | −30.5 | −37.2 | mono |
| **50** | **−44.2** | −46.9 | −31.1 | −39.7 | **mono** |
| 63 | −42.0 | −45.8 | −29.8 | −35.8 | mono |
| 80 | −36.3 | −41.6 | −20.7 | −30.1 | mono |
| 100 | −28.4 | −36.6 | −13.4 | −23.7 | mono |
| 125 | −21.1 | −30.9 | −9.9 | −19.5 | |
| 160 | −13.6 | −23.3 | −6.2 | −13.7 | abre |
| 200 | −8.6 | −13.9 | −2.2 | −9.2 | |
| 250 | −5.2 | −11.8 | −2.1 | −8.1 | |
| 315 | −3.6 | −6.5 | +0.1 | −6.7 | |
| **400** | **−2.1** | −5.1 | −0.1 | −5.6 | **ancho** |
| 500 | −1.9 | −4.1 | +0.2 | −5.0 | ancho |
| 630 | −1.8 | −3.2 | +0.2 | −4.6 | ancho |
| **800** | **−1.4** | −3.4 | +0.2 | −4.2 | **el más ancho** |
| 1000 | −1.5 | −4.1 | 0.0 | −3.9 | ancho |
| 1250 | −1.8 | −4.8 | +0.2 | −4.4 | ancho |
| 1600 | −2.7 | −5.6 | +0.1 | −4.2 | |
| 2000 | −3.2 | −6.0 | −0.3 | −4.5 | |
| 2500 | −3.3 | −6.1 | −1.0 | −4.7 | |
| 3150 | −3.9 | −7.1 | −1.7 | −4.7 | |
| 4000 | −4.5 | −7.3 | −1.9 | −4.8 | |
| 5000 | −5.4 | −8.4 | −1.9 | −4.8 | |
| 6300 | −5.0 | −9.8 | −1.6 | −4.8 | |
| 8000 | −4.2 | −10.2 | −1.4 | −4.5 | |
| 10000 | −4.5 | −11.2 | −0.2 | −4.1 | |
| 12500 | −4.0 | −12.3 | −0.4 | −4.1 | |
| 16000 | −4.4 | −13.0 | −0.6 | −4.4 | |
| 20000 | −3.6 | −12.1 | +0.1 | −4.6 | |

| Métrica | Mediana | p10 – p90 | Guy J |
|---|---|---|---|
| Correlación entre canales | **0.86** | 0.71 – 0.91 | 0.89 |
| Pérdida de graves al sumar a mono | **0.00 dB** | peor caso −1.49 dB (Valinor) | −0.01 dB |
| Veredicto mono | sub centrado en 30 de 36 | 4 algo anchos, 2 muy anchos | 66 de 73 |
| Tramos con lateral sobre central | **6 de 36** | — | ninguno |
| Primera banda con lateral > −12 dB | 200 Hz | — | 200 Hz |

### Las tres firmas del estéreo

1. **Grave más mono que Guy J.** 50 y 63 Hz a −44/−42 dB (Guy J −40/−36),
   100 Hz a −28 (Guy J −24). La apertura arranca en el mismo lugar (200 Hz),
   pero lo de abajo es más punto que en Guy J.
2. **Los medios son muy anchos: es la diferencia más grande con Guy J.** De
   400 Hz a 1.25 kHz el lateral está a −1.5/−2 dB del central, 2.5 a 3.5 dB más
   ancho que Guy J. El p90 toca 0 dB: en uno de cada diez temas el lateral
   iguala al central en esa zona. Es donde viven pads, acordes y arpegios.
3. **Los agudos se quedan en −4/−5 dB, igual que Guy J.** El ancho no crece
   con la frecuencia; al revés, se cierra un poco de 2 kHz para arriba. La forma
   es una panza en los medios, no una rampa.

**El precio de esos medios anchos:** 6 de 36 temas tienen tramos donde el
lateral supera al central (Helioflow 627–803 Hz, Lost on Origin 201–280 Hz,
Eraya 1.6–3.5 kHz, Preta 409–659 Hz, Gauntlet 627 Hz–1.9 kHz, Embers
284 Hz–1.9 kHz). En Guy J no pasa en ninguno. GMJ lo tolera; no conviene
copiarlo.

---

## 4. Diagnóstico con GMJ — qué cambia respecto de Guy J

El procedimiento es el de [GUY_J.md §4](GUY_J.md#4-procedimiento-de-diagnóstico-para-una-mezcla-propia)
(grave → mono → medios → estéreo → master). En casi todo valen los mismos
umbrales. Cambian estos:

| Se observa | Con Guy J | Con GMJ |
|---|---|---|
| 31.5 Hz respecto del pico | pasa-altos si está a menos de 15 dB | pasa-altos si está a menos de **22 dB**; GMJ tiene −27.6 |
| Pico de graves en 80 Hz | aceptable en el límite | ya está afuera: GMJ nunca pasa de 63 Hz |
| 160–200 Hz | referencia relativa | 1.5–2 dB más limpio que Guy J |
| Lateral en 50 Hz | problema arriba de −25 dB | problema arriba de **−30 dB**; GMJ tiene −44 |
| Ancho 400 Hz – 1.25 kHz | meseta de −4 a −5 dB | **−1.5 a −2 dB** es normal |
| Ancho abajo de −5 dB en los medios | normal | mezcla angosta para GMJ |
| Lateral sobre central en algún tramo | nunca pasa | 6 de 36 lo tienen; igual evitarlo |
| Correlación | vive en 0.82–0.94 | vive en **0.71–0.91** |
| Pico real | +1 dBTP es descuido | **arriba de −0.3 dBTP** es descuido |
| 10 kHz → 16 kHz | cae 6.6 dB | cae **5.7 dB** |

Sin cambios, porque las dos referencias coinciden: pico de graves en 50 Hz,
50 Hz − 1 kHz de +13/+14 dB, valle en 3.15 kHz con brillo en 6–10 kHz, agudos
en −4/−5 dB de ancho, −9 LUFS, cresta de 10 dB, DR 8–9.

Si una mezcla cae entre las dos referencias está dentro del estilo. Recién hay
que corregir cuando queda afuera de ambas.

---

## 5. Excepciones documentadas

**Valinor** es otro tipo de tema y rompe casi todo: −13.3 LUFS, DR 11.5,
cresta 17.4 dB, LRA 14.6, 2 % de la energía en el sub, 1 kHz 8 dB **por
encima** de 50 Hz, correlación 0.32 y sub muy ancho (−2 dB, pierde 1.5 dB al
sumar a mono). Es un tema ambiental. No sirve de referencia para un tema de
pista; las medianas del perfil casi no se mueven con él.

**Sub no centrado** (6 de 36):

- `12 - Valinor` — lateral a −2 dB, riesgo real al sumar a mono
- `44 - Earthless` — lateral a −1 dB, riesgo real al sumar a mono
- `07 - Baharat (GMJ & Matter Remix)`, `13 - Metai`, `21 - Metanoia`,
  `32 - Lost on Origin` — algo anchos (−9 a −11 dB)

**Con clipeo** (3 de 36): `35 - Eldarin` (121 mesetas), `43 - Mood Medicine`
(97), `40 - Preta` (12). Los tres con pico de muestra en 0.0 dBFS.

**Pico real arriba de 0 dBTP:** `32 - Lost on Origin` (+0.44).

**Los más fuertes:** `35 - Eldarin` (−7.7, DR 7.9), `02 - Perfect Storm`
(−7.7, DR 7.2), `30 - Mara (GMJ & Matter Main Mix)` (−8.2, DR 7.2).

**Los más dinámicos** (sin contar Valinor): `44 - Earthless` (−10.8, DR 9.8),
`32 - Lost on Origin` (−9.9, DR 9.8).

**Extremos del grave:**
- Más sub: `04 - Feel Inside` (68 % de la energía, 50 Hz − 1 kHz de +21.5),
  `15 - Ebb & Flow` (60 %, +19.0), `08 - Love Sequence` (57 %).
- Menos sub (sin Valinor): `40 - Preta` (28 %, +9.2), `27 - Embers` (28 %),
  `30 - Mara` (+9.1).

**Extremos del aire** (16 kHz respecto de 10 kHz): más oscuros `36 - Eraya`
(−10.9 dB) y `09 - Helioflow` (−9.1); más abiertos `40 - Preta` (+1.4) y
`05 - Telomeres` (−1.0).

---

## 6. Remixes de otros productores (fuera del perfil)

| Tema | LUFS | DR | dBTP | 50 Hz − 1 kHz | Correlación |
|---|---:|---:|---:|---:|---:|
| 23 Shelter of Hearts (Alex O'Rion Remix) | −9.5 | 8.2 | −0.30 | +15.6 | 0.85 |
| 26 Aeons (Paul Angelo & Don Argento Remix) | −9.1 | 8.6 | +0.01 | +16.2 | 0.89 |
| 28 Mood Medicine (Paul Kardos Remix) | −8.2 | 7.4 | **+0.88** | +14.3 | 0.83 |
| 31 Gauntlet (Alex O'Rion Alternative Mix) | −10.0 | 8.6 | −0.30 | +6.6 | 0.74 |
| 33 Rite of Passage (Matter Remix) | −9.5 | 9.1 | −0.31 | +8.9 | 0.78 |
| 38 The Path (Alex O'Rion Remix) | −9.5 | 8.3 | −0.30 | +15.7 | 0.88 |
| 39 Gauntlet (Alex O'Rion Remix) | −10.4 | 9.1 | −0.30 | +7.2 | 0.80 |

- Algo más flojos (−9.5 LUFS de mediana) y con **pasa-altos mucho más suave**:
  31.5 Hz a −17 dB del pico, contra −27.6 de GMJ. Esa es la marca que más
  distingue a GMJ de sus remixers.
- Medios igual de anchos que GMJ (−1.2 dB en 630 Hz – 1.25 kHz).
- **El remix de Paul Kardos tiene 10 244 mesetas de clipeo** y +0.88 dBTP: es
  el archivo más castigado de toda la carpeta.

---

## 7. Qué no dice este perfil

- **No dice nada sobre arreglo, groove ni selección de sonidos.** Un tema puede
  calcar esta curva y no parecerse en nada.
- **No es un objetivo de EQ.** Copiar la curva banda por banda da peor
  resultado que la mezcla original: la curva es consecuencia del arreglo.
- **Es un promedio de temas enteros.** No distingue drop de breakdown.
- **Son masters, no mezclas.** Para una mezcla pre-master: usar balance tonal y
  estéreo, ignorar LUFS, DR, cresta y pico.
- **Incluye colaboraciones con Matter.** 7 de los 36 son GMJ & Matter; el
  perfil es el sonido de GMJ con y sin Matter, no se pueden separar con esta
  muestra.

---

## Reproducir la medición

Los datos por tema están en `referencias/gmj_datos.json` (44 entradas, mismo
formato que `guy_j_datos.json`; incluye el duplicado y los remixes de otros).
Para rehacerlo:

```
.venv/Scripts/python.exe referencias/extraer_perfil.py "<carpeta GMJ FULL>" referencias/gmj_datos.json
```

El perfil para la pestaña de Balance y Match se guardó como `perfiles/GMJ.json`
con los 36 temas del perfil (la carpeta `perfiles/` no se versiona; se
regenera desde la interfaz eligiendo esos archivos).
