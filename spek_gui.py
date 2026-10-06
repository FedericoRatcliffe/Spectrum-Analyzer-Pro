#!/usr/bin/env python3
"""Analizador de espectro con ventana propia, al estilo de Spek.

Acepta un archivo arrastrado sobre el icono del .exe, soltado dentro de la
ventana, o abierto con el boton. Soltando una carpeta analiza todo su contenido
y arma una tabla ordenable; al elegir una fila se dibuja su espectrograma.

El analisis corre en un hilo aparte para que la ventana no se congele. De los
resultados completos solo se conservan unos pocos en memoria, porque cada
espectrograma pesa decenas de megabytes; de los demas queda el resumen, que es
lo unico que la tabla necesita.
"""
import csv
import multiprocessing
import queue
import sys
import threading
import tkinter as tk
from collections import OrderedDict
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.figure import Figure

import spectro_balance
import spectro_batch
import spectro_core as core
import spectro_dupes
import spectro_match
import spectro_profile
import spectro_reference
import ui_theme
from ui_theme import (ACCENT, BG, BLUE, BLUE_DIM, BLUE_SOFT, BORDER, DIM, FG,
                      PANEL, PANEL_ALT, fuente, px)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

FULL_CACHE_SIZE = 6   # espectrogramas guardados: 6 x 49 MB, para no recalcular al hacer clic

# Los anchos suman 494, menos que los 520 del panel, para que al abrir no haya
# desplazamiento horizontal y ninguna columna nazca fuera de vista. 'Avisos'
# se estira para ocupar lo que sobre; la barra horizontal queda para cuando el
# usuario angosta el panel.
COLUMNS = [
    ('verdict', 'Veredicto', 88),
    ('name', 'Archivo', 150),
    ('cutoff', 'Corte', 52),
    ('dr', 'DR', 36),
    ('lufs', 'LUFS', 50),
    ('peak', 'Pico', 48),
    ('flags', 'Avisos', 120),
]


class BarraGrafico(NavigationToolbar2Tk):
    """La barra de matplotlib sin atras/adelante ni el dialogo de margenes.

    En Windows un boton de imagen deshabilitado se pinta tramado, y atras y
    adelante nacen deshabilitados: eran dos manchas grises en una franja
    oscura. Con inicio, paneo y zoom alcanza, y los margenes ya los maneja el
    layout 'tight'.
    """
    toolitems = [t for t in NavigationToolbar2Tk.toolitems
                 if t[0] in ('Home', 'Pan', 'Zoom', 'Save')]


class SpectroApp:
    def __init__(self, root):
        self.root = root
        self.queue = queue.Queue()
        self.summaries = {}                 # iid del arbol -> resumen
        self.full_cache = OrderedDict()     # ruta -> resultado completo
        self.current = None
        self.result = None
        self.channel = tk.StringVar(value='mid')
        self.yscale = tk.StringVar(value='linear')
        self.sort_key = None
        self.sort_desc = False
        self.pending = 0
        self.total = 0
        self.done = 0
        self.workers = 1
        self.errors = []
        self.perfil = None       # perfil objetivo contra el que se compara
        self.espectros = {}      # ruta -> espectro promedio ya calculado
        self.canal_balance = tk.StringVar(value='mid')
        self.filas_balance, self.sugerencias_eq = [], []
        self.eje_tiempo = tk.StringVar(value='pct')
        self.ref_en_tiempo = tk.BooleanVar(value=True)
        # Match: la cantidad arranca a la mitad porque corregir del todo copia
        # tambien lo que el perfil tiene de particular
        self.match_amount = tk.DoubleVar(value=50.0)
        self.match_taps = tk.StringVar(value=str(spectro_match.TAPS))
        self.match_sub_mono = tk.BooleanVar(value=True)
        self.match_sub_hz = tk.StringVar(value=f'{spectro_match.SUB_MONO_HZ:.0f}')
        self.match_lufs = tk.StringVar(value='')
        self.match_trabajando = False

        root.title('Analizador de espectro')
        # A 150% el tamano de diseno no entra en una pantalla de 1080: se acota
        ancho = min(px(1320), int(root.winfo_screenwidth() * 0.92))
        alto = min(px(760), int(root.winfo_screenheight() * 0.86))
        x = (root.winfo_screenwidth() - ancho) // 2
        y = max(0, (root.winfo_screenheight() - alto) // 2 - px(24))
        root.geometry(f'{ancho}x{alto}+{x}+{y}')
        root.configure(bg=BG)
        self._style()

        self._build_toolbar()
        self._build_body()

        if HAS_DND:
            root.drop_target_register(DND_FILES)
            root.dnd_bind('<<Drop>>', self.on_drop)

        self.root.after(80, self.drain_queue)

    # --- construccion de la interfaz -----------------------------------------

    def _style(self):
        ui_theme.estilo_tabla(ttk.Style(), rowheight=26)

    def _button(self, parent, text, command, state='normal'):
        boton = ui_theme.boton(parent, text, command)
        boton.config(state=state)
        return boton

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill='x', padx=10, pady=(10, 6))

        self._button(bar, 'Abrir archivo...', self.pick_file).pack(side='left')
        self._button(bar, 'Abrir carpeta...', self.pick_folder).pack(side='left', padx=(6, 0))
        self.save_btn = self._button(bar, 'Guardar PNG', self.save_png, 'disabled')
        self.save_btn.pack(side='left', padx=(6, 0))
        self.csv_btn = self._button(bar, 'Exportar CSV', self.export_csv, 'disabled')
        self.csv_btn.pack(side='left', padx=(6, 0))

        chan = tk.Frame(bar, bg=BG)
        chan.pack(side='left', padx=(16, 0))
        tk.Label(chan, text='Canal:', bg=BG, fg=DIM, font=fuente(9)).pack(side='left')
        for value, label in (('mid', 'central'), ('side', 'lateral')):
            ttk.Radiobutton(chan, text=label, value=value, variable=self.channel,
                            command=self.redraw, style='Barra.TRadiobutton'
                            ).pack(side='left', padx=(6, 0))

        eje = tk.Frame(bar, bg=BG)
        eje.pack(side='left', padx=(16, 0))
        tk.Label(eje, text='Eje:', bg=BG, fg=DIM, font=fuente(9)).pack(side='left')
        for value, label in (('linear', 'lineal'), ('log', 'log')):
            ttk.Radiobutton(eje, text=label, value=value, variable=self.yscale,
                            command=self.redraw, style='Barra.TRadiobutton'
                            ).pack(side='left', padx=(6, 0))

        self.progress = ttk.Progressbar(bar, mode='indeterminate', length=px(130))

        self.status = tk.Label(
            self.root, text='Arrastra un archivo o una carpeta a esta ventana',
            bg=BG, fg=DIM, anchor='w', font=fuente(9),
        )
        self.status.pack(fill='x', padx=12, pady=(0, 6))

    def _build_body(self):
        paned = tk.PanedWindow(self.root, orient='horizontal', bg=BG,
                               sashwidth=px(8), bd=0, sashrelief='flat')
        paned.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        left_borde = tk.Frame(paned, bg=BORDER)
        left = tk.Frame(left_borde, bg=PANEL)
        left.pack(fill='both', expand=True, padx=1, pady=1)
        self.tree = ttk.Treeview(
            left, columns=[c[0] for c in COLUMNS], show='headings', selectmode='browse')
        for key, label, width in COLUMNS:
            self.tree.heading(key, text=label, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=px(width), minwidth=px(36), anchor='w',
                             stretch=(key == 'flags'))
        vbar = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        hbar = ttk.Scrollbar(left, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        # grid en vez de pack: con dos barras, pack deja una pisando la esquina
        self.tree.grid(row=0, column=0, sticky='nsew')
        vbar.grid(row=0, column=1, sticky='ns')
        hbar.grid(row=1, column=0, sticky='ew')
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        for verdict, color in core.VERDICT_COLORS.items():
            self.tree.tag_configure(verdict, foreground=color)
        paned.add(left_borde, width=px(520), minsize=px(260))

        right_borde = tk.Frame(paned, bg=BORDER)
        cuaderno = ttk.Notebook(right_borde)
        cuaderno.pack(fill='both', expand=True, padx=1, pady=1)
        cuaderno.bind('<<NotebookTabChanged>>', self._cambio_pestana)
        self.cuaderno = cuaderno

        right = tk.Frame(cuaderno, bg=PANEL)
        cuaderno.add(right, text='Verificacion')
        self.fig = Figure(figsize=(8, 5), dpi=100, facecolor=PANEL)
        # El motor de layout se fija una vez y se aplica en cada dibujado,
        # tambien al redimensionar la ventana. Llamar a tight_layout() a mano
        # solo lo corregia al cambiar de archivo, y el eje inferior quedaba
        # cortado despues de mover el divisor.
        self.fig.set_layout_engine('tight')
        self.ax = self.fig.add_subplot(111)
        self.add_colorbar()
        self.reset_axes()
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)

        nav = self._barra_grafico(self.canvas, right)
        # La barra se empaqueta antes que el lienzo: si va despues, el lienzo
        # con expand=True le come el espacio y queda fuera de la ventana
        nav.pack(side='bottom', fill='x')
        self.canvas.get_tk_widget().pack(side='top', fill='both', expand=True)
        self._build_produccion(cuaderno)
        self._build_balance(cuaderno)
        self._build_match(cuaderno)
        paned.add(right_borde, minsize=px(420))

    @staticmethod
    def _barra_grafico(canvas, padre):
        """Barra de zoom y paneo de matplotlib, en oscuro como el resto.

        Los iconos son trazo negro, pero matplotlib (3.6+) los recolorea con el
        color de texto del boton cuando el fondo es oscuro. Lo decide al crear
        el boton, asi que despues de cambiar los colores hay que pedirle que
        vuelva a armar cada imagen. Antes la franja iba clara para que se
        vieran, y era la parte mas fuera de lugar de la ventana.
        """
        nav = BarraGrafico(canvas, padre, pack_toolbar=False)
        nav.configure(bg=PANEL, bd=0, height=px(36))
        for child in nav.winfo_children():
            opciones = dict(bg=PANEL, fg=DIM, activebackground=ACCENT,
                            activeforeground=FG, highlightbackground=PANEL,
                            selectcolor=BLUE_DIM, relief='flat', overrelief='flat',
                            bd=0)
            for clave, valor in opciones.items():
                try:
                    child.configure(**{clave: valor})
                except tk.TclError:
                    pass
        for boton in getattr(nav, '_buttons', {}).values():
            try:
                nav._set_image_for_button(boton)   # pylint: disable=protected-access
            except (AttributeError, tk.TclError):
                pass
        nav.update()
        return nav

    def _build_produccion(self, cuaderno):
        """Pestana de referencia: balance tonal y ancho estereo por banda.

        No da veredictos. Responde en que se diferencia el tema abierto del que
        se cargue como referencia, que es una comparacion que interpreta quien
        mezcla.
        """
        hoja = tk.Frame(cuaderno, bg=PANEL)
        cuaderno.add(hoja, text='Produccion')

        barra = tk.Frame(hoja, bg=PANEL)
        barra.pack(fill='x', padx=10, pady=(10, 4))
        ui_theme.boton(barra, 'Crear perfil...', self.crear_perfil,
                       principal=True).pack(side='left')
        ui_theme.boton(barra, 'Cargar perfil...',
                       self.cargar_perfil).pack(side='left', padx=(8, 0))
        ui_theme.boton(barra, 'Una referencia...',
                       self.pick_reference).pack(side='left', padx=(8, 0))
        self.ref_btn_quitar = ui_theme.boton(barra, 'Quitar', self.clear_reference)
        self.ref_btn_quitar.pack(side='left', padx=(8, 0))
        self.ref_btn_quitar.config(state='disabled')
        self.ref_label = tk.Label(hoja, text='sin perfil', bg=PANEL, fg=DIM,
                                  anchor='w', font=fuente(9))
        self.ref_label.pack(fill='x', padx=12, pady=(2, 0))

        # Segunda fila: en una sola, con la ruta de la referencia expandiendose,
        # estos controles quedaban cortados contra el borde
        fila = tk.Frame(hoja, bg=PANEL)
        fila.pack(fill='x', padx=10, pady=(0, 4))

        # Los temas rara vez duran lo mismo, asi que superponer sus curvas por
        # segundos desalinea las secciones. En porcentaje quedan comparables
        # sin tener que calzar nada a mano.
        tk.Label(fila, text='Guardados:', bg=PANEL, fg=DIM,
                 font=fuente(9)).pack(side='left')
        self.combo_perfiles = ttk.Combobox(fila, state='readonly', width=22,
                                           font=fuente(9))
        self.combo_perfiles.pack(side='left', padx=(6, 0))
        self.combo_perfiles.bind('<<ComboboxSelected>>', self._elegir_del_combo)

        tk.Label(fila, text='Tiempo:', bg=PANEL, fg=DIM,
                 font=fuente(9)).pack(side='left', padx=(18, 0))
        for value, label in (('seg', 'segundos'), ('pct', '%')):
            ttk.Radiobutton(fila, text=label, value=value, variable=self.eje_tiempo,
                            command=self._dibujar_produccion,
                            style='Panel.TRadiobutton').pack(side='left', padx=(6, 0))
        ttk.Checkbutton(fila, text='mostrar referencia en el tiempo',
                        variable=self.ref_en_tiempo, command=self._dibujar_produccion,
                        style='Panel.TCheckbutton').pack(side='left', padx=(18, 0))

        self.fig_prod = Figure(figsize=(8, 7), dpi=100, facecolor=PANEL)
        self.fig_prod.set_layout_engine('tight')
        # El balance ocupa el doble que los otros dos: es la curva sobre la que
        # se toman decisiones, las demas se consultan. La sonoridad va aparte
        # porque su eje es el tiempo y no la frecuencia, asi que no puede
        # compartirlo con las de arriba.
        grilla = self.fig_prod.add_gridspec(3, 1, height_ratios=[2, 1, 1])
        self.ax_bal = self.fig_prod.add_subplot(grilla[0])
        self.ax_width = self.fig_prod.add_subplot(grilla[1], sharex=self.ax_bal)
        self.ax_st = self.fig_prod.add_subplot(grilla[2])
        self.canvas_prod = FigureCanvasTkAgg(self.fig_prod, master=hoja)

        nav = self._barra_grafico(self.canvas_prod, hoja)
        nav.pack(side='bottom', fill='x')
        self.canvas_prod.get_tk_widget().pack(side='top', fill='both', expand=True,
                                              padx=8, pady=(0, 6))
        self._refrescar_combo()
        self._reset_produccion('Elegi un archivo de la lista')

    def _reset_produccion(self, mensaje):
        for ax in (self.ax_bal, self.ax_width, self.ax_st):
            ax.clear()
            ax.set_facecolor(PANEL)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color(BORDER)
        self.ax_bal.text(0.5, 0.5, mensaje, transform=self.ax_bal.transAxes,
                         color=DIM, fontsize=12, ha='center', va='center')
        # Sin esto las tres etiquetas quedan a distinta altura del borde y se
        # montan unas sobre otras
        self.fig_prod.align_ylabels([self.ax_bal, self.ax_width, self.ax_st])
        self.canvas_prod.draw()

    def _build_balance(self, cuaderno):
        """Pestana guia: cuanto se desvia el tema del perfil, banda por banda.

        Dibuja la diferencia y no las curvas absolutas, que ya estan en
        Produccion: sobre un eje de noventa decibeles un desvio de dos no se
        ve, y dos son suficientes para que una mezcla suene distinta. Aca el
        cero es el perfil y la franja es su tolerancia, asi que estar adentro o
        afuera se lee de un vistazo.
        """
        hoja = tk.Frame(cuaderno, bg=PANEL)
        cuaderno.add(hoja, text='Balance')

        barra = tk.Frame(hoja, bg=PANEL)
        barra.pack(fill='x', padx=10, pady=(10, 4))
        tk.Label(barra, text='Canal:', bg=PANEL, fg=DIM,
                 font=fuente(9)).pack(side='left')
        for value, label in (('mid', 'central'), ('side', 'lateral')):
            ttk.Radiobutton(barra, text=label, value=value, variable=self.canal_balance,
                            command=self._dibujar_balance,
                            style='Panel.TRadiobutton').pack(side='left', padx=(6, 0))
        self.btn_csv_balance = ui_theme.boton(barra, 'Exportar reporte...',
                                              self.exportar_balance)
        self.btn_csv_balance.pack(side='right')
        self.btn_csv_balance.config(state='disabled')

        self.lbl_sonoridad = tk.Label(hoja, text='', bg=PANEL, fg=DIM,
                                      anchor='w', font=fuente(9))
        self.lbl_sonoridad.pack(fill='x', padx=12, pady=(0, 4))

        self.fig_bal = Figure(figsize=(8, 3), dpi=100, facecolor=PANEL)
        self.fig_bal.set_layout_engine('tight')
        self.ax_dev = self.fig_bal.add_subplot(111)
        self.canvas_bal = FigureCanvasTkAgg(self.fig_bal, master=hoja)
        self.canvas_bal.get_tk_widget().pack(fill='x', padx=8, pady=(0, 6))

        abajo = tk.Frame(hoja, bg=PANEL)
        abajo.pack(fill='both', expand=True, padx=8, pady=(0, 8))

        izq_borde = tk.Frame(abajo, bg=BORDER)
        izq_borde.pack(side='left', fill='both', expand=True)
        izq = tk.Frame(izq_borde, bg=PANEL)
        izq.pack(fill='both', expand=True, padx=1, pady=1)
        cols = [('banda', 'Banda', 90), ('rango', 'Rango', 100),
                ('desvio', 'Desvio', 70), ('estado', 'Estado', 70),
                ('ancho', 'Ancho', 70)]
        self.tabla_bandas = ttk.Treeview(izq, columns=[c[0] for c in cols],
                                         show='headings', selectmode='none', height=8)
        for clave, titulo, ancho in cols:
            self.tabla_bandas.heading(clave, text=titulo)
            self.tabla_bandas.column(clave, width=px(ancho), anchor='w',
                                     stretch=(clave == 'rango'))
        self.tabla_bandas.pack(fill='both', expand=True)
        for nombre, color in (('dentro', ui_theme.GREEN), ('al borde', ui_theme.YELLOW),
                              ('fuera', ui_theme.RED), ('sin datos', DIM)):
            self.tabla_bandas.tag_configure(nombre, foreground=color)

        der_borde = tk.Frame(abajo, bg=BORDER)
        der_borde.pack(side='left', fill='both', expand=True, padx=(8, 0))
        der = tk.Frame(der_borde, bg=PANEL)
        der.pack(fill='both', expand=True, padx=1, pady=1)
        tk.Label(der, text='Sugerencias para EQ Eight', bg=PANEL, fg=FG,
                 anchor='w', font=fuente(9, bold=True)).pack(fill='x', padx=8, pady=(6, 0))
        tk.Label(der, text='Orientativas: en el master tapan el sintoma. Lo que '
                           'lo resuelve es corregir\nel elemento que lo causa en '
                           'la mezcla.',
                 bg=PANEL, fg=DIM, anchor='w', justify='left',
                 font=fuente(8)).pack(fill='x', padx=8, pady=(0, 4))
        cols_eq = [('tipo', 'Tipo', 90), ('freq', 'Frecuencia', 90),
                   ('gan', 'Ganancia', 80), ('q', 'Q', 55)]
        self.tabla_eq = ttk.Treeview(der, columns=[c[0] for c in cols_eq],
                                     show='headings', selectmode='none', height=8)
        for clave, titulo, ancho in cols_eq:
            self.tabla_eq.heading(clave, text=titulo)
            self.tabla_eq.column(clave, width=px(ancho), anchor='w')
        self.tabla_eq.pack(fill='both', expand=True, padx=1, pady=(0, 1))
        self.tabla_eq.tag_configure('recortada', foreground=ui_theme.YELLOW)

    def _build_match(self, cuaderno):
        """Pestana de proceso: corrige el tema y escribe un archivo nuevo.

        Es la unica parte de la herramienta que produce audio en vez de
        medirlo, asi que el original nunca se toca: siempre se escribe al lado
        con el sufijo _match.
        """
        hoja = tk.Frame(cuaderno, bg=PANEL)
        cuaderno.add(hoja, text='Match')

        aviso = tk.Label(
            hoja,
            text='Iguala la curva del tema a la del perfil. Medir parecido no es '
                 'sonar mejor:\nsi el problema esta en como conviven los elementos, '
                 'moverlos a todos juntos no lo resuelve.',
            bg=PANEL, fg=DIM, anchor='w', justify='left', font=fuente(8))
        aviso.pack(fill='x', padx=12, pady=(10, 6))

        fila1 = tk.Frame(hoja, bg=PANEL)
        fila1.pack(fill='x', padx=12, pady=2)
        tk.Label(fila1, text='Cantidad:', bg=PANEL, fg=DIM,
                 font=fuente(9)).pack(side='left')
        self.lbl_amount = tk.Label(fila1, text='50%', bg=PANEL, fg=BLUE_SOFT,
                                   width=5, font=fuente(9))
        self.lbl_amount.pack(side='right')
        ttk.Scale(fila1, from_=0, to=100, variable=self.match_amount,
                  style='Panel.Horizontal.TScale',
                  command=lambda _v: self.lbl_amount.config(
                      text=f'{self.match_amount.get():.0f}%')
                  ).pack(side='left', fill='x', expand=True, padx=(8, 8))

        fila2 = tk.Frame(hoja, bg=PANEL)
        fila2.pack(fill='x', padx=12, pady=(6, 2))
        tk.Label(fila2, text='Taps del FIR:', bg=PANEL, fg=DIM,
                 font=fuente(9)).pack(side='left')
        combo = ttk.Combobox(fila2, textvariable=self.match_taps, width=7,
                             state='readonly', font=fuente(9),
                             values=('2047', '4095', '8191', '16383'))
        combo.pack(side='left', padx=(6, 0))

        ttk.Checkbutton(fila2, text='sub mono debajo de',
                        variable=self.match_sub_mono,
                        style='Panel.TCheckbutton').pack(side='left', padx=(20, 0))
        tk.Entry(fila2, textvariable=self.match_sub_hz, width=6, bg=ui_theme.INPUT_BG,
                 fg=FG, insertbackground=BLUE_SOFT, relief='flat',
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=BLUE_SOFT, font=fuente(9)).pack(side='left', padx=(6, 2))
        tk.Label(fila2, text='Hz', bg=PANEL, fg=DIM,
                 font=fuente(9)).pack(side='left')

        tk.Label(fila2, text='Sonoridad objetivo:', bg=PANEL, fg=DIM,
                 font=fuente(9)).pack(side='left', padx=(20, 0))
        tk.Entry(fila2, textvariable=self.match_lufs, width=7, bg=ui_theme.INPUT_BG,
                 fg=FG, insertbackground=BLUE_SOFT, relief='flat',
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=BLUE_SOFT, font=fuente(9)).pack(side='left', padx=(6, 2))
        tk.Label(fila2, text='LUFS (vacio = el del perfil)', bg=PANEL, fg=DIM,
                 font=fuente(8)).pack(side='left')

        fila3 = tk.Frame(hoja, bg=PANEL)
        fila3.pack(fill='x', padx=12, pady=(10, 4))
        self.btn_match = ui_theme.boton(fila3, 'Procesar y guardar...',
                                        self.procesar_match, principal=True)
        self.btn_match.pack(side='left')
        self.btn_match.config(state='disabled')
        self.barra_match = ttk.Progressbar(fila3, mode='determinate',
                                           maximum=9, length=px(140))
        self.lbl_match = tk.Label(fila3, text='Elegi un tema y un perfil',
                                  bg=PANEL, fg=DIM, anchor='w', font=fuente(9))
        self.lbl_match.pack(side='left', padx=(14, 0), fill='x', expand=True)

        self.fig_match = Figure(figsize=(8, 3.4), dpi=100, facecolor=PANEL)
        self.fig_match.set_layout_engine('tight')
        self.ax_match = self.fig_match.add_subplot(111)
        self.canvas_match = FigureCanvasTkAgg(self.fig_match, master=hoja)
        self.canvas_match.get_tk_widget().pack(fill='both', expand=True,
                                               padx=8, pady=(4, 8))
        self._reset_match('Procesa un tema para ver el antes y el despues')

    def _reset_match(self, mensaje):
        self.ax_match.clear()
        self.ax_match.set_facecolor(PANEL)
        self.ax_match.set_xticks([])
        self.ax_match.set_yticks([])
        for spine in self.ax_match.spines.values():
            spine.set_color(BORDER)
        self.ax_match.text(0.5, 0.5, mensaje, transform=self.ax_match.transAxes,
                           color=DIM, fontsize=11, ha='center', va='center')
        self.canvas_match.draw()

    # --- pestana de match ----------------------------------------------------

    def _estado_match(self):
        """Habilita el boton solo cuando hay con que trabajar."""
        if not hasattr(self, 'btn_match'):
            return
        if self.match_trabajando:
            return
        if not self.current:
            texto, listo = 'Elegi un tema de la lista', False
        elif not self.perfil:
            texto, listo = 'Cargá un perfil objetivo', False
        else:
            objetivo = self.perfil.get('lufs')
            destino = spectro_match.destino(self.current).name
            texto = f'{self.current.name} contra {self.perfil["nombre"]}'
            if objetivo is not None:
                texto += f' | objetivo {objetivo:.1f} LUFS'
            texto += f' | se guarda como {destino}'
            listo = True
        self.lbl_match.config(text=texto, fg=BLUE_SOFT if listo else DIM)
        self.btn_match.config(state='normal' if listo else 'disabled')

    def _opciones_match(self):
        """Lee los controles en el hilo principal.

        Las variables de Tk no se pueden leer desde otro hilo; se resuelven
        aca y viajan al worker como argumentos.
        """
        def numero(var, por_defecto):
            try:
                return float(var.get().strip())
            except (ValueError, AttributeError):
                return por_defecto

        lufs = self.match_lufs.get().strip()
        return {
            'amount': self.match_amount.get() / 100.0,
            'taps': int(self.match_taps.get()),
            'sub_mono': self.match_sub_mono.get(),
            'sub_hz': numero(self.match_sub_hz, spectro_match.SUB_MONO_HZ),
            'target_lufs': float(lufs) if lufs else None,
        }

    def procesar_match(self):
        if not (self.current and self.perfil) or self.match_trabajando:
            return
        sugerido = spectro_match.destino(self.current)
        salida = filedialog.asksaveasfilename(
            title='Guardar el tema procesado', defaultextension='.wav',
            initialdir=str(sugerido.parent), initialfile=sugerido.name,
            filetypes=[('WAV', '*.wav')])
        if not salida:
            return
        if Path(salida) == self.current:
            self.lbl_match.config(text='Elegi otro nombre: el original no se toca',
                                  fg=ui_theme.RED)
            return

        try:
            opciones = self._opciones_match()
        except ValueError:
            self.lbl_match.config(text='Revisá los valores: tienen que ser numeros',
                                  fg=ui_theme.RED)
            return

        self.match_trabajando = True
        self.btn_match.config(state='disabled')
        self.barra_match.config(value=0)
        self.barra_match.pack(side='right', padx=(10, 0))
        threading.Thread(target=self._worker_match,
                         args=(self.current, self.perfil, Path(salida), opciones),
                         daemon=True).start()

    def _worker_match(self, path, perfil, salida, opciones):
        def progreso(paso, texto):
            self.queue.put(('match_avance', path, (paso, texto)))
        try:
            data, rate, informe = spectro_match.procesar(
                path, perfil, progreso=progreso, **opciones)
            spectro_match.guardar(data, rate, salida)
            del data

            # Se vuelve a medir el archivo escrito, no lo que quedo en memoria:
            # asi el 'despues' del grafico es lo que de verdad se guardo
            progreso(9, 'midiendo el resultado')
            spec = spectro_reference.average_spectrum(salida)
            informe['salida'] = salida
            self.queue.put(('match', path, (spec, informe)))
        except Exception as e:  # pylint: disable=broad-except
            self.queue.put(('match_error', path, str(e)))

    def _curvas_de(self, spec):
        lufs = spectro_reference.integrated_from_spec(spec)
        return spectro_reference.tonal_balance(spec, -lufs if lufs is not None else 0.0)

    def _terminar_match(self, path, spec, informe):
        self.match_trabajando = False
        self.barra_match.pack_forget()
        canal = self.canal_balance.get()
        antes = spectro_balance.deviation(self._curvas_de(self.espectros.get(path)),
                                          self.perfil, canal)
        despues = spectro_balance.deviation(self._curvas_de(spec), self.perfil, canal)
        self._dibujar_match(antes, despues, informe, canal)

        partes = [f"guardado: {Path(informe['salida']).name}"]
        if informe.get('lufs_final') is not None:
            partes.append(f"{informe['lufs_final']:.1f} LUFS")
        if informe.get('true_peak_final') is not None:
            partes.append(f"pico real {informe['true_peak_final']:+.2f} dBTP")
        if informe.get('ajuste_extra_db'):
            partes.append(f"ajuste extra {informe['ajuste_extra_db']:+.2f} dB")
        self.lbl_match.config(text='   |   '.join(partes), fg=ui_theme.GREEN)
        self.btn_match.config(state='normal')
        self.set_status(f"Tema procesado: {Path(informe['salida']).name}", FG)

    def _dibujar_match(self, antes, despues, informe, canal):
        """Antes y despues sobre el mismo eje de desvio que la pestana Balance.

        Mismo cero, misma franja y misma escala: si no coincidieran, comparar
        las dos pestanas induciria a error.
        """
        self.ax_match.clear()
        self.ax_match.set_facecolor(PANEL)
        for spine in self.ax_match.spines.values():
            spine.set_color(BORDER)
        if despues is None:
            self._reset_match('El perfil no tiene ese canal')
            return

        self.ax_match.fill_between(despues['freqs'], despues['tolerancia_baja'],
                                   despues['tolerancia_alta'], color=ui_theme.YELLOW,
                                   alpha=0.22, linewidth=0, zorder=1)
        self.ax_match.axhline(0, color=ui_theme.YELLOW, linewidth=1.0,
                              linestyle=':', zorder=2)
        if antes is not None:
            self.ax_match.plot(
                antes['freqs'], spectro_balance.suavizar(antes['diferencia'],
                                                         antes['freqs']),
                color=DIM, linewidth=1.2, linestyle='--', zorder=3, label='antes')
        self.ax_match.plot(
            despues['freqs'], spectro_balance.suavizar(despues['diferencia'],
                                                       despues['freqs']),
            color=ui_theme.GREEN, linewidth=1.8, zorder=4, label='despues')

        self.ax_match.set_xscale('log')
        self.ax_match.set_xlim(spectro_reference.F_LO, spectro_reference.F_HI)
        self.ax_match.set_ylim(-12, 12)
        self.ax_match.set_xticks([20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
        self.ax_match.set_xticklabels(['20', '50', '100', '200', '500', '1k',
                                       '2k', '5k', '10k', '20k'])
        self.ax_match.grid(True, which='major', color=BORDER, linewidth=0.6, alpha=0.7)
        self.ax_match.tick_params(colors=DIM, labelsize=8)
        self.ax_match.set_ylabel('desvio (dB)', color=DIM, fontsize=8)
        self.ax_match.set_xlabel('Frecuencia (Hz)', color=DIM, fontsize=9)
        etiqueta = 'central' if canal == 'mid' else 'lateral'
        self.ax_match.set_title(
            f'canal {etiqueta} contra {self.perfil["nombre"]} - '
            f'correccion al {self.match_amount.get():.0f}%',
            color=core.CHART_TEXT, fontsize=10, loc='left', pad=8)
        leyenda = self.ax_match.legend(loc='upper right', fontsize=8,
                                       facecolor=PANEL, edgecolor=BORDER)
        for texto in leyenda.get_texts():
            texto.set_color(DIM)
        self.canvas_match.draw()

    def add_colorbar(self):
        """Escala dBFS fija. La normalizacion nunca cambia, asi que se crea una
        sola vez: los redibujados llaman a ax.clear(), que no la toca."""
        # Se guarda el mapeo para poder mover el tope: ahora sale de un
        # percentil del tema y no es siempre 0 dB, asi que una barra fija
        # mostraria una escala que no es la del grafico
        self.mappable = ScalarMappable(cmap=core.SPEK_CMAP,
                                       norm=Normalize(core.DB_FLOOR, 0))
        bar = self.fig.colorbar(self.mappable, ax=self.ax, pad=0.012,
                                fraction=0.035)
        bar.set_label('dBFS', color=DIM, fontsize=9)
        bar.ax.tick_params(colors=DIM, labelsize=8)
        bar.outline.set_edgecolor(BORDER)

    def reset_axes(self, message=None, color=DIM):
        """Lienzo vacio con un mensaje al centro.

        Sin argumentos es la invitacion inicial. Durante una espera conviene
        pasar el mensaje propio: dejar el cartel de 'arrastra un archivo'
        mientras se dibuja da a entender que no esta pasando nada.
        """
        self.ax.clear()
        self.ax.set_facecolor('#000000')
        if message is None:
            message = 'Arrastra un .flac o una carpeta' if HAS_DND else 'Usa "Abrir archivo..."'
        self.ax.text(0.5, 0.5, message, transform=self.ax.transAxes,
                     color=color, fontsize=13, ha='center', va='center')
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        for spine in self.ax.spines.values():
            spine.set_color(BORDER)

    # --- entrada de archivos -------------------------------------------------

    def on_drop(self, event):
        # Tk entrega varias rutas separadas por espacios, con llaves si hay espacios
        paths = [Path(p) for p in self.root.tk.splitlist(event.data)]
        if not paths:
            return
        if len(paths) == 1 and paths[0].is_dir():
            self.load_folder(paths[0])
        elif len(paths) == 1:
            self.load_files([paths[0]])
        else:
            self.load_files(paths)

    def pick_file(self):
        exts = ' '.join(f'*{e}' for e in sorted(core.AUDIO_EXTS))
        paths = filedialog.askopenfilenames(
            title='Elegi uno o varios archivos de audio',
            filetypes=[('Audio', exts), ('Todos los archivos', '*.*')])
        if paths:
            self.load_files([Path(p) for p in paths])

    def pick_folder(self):
        path = filedialog.askdirectory(title='Elegi una carpeta')
        if path:
            self.load_folder(Path(path))

    def load_folder(self, folder):
        files = sorted(p for p in folder.rglob('*') if p.suffix.lower() in core.AUDIO_EXTS)
        if not files:
            self.set_status(f'No se encontro audio en {folder.name}', '#f87171')
            return
        self.load_files(files)

    def load_files(self, paths):
        paths = [p for p in paths if p.exists() and p.suffix.lower() in core.AUDIO_EXTS]
        if not paths:
            self.set_status('Ningun archivo de audio valido', '#f87171')
            return

        self.tree.delete(*self.tree.get_children())
        self.summaries.clear()
        self.full_cache.clear()
        self.errors.clear()
        self.csv_btn.config(state='disabled')
        self.pending = len(paths)

        self.total = len(paths)
        self.done = 0
        self.start_progress(len(paths))
        threading.Thread(target=self.worker, args=(paths,), daemon=True).start()

    def worker(self, paths):
        """Corre fuera del hilo de Tk; devuelve cada resultado por la cola.

        Un solo archivo se analiza entero, porque hay que dibujarlo. Varios van
        al pool de procesos, que devuelve solo resumenes: mandar cada
        espectrograma entre procesos costaria mas de lo que ahorra el paralelo.
        """
        if len(paths) == 1:
            path = paths[0]
            try:
                result = core.analyze(path)
                self.queue.put(('row', path, core.summary(result, path)))
                self.queue.put(('full', path, result))
            except Exception as e:  # pylint: disable=broad-except
                self.queue.put(('error', path, str(e)))
        else:
            workers = spectro_batch.run(
                paths,
                lambda s: self.queue.put(('row', s['path'], s)),
                lambda p, e: self.queue.put(('error', p, e)))
            self.queue.put(('workers', None, workers))
        self.queue.put(('done', None, None))

    def drain_queue(self):
        try:
            while True:
                kind, path, payload = self.queue.get_nowait()
                if kind == 'row':
                    self.add_row(payload)
                elif kind == 'full':
                    self.cache_full(path, payload)
                    self.show(path, payload)
                elif kind == 'workers':
                    self.workers = payload
                elif kind == 'perfil_avance':
                    hechos, total, actual = payload
                    self.progress.config(value=hechos)
                    if actual:
                        self.set_status(f'Perfil: {hechos}/{total} - {actual}', DIM)
                elif kind == 'perfil':
                    self.progress.stop()
                    self.progress.pack_forget()
                    if payload:
                        self._usar_perfil(payload)
                        self.set_status(
                            f'Perfil creado y guardado: {spectro_profile.describir(payload)}',
                            FG)
                    else:
                        self.set_status('No se pudo leer ninguno de los temas', ui_theme.RED)
                elif kind == 'espectro':
                    spec, es_ref = payload
                    self._guardar_curva(path, spec, es_ref)
                    self.set_status('Espectro promedio listo', FG)
                elif kind == 'match_avance':
                    paso, texto = payload
                    self.barra_match.config(value=paso)
                    self.lbl_match.config(text=texto, fg=DIM)
                elif kind == 'match':
                    spec, informe = payload
                    self._terminar_match(path, spec, informe)
                elif kind == 'match_error':
                    self.match_trabajando = False
                    self.barra_match.pack_forget()
                    self.lbl_match.config(text=f'No se pudo procesar: {payload}',
                                          fg=ui_theme.RED)
                    self.btn_match.config(state='normal')
                elif kind == 'error':
                    self.pending -= 1
                    self.tick_progress()
                    self.errors.append((Path(path).name, payload))
                    self.set_status(f'Error con {path.name}: {payload}', '#f87171')
                elif kind == 'done':
                    self.finish_batch()
        except queue.Empty:
            pass
        self.root.after(80, self.drain_queue)

    # --- tabla ---------------------------------------------------------------

    def start_progress(self, total):
        """Barra con cuenta real en vez de animacion indefinida."""
        self.progress.config(mode='determinate', maximum=total, value=0)
        self.progress.pack(side='right')
        self.set_status(f'Analizando 0/{total}...', DIM)

    def tick_progress(self):
        self.done += 1
        self.progress.config(value=self.done)
        if self.total > 1:
            self.set_status(f'Analizando {self.done}/{self.total}...', DIM)

    def add_row(self, s):
        flags = '; '.join(s['signals'] + s['warnings'])
        values = (
            s['verdict'],
            s['name'],
            f"{s['cutoff']/1000:.1f}k" if s['cutoff'] else '-',
            f"{s['dr']:.0f}" if s['dr'] is not None else '-',
            f"{s['lufs']:.1f}" if s['lufs'] is not None else '-',
            f"{s['true_peak_db']:+.1f}",
            flags,
        )
        iid = self.tree.insert('', 'end', values=values, tags=(s['verdict'],))
        self.summaries[iid] = s
        self.pending -= 1
        self.tick_progress()
        # Insertar o seleccionar filas puede dejar el arbol desplazado a la
        # derecha y esconder la primera columna; se vuelve al inicio
        self.tree.xview_moveto(0)

    def finish_batch(self):
        self.progress.stop()
        self.progress.pack_forget()

        if self.errors:
            # El resumen final pisaba el aviso de error y la cuenta quedaba
            # corta sin explicacion: el que falla tiene que quedar dicho
            fallos = ', '.join(name for name, _ in self.errors[:3])
            extra = '...' if len(self.errors) > 3 else ''
            self.set_status(
                f'{len(self.summaries)} analizados, {len(self.errors)} con error: '
                f'{fallos}{extra}', '#f87171')
        if not self.summaries:
            return
        self.csv_btn.config(state='normal')

        repetidos = self.mark_duplicates()

        counts = {}
        for s in self.summaries.values():
            counts[s['verdict']] = counts.get(s['verdict'], 0) + 1
        if len(self.summaries) > 1:
            self.sort_by('verdict', keep_direction=True)
            if not self.errors:
                resumen = ', '.join(f'{v} {k}' for k, v in sorted(counts.items()))
                paralelo = f' | {self.workers} procesos' if self.workers > 1 else ''
                dupes = f' | {repetidos}' if repetidos else ''
                self.set_status(
                    f'{len(self.summaries)} archivos: {resumen}{paralelo}{dupes}', FG)

    def mark_duplicates(self):
        """Busca temas repetidos y lo anota en la fila de cada uno.

        Devuelve el texto para la barra de estado, o None si no hay ninguno.
        """
        iids = list(self.summaries)
        entries = [self.summaries[i] for i in iids]
        groups = spectro_dupes.find_duplicates(entries)
        if not groups:
            return None

        col = [c[0] for c in COLUMNS].index('flags')
        for numero, group in enumerate(groups, start=1):
            for pos in group:
                otros = [entries[o]['name'] for o in group if o != pos]
                nota = f'repetido #{numero} de: ' + ', '.join(otros)
                iid = iids[pos]
                actuales = list(self.tree.item(iid, 'values'))
                actuales[col] = f'{nota}; {actuales[col]}' if actuales[col] else nota
                self.tree.item(iid, values=actuales)
        return spectro_dupes.describe(groups, entries)

    def sort_by(self, key, keep_direction=False):
        if not keep_direction:
            self.sort_desc = not self.sort_desc if self.sort_key == key else False
        self.sort_key = key

        def sort_value(iid):
            s = self.summaries[iid]
            raw = {'name': s['name'], 'verdict': s['verdict'], 'cutoff': s['cutoff'],
                   'dr': s['dr'], 'lufs': s['lufs'], 'peak': s['true_peak_db'],
                   'flags': len(s['signals']) + len(s['warnings'])}[key]
            if raw is None:
                return (1, 0)           # los vacios al final, sin comparar tipos
            return (0, raw.lower() if isinstance(raw, str) else raw)

        for pos, iid in enumerate(sorted(self.tree.get_children(),
                                         key=sort_value, reverse=self.sort_desc)):
            self.tree.move(iid, '', pos)

    def on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        s = self.summaries.get(sel[0])
        if not s:
            return
        path = s['path']
        cached = self.full_cache.get(path)
        if cached is not None:
            self.show(path, cached)
            return
        # El espectrograma no se guardo: se recalcula solo para este archivo
        self.set_status(f"Dibujando {s['name']}...", DIM)
        self.reset_axes(f"Analizando {s['name']}...", DIM)
        self.canvas.draw()
        self.save_btn.config(state='disabled')
        self.progress.config(mode='indeterminate')
        self.progress.pack(side='right')
        self.progress.start(12)
        threading.Thread(target=self.single_worker, args=(path,), daemon=True).start()

    def single_worker(self, path):
        try:
            self.queue.put(('full', path, core.analyze(path)))
        except Exception as e:  # pylint: disable=broad-except
            self.queue.put(('error', path, str(e)))

    def cache_full(self, path, result):
        self.full_cache[path] = result
        self.full_cache.move_to_end(path)
        while len(self.full_cache) > FULL_CACHE_SIZE:
            self.full_cache.popitem(last=False)

    # --- salida --------------------------------------------------------------

    def show(self, path, result):
        self.progress.stop()
        self.progress.pack_forget()
        self.current = path
        self.result = result
        self.cache_full(path, result)
        self.redraw()
        self.save_btn.config(state='normal')
        self._estado_match()

        if self.cuaderno.index('current') in (1, 2):
            self._pedir_referencia_curva(path, es_referencia=False)

        mins, secs = divmod(int(result['duration']), 60)
        m = result['master']
        bits = f"{m['real_bits']} bit" if m['real_bits'] else result['subtype']
        extra = f" | DR{m['dr']:.0f}" if m['dr'] is not None else ''
        if m.get('lufs') is not None:
            extra += f" | {m['lufs']:.1f} LUFS"
        self.set_status(
            f"{result['verdict']} - {result['detail']} | {result['rate']} Hz | "
            f"{bits}{extra} | pico real {m['true_peak_db']:+.1f} dBTP | {mins}:{secs:02d}",
            core.VERDICT_COLORS[result['verdict']])

    def redraw(self):
        if not self.result:
            return
        channel = self.channel.get()
        if channel == 'side' and self.result.get('side_db') is None:
            self.set_status('El archivo es mono: no hay canal lateral', '#facc15')
            self.channel.set('mid')
            channel = 'mid'
        title = self.current.name + (' - canal lateral (L-R)' if channel == 'side' else '')
        tope = core.draw(self.ax, self.result, title, channel=channel,
                         yscale=self.yscale.get())
        if tope is not None:
            self.mappable.set_norm(Normalize(core.DB_FLOOR, tope))
        self.canvas.draw()

    # --- pestana de produccion -----------------------------------------------

    def _cambio_pestana(self, _event=None):
        """Calcula el espectro promedio recien cuando se mira una pestana que lo usa.

        Es otra pasada sobre el archivo con ventanas ocho veces mas grandes; no
        tiene sentido pagarla en cada analisis si nadie la va a ver.
        """
        if self.cuaderno.index('current') in (1, 2, 3) and self.current:
            self._pedir_referencia_curva(self.current, es_referencia=False)
        self._dibujar_balance()
        self._estado_match()

    def pick_reference(self):
        """Una sola referencia, que se guarda como perfil de un tema.

        La pestana dibuja siempre contra un perfil; tratar la referencia suelta
        como un perfil de N=1 evita mantener dos caminos que hacen lo mismo.
        """
        exts = ' '.join(f'*{e}' for e in sorted(core.AUDIO_EXTS))
        path = filedialog.askopenfilename(
            title='Elegi el tema de referencia',
            filetypes=[('Audio', exts), ('Todos los archivos', '*.*')])
        if path:
            self._pedir_referencia_curva(Path(path), es_referencia=True)

    def crear_perfil(self):
        """Perfil objetivo a partir de varios temas.

        Con uno solo se copia tambien lo que ese tema tiene de particular. Con
        varios queda la forma que comparten, y cuanto difieren entre si define
        el margen antes de que un desvio importe.
        """
        exts = ' '.join(f'*{e}' for e in sorted(core.AUDIO_EXTS))
        paths = filedialog.askopenfilenames(
            title='Elegi los temas de referencia (3 a 10 anda bien)',
            filetypes=[('Audio', exts), ('Todos los archivos', '*.*')])
        if not paths:
            return

        nombre = simpledialog.askstring(
            'Nombre del perfil', 'Como se llama este perfil?',
            initialvalue=Path(paths[0]).parent.name or 'perfil', parent=self.root)
        if not nombre:
            return

        self.start_progress(len(paths))
        self.set_status(f'Creando perfil con {len(paths)} temas...', DIM)
        threading.Thread(target=self._worker_perfil,
                         args=([Path(p) for p in paths], nombre), daemon=True).start()

    def _worker_perfil(self, paths, nombre):
        def progreso(hechos, total, actual):
            self.queue.put(('perfil_avance', None, (hechos, total, actual)))
        try:
            perfil = spectro_profile.construir(paths, nombre, progreso)
            if perfil:
                spectro_profile.guardar(perfil)
            self.queue.put(('perfil', None, perfil))
        except Exception as e:  # pylint: disable=broad-except
            self.queue.put(('error', Path(nombre), str(e)))

    def cargar_perfil(self):
        carpeta = spectro_profile.PERFILES_DIR
        carpeta.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            title='Elegi un perfil', initialdir=str(carpeta),
            filetypes=[('Perfil', '*.json')])
        if path:
            self._usar_perfil(spectro_profile.cargar(path))

    def _elegir_del_combo(self, _event=None):
        nombre = self.combo_perfiles.get()
        for guardado, ruta in spectro_profile.listar():
            if guardado == nombre:
                self._usar_perfil(spectro_profile.cargar(ruta))
                return

    def _refrescar_combo(self, seleccionado=None):
        nombres = [n for n, _ in spectro_profile.listar()]
        self.combo_perfiles['values'] = nombres
        if seleccionado in nombres:
            self.combo_perfiles.set(seleccionado)

    def _usar_perfil(self, perfil):
        self.perfil = perfil
        if perfil:
            self.ref_label.config(text=spectro_profile.describir(perfil), fg=BLUE_SOFT)
            self.ref_btn_quitar.config(state='normal')
            self._refrescar_combo(perfil['nombre'])
        self._dibujar_produccion()
        self._dibujar_balance()
        self._estado_match()

    def clear_reference(self):
        self.perfil = None
        self.ref_label.config(text='sin perfil', fg=DIM)
        self.ref_btn_quitar.config(state='disabled')
        self.combo_perfiles.set('')
        self._dibujar_produccion()
        self._dibujar_balance()
        self._estado_match()

    def _pedir_referencia_curva(self, path, es_referencia):
        """Encola el calculo del espectro promedio de un archivo."""
        guardado = self.espectros.get(path)
        if guardado is not None:
            self._guardar_curva(path, guardado, es_referencia)
            return
        etiqueta = 'referencia' if es_referencia else 'tema'
        self.set_status(f'Calculando espectro promedio del {etiqueta}...', DIM)
        threading.Thread(target=self._worker_espectro,
                         args=(path, es_referencia), daemon=True).start()

    def _worker_espectro(self, path, es_referencia):
        try:
            spec = spectro_reference.average_spectrum(path)
            self.queue.put(('espectro', path, (spec, es_referencia)))
        except Exception as e:  # pylint: disable=broad-except
            self.queue.put(('error', path, str(e)))

    def _guardar_curva(self, path, spec, es_referencia):
        self.espectros[path] = spec
        if es_referencia:
            self._usar_perfil(spectro_profile.una_referencia(spec, path))
        else:
            self._dibujar_produccion()
            self._dibujar_balance()

    def _offset_sonoridad(self, path):
        """Cuanto desplazar la curva para alinearla por sonoridad.

        Alinear por pico compararia volumen; alinear por sonoridad compara
        balance, que es lo unico que se quiere mirar al superponer dos temas.

        Se saca del propio espectro y no de la tabla: una referencia se elige
        desde cualquier carpeta y nunca paso por el analisis, asi que buscarla
        en la lista la dejaba sin alinear, que es justo el caso que importa.
        """
        lufs = spectro_reference.integrated_from_spec(self.espectros.get(path))
        return -lufs if lufs is not None else 0.0

    def _dibujar_produccion(self):
        actual = self.espectros.get(self.current) if self.current else None
        if actual is None:
            self._reset_produccion('Elegi un archivo de la lista')
            return

        bal = spectro_reference.tonal_balance(actual, self._offset_sonoridad(self.current))
        ancho = spectro_reference.stereo_width(actual)

        for ax in (self.ax_bal, self.ax_width, self.ax_st):
            ax.clear()
            ax.set_facecolor(PANEL)
            ax.grid(True, which='both', color=BORDER, linewidth=0.6, alpha=0.7)
            ax.tick_params(colors=DIM, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(BORDER)
        for ax in (self.ax_bal, self.ax_width):
            ax.set_xscale('log')

        self.ax_bal.plot(bal['freqs'], bal['mid'], color=BLUE_SOFT, linewidth=1.6,
                         label='central')
        if bal['side'] is not None:
            self.ax_bal.plot(bal['freqs'], bal['side'], color=ui_theme.INDIGO,
                             linewidth=1.2, alpha=0.85, label='lateral')
        if self.perfil:
            # La franja dice cuanto difieren entre si las referencias: adentro
            # es diferencia de estilo, afuera empieza a ser un desvio
            canal = self.perfil['mid']
            # Opacidad alta: sobre fondo oscuro, y con un eje de noventa
            # decibeles, una franja tipica de dos o tres no se distingue
            self.ax_bal.fill_between(self.perfil['freqs'], canal['bajo'], canal['alto'],
                                     color=ui_theme.YELLOW, alpha=0.24, linewidth=0,
                                     zorder=1)
            etiqueta = f"perfil ({self.perfil['n']})" if self.perfil['n'] > 1 else 'referencia'
            self.ax_bal.plot(self.perfil['freqs'], canal['mediana'], color=ui_theme.YELLOW,
                             linewidth=1.4, linestyle='--', label=etiqueta)

        self.ax_bal.set_ylabel('nivel (dB)', color=DIM, fontsize=8)
        self.ax_bal.set_title(self.current.name, color=core.CHART_TEXT, fontsize=10,
                              loc='left', pad=10)
        self.ax_bal.text(0.005, 0.03, 'alineado por sonoridad',
                         transform=self.ax_bal.transAxes, color=DIM, fontsize=8)
        leyenda = self.ax_bal.legend(loc='upper right', fontsize=8, facecolor=PANEL,
                                     edgecolor=BORDER, labelcolor=DIM)
        leyenda.get_frame().set_alpha(0.9)

        if ancho is not None:
            self.ax_width.plot(ancho['freqs'], ancho['width'], color=BLUE_SOFT,
                               linewidth=1.4)
            if self.perfil and self.perfil.get('side'):
                # El ancho del perfil es la diferencia entre sus dos medianas
                ancho_perfil = (self.perfil['side']['mediana']
                                - self.perfil['mid']['mediana'])
                self.ax_width.plot(self.perfil['freqs'], ancho_perfil,
                                   color=ui_theme.YELLOW, linewidth=1.2,
                                   linestyle='--')
            # La zona donde conviene que el estereo sea angosto
            self.ax_width.axvspan(spectro_reference.F_LO, spectro_reference.MONO_HI_HZ,
                                  color=ui_theme.RED, alpha=0.07)
            self.ax_width.axhline(0, color=DIM, linewidth=0.8, alpha=0.5)
            self.ax_width.set_ylim(-45, 15)

            # Donde la curva cruza el cero el lateral pesa mas que el central,
            # que es lo que se cancela al sumar a mono. Se marca sobre el
            # grafico para que el aviso y lo que se ve sean la misma cosa.
            cruces = spectro_reference.bands_over_zero(ancho)
            for desde, hasta in cruces:
                self.ax_width.axvspan(desde, hasta, color=ui_theme.YELLOW, alpha=0.16)

            textos = [spectro_reference.mono_verdict(ancho),
                      spectro_reference.describe_over_zero(cruces)]
            self.ax_width.text(
                spectro_reference.F_LO * 1.1, 12,
                '\n'.join(t for t in textos if t),
                color=ui_theme.YELLOW if cruces else DIM, fontsize=8, va='top')

        self.ax_width.set_ylabel('ancho (dB)', color=DIM, fontsize=8)
        self.ax_width.set_xlabel('Frecuencia (Hz)', color=DIM, fontsize=9)

        # Sonoridad de corto plazo: como respira el arreglo a lo largo del tema
        por_ciento = self.eje_tiempo.get() == 'pct'

        def eje_x(tiempos):
            return tiempos / tiempos[-1] * 100 if por_ciento and tiempos[-1] else tiempos

        st = spectro_reference.short_term_loudness(
            actual, self._offset_sonoridad(self.current))
        if st is not None:
            self.ax_st.plot(eje_x(st[0]), st[1], color=BLUE_SOFT, linewidth=1.2)
        # La curva en el tiempo solo existe para un tema concreto: un perfil de
        # varios no tiene una linea temporal que mostrar
        ref_path = None
        if self.perfil and self.perfil['n'] == 1 and self.perfil['archivos']:
            ref_path = Path(self.perfil['archivos'][0])
        ref_spec = self.espectros.get(ref_path) if ref_path else None
        if ref_spec is not None and self.ref_en_tiempo.get():
            st_ref = spectro_reference.short_term_loudness(
                ref_spec, self._offset_sonoridad(ref_path))
            if st_ref is not None:
                self.ax_st.plot(eje_x(st_ref[0]), st_ref[1], color=ui_theme.YELLOW,
                                linewidth=1.1, linestyle='--', alpha=0.9)

        # El cero es el nivel integrado del propio tema, porque las curvas ya
        # vienen desplazadas por su sonoridad
        self.ax_st.set_ylabel('corto plazo (LU)', color=DIM, fontsize=8)
        self.ax_st.set_xlabel('% del tema' if por_ciento else 'Tiempo (s)',
                              color=DIM, fontsize=9)
        self.ax_st.axhline(0, color=DIM, linewidth=0.8, alpha=0.5)
        self.ax_st.text(0.005, 0.04, '0 = sonoridad integrada del tema',
                        transform=self.ax_st.transAxes, color=DIM, fontsize=8)
        # Rango angosto a proposito: con veinte unidades las diferencias de una
        # o dos, que son las que importan al comparar arreglos, se ven planas.
        # Hasta -15 y no -12 para que el fundido del final no quede cortado.
        self.ax_st.set_ylim(-15, 3)
        self.ax_width.set_xlim(spectro_reference.F_LO, spectro_reference.F_HI)
        self.ax_width.set_xticks([20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
        self.ax_width.set_xticklabels(['20', '50', '100', '200', '500', '1k',
                                       '2k', '5k', '10k', '20k'])
        # Sin esto las tres etiquetas quedan a distinta altura del borde y se
        # montan unas sobre otras
        self.fig_prod.align_ylabels([self.ax_bal, self.ax_width, self.ax_st])
        self.canvas_prod.draw()

    # --- pestana de balance --------------------------------------------------

    def _curvas_actuales(self):
        spec = self.espectros.get(self.current) if self.current else None
        if spec is None:
            return None
        return spectro_reference.tonal_balance(spec, self._offset_sonoridad(self.current))

    def _resumen_actual(self):
        for resumen in self.summaries.values():
            if resumen['path'] == self.current:
                return resumen
        return None

    def _dibujar_balance(self):
        self.tabla_bandas.delete(*self.tabla_bandas.get_children())
        self.tabla_eq.delete(*self.tabla_eq.get_children())
        self.btn_csv_balance.config(state='disabled')
        self.filas_balance, self.sugerencias_eq = [], []

        curvas = self._curvas_actuales()
        self.ax_dev.clear()
        self.ax_dev.set_facecolor(PANEL)
        for spine in self.ax_dev.spines.values():
            spine.set_color(BORDER)

        if curvas is None or not self.perfil:
            falta = 'Elegi un archivo de la lista' if curvas is None else 'Cargá un perfil'
            self.ax_dev.set_xticks([])
            self.ax_dev.set_yticks([])
            self.ax_dev.text(0.5, 0.5, falta, transform=self.ax_dev.transAxes,
                             color=DIM, fontsize=12, ha='center', va='center')
            self.lbl_sonoridad.config(text='')
            self.canvas_bal.draw()
            return

        canal = self.canal_balance.get()
        dev = spectro_balance.deviation(curvas, self.perfil, canal)
        if dev is None:
            self.ax_dev.text(0.5, 0.5, 'El perfil no tiene ese canal',
                             transform=self.ax_dev.transAxes, color=DIM,
                             fontsize=12, ha='center', va='center')
            self.canvas_bal.draw()
            return

        dev_side = spectro_balance.deviation(curvas, self.perfil, 'side')
        self.filas_balance = spectro_balance.band_report(dev, dev_side)
        self.sugerencias_eq = spectro_balance.eq_suggestions(self.filas_balance)

        self.ax_dev.fill_between(dev['freqs'], dev['tolerancia_baja'],
                                 dev['tolerancia_alta'], color=ui_theme.YELLOW,
                                 alpha=0.22, linewidth=0, zorder=1)
        self.ax_dev.axhline(0, color=ui_theme.YELLOW, linewidth=1.0,
                            linestyle=':', zorder=2)
        # Suavizada solo para dibujar: los promedios de la tabla salen de la
        # curva sin suavizar
        self.ax_dev.plot(dev['freqs'],
                         spectro_balance.suavizar(dev['diferencia'], dev['freqs']),
                         color=BLUE_SOFT, linewidth=1.8, zorder=3)

        # Las bandas fuera de tolerancia se sombrean para que la tabla y el
        # grafico senalen lo mismo
        for fila in self.filas_balance:
            if fila['estado'] == 'fuera':
                self.ax_dev.axvspan(fila['desde'], fila['hasta'],
                                    color=ui_theme.RED, alpha=0.10, zorder=0)
            self.ax_dev.axvline(fila['desde'], color=BORDER, linewidth=0.6, zorder=0)

        self.ax_dev.set_xscale('log')
        self.ax_dev.set_xlim(spectro_reference.F_LO, spectro_reference.F_HI)
        self.ax_dev.set_ylim(-12, 12)
        self.ax_dev.set_xticks([20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
        self.ax_dev.set_xticklabels(['20', '50', '100', '200', '500', '1k',
                                     '2k', '5k', '10k', '20k'])
        self.ax_dev.grid(True, which='major', color=BORDER, linewidth=0.6, alpha=0.7)
        self.ax_dev.tick_params(colors=DIM, labelsize=8)
        self.ax_dev.set_ylabel('desvio (dB)', color=DIM, fontsize=8)
        self.ax_dev.set_xlabel('Frecuencia (Hz)', color=DIM, fontsize=9)
        etiqueta = 'central' if canal == 'mid' else 'lateral'
        self.ax_dev.set_title(f'{self.current.name} - canal {etiqueta} contra '
                              f"{self.perfil['nombre']}",
                              color=core.CHART_TEXT, fontsize=10, loc='left', pad=8)
        self.canvas_bal.draw()

        for fila in self.filas_balance:
            self.tabla_bandas.insert('', 'end', tags=(fila['estado'],), values=(
                fila['banda'],
                spectro_balance.etiqueta_rango(fila['desde'], fila['hasta']),
                f"{fila['desvio_db']:+.1f}" if fila['desvio_db'] is not None else '-',
                fila['estado'],
                f"{fila['ancho_db']:+.1f}" if fila['ancho_db'] is not None else '-'))

        for s in self.sugerencias_eq:
            self.tabla_eq.insert('', 'end',
                                 tags=('recortada',) if s['recortada'] else (),
                                 values=(s['tipo'],
                                         spectro_balance.etiqueta_hz(s['freq_hz']),
                                         f"{s['ganancia_db']:+.1f} dB", s['q']))
        if not self.sugerencias_eq:
            self.tabla_eq.insert('', 'end', values=('todo dentro de tolerancia',
                                                    '', '', ''))

        resumen = spectro_balance.loudness_summary(self._resumen_actual(), self.perfil)
        if resumen:
            partes = [f"{f['que']}: {f['tema']:+.1f} contra {f['perfil']:+.1f} "
                      f"{f['unidad']} ({f['diferencia']:+.1f})" for f in resumen]
            self.lbl_sonoridad.config(text='   |   '.join(partes))
        else:
            self.lbl_sonoridad.config(text='')
        self.btn_csv_balance.config(state='normal')

    def exportar_balance(self):
        if not self.filas_balance:
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv',
            initialfile=f'{self.current.stem} vs {self.perfil["nombre"]}.csv',
            filetypes=[('CSV', '*.csv')])
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            escritor = csv.writer(f, delimiter=';')
            escritor.writerow(['tema', self.current.name])
            escritor.writerow(['perfil', self.perfil['nombre'],
                               f"{self.perfil['n']} temas"])
            escritor.writerow([])
            escritor.writerow(spectro_balance.CSV_BANDAS)
            for fila in self.filas_balance:
                escritor.writerow([fila[c] if not isinstance(fila.get(c), float)
                                   else round(fila[c], 2)
                                   for c in spectro_balance.CSV_BANDAS])
            escritor.writerow([])
            escritor.writerow(spectro_balance.CSV_EQ)
            for s in self.sugerencias_eq:
                escritor.writerow([s[c] for c in spectro_balance.CSV_EQ])
        self.set_status(f'Reporte exportado a {path}', ui_theme.GREEN)

    def save_png(self):
        if not self.current:
            return
        suffix = '.lateral' if self.channel.get() == 'side' else ''
        path = filedialog.asksaveasfilename(
            defaultextension='.png',
            initialfile=f'{self.current.stem}{suffix}.spectro.png',
            initialdir=str(self.current.parent), filetypes=[('PNG', '*.png')])
        if path:
            self.fig.savefig(path, facecolor=PANEL, dpi=140)
            self.set_status(f'Guardado en {path}', '#4ade80')

    def export_csv(self):
        if not self.summaries:
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv', initialfile='analisis.csv',
            filetypes=[('CSV', '*.csv')])
        if not path:
            return
        rows = [self.summaries[iid] for iid in self.tree.get_children()]
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow([label for _, label in core.CSV_COLUMNS] + ['avisos'])
            for s in rows:
                writer.writerow(
                    [s[key] for key, _ in core.CSV_COLUMNS]
                    + ['; '.join(s['signals'] + s['warnings'])])
        self.set_status(f'Exportado a {path}', '#4ade80')

    def set_status(self, text, color):
        self.status.config(text=text, fg=color)


def main():
    # Imprescindible antes de cualquier cosa: al empaquetar con PyInstaller,
    # cada proceso hijo vuelve a ejecutar este mismo .exe, y sin esto abriria
    # una ventana nueva por cada uno en vez de trabajar
    multiprocessing.freeze_support()

    ui_theme.activar_dpi()   # antes de crear la raiz, o Windows ya la estiro
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    ui_theme.preparar_ventana(root)
    app = SpectroApp(root)

    # Archivos arrastrados sobre el icono del .exe, o pasados por linea de comandos
    if len(sys.argv) > 1:
        args = [Path(a) for a in sys.argv[1:]]
        if len(args) == 1 and args[0].is_dir():
            root.after(120, lambda: app.load_folder(args[0]))
        else:
            root.after(120, lambda: app.load_files(args))

    root.mainloop()


if __name__ == '__main__':
    main()
