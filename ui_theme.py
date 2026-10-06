"""Aspecto compartido por las dos ventanas del proyecto.

Los valores salen del sistema de diseno de la ticketera
(TicketOnlineFrontend/src/styles/_variables.scss). Estan aca y no repetidos en
cada ventana para que el descargador y el analizador no se vayan separando con
el tiempo: son dos caras de la misma herramienta y tienen que verse igual.

Cada constante lleva anotado de que variable SCSS viene, asi actualizar una es
buscarla alla y copiar el valor.
"""
import sys
import tkinter as tk

# --- fondos ------------------------------------------------------------------
BG = '#040F1C'          # $bg-body
PANEL = '#061625'       # $bg-card
PANEL_ALT = '#0A1F33'   # fila alternada, reusa $bg-input
INPUT_BG = '#0A1F33'    # $bg-input

# --- texto -------------------------------------------------------------------
FG = '#EAF5FF'          # $text-main
DIM = '#7AA8C0'         # $text-muted

# $border es rgba($blue-600, .22). Aca va ya mezclado sobre la tarjeta porque
# tkinter no maneja transparencia.
BORDER = '#0A2C45'

# --- azules ------------------------------------------------------------------
BLUE = '#0088D4'        # $blue-600, la accion principal
BLUE_HOVER = '#006BB0'  # $blue-700
BLUE_SOFT = '#21A9FF'   # $blue-500, acentos y foco
BLUE_DIM = '#0B2F4C'    # seleccion y estado deshabilitado

ACCENT = '#0A1F33'      # boton secundario: mismo fondo que un campo
ACCENT_HOVER = '#10304E'

# --- semanticos --------------------------------------------------------------
GREEN = '#22D09A'       # $green
YELLOW = '#F5B800'      # $yellow
RED = '#F16C6C'         # $red
INDIGO = '#5B7CF5'      # $color-a

# --- forma -------------------------------------------------------------------
RADIUS_PILL = 99        # $radius-pill
RADIUS_MD = 10          # $radius-md

# Manrope es la fuente del sistema; si no esta instalada se cae a la misma
# alternativa que declara la hoja de estilos
FONT = 'Manrope'
FONT_FALLBACK = 'Segoe UI'

_FAMILIA = None

# Pixeles fisicos por pixel de diseno. Las medidas de este modulo y de las
# ventanas se piensan a 96 DPI y pasan por px(); las fuentes van en puntos y
# Tk ya las escala solo.
_ESCALA = 1.0


def activar_dpi():
    """Avisa a Windows que la ventana se dibuja a la resolucion real.

    Sin esto, con la pantalla al 150% Windows renderiza la ventana a 96 DPI y
    la estira como una imagen: todo el texto y los graficos salen borrosos.
    Tiene que llamarse antes de crear la raiz de Tk.
    """
    if sys.platform != 'win32':
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # consciente del DPI del sistema
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()     # Windows 7
        except (AttributeError, OSError):
            pass


def preparar_ventana(root):
    """Toma la escala de la pantalla y oscurece la barra de titulo.

    La barra blanca de Windows era lo primero que delataba una ventana de
    tkinter sobre un fondo casi negro. DWMWA_USE_IMMERSIVE_DARK_MODE es el
    atributo 20 desde Windows 10 20H1 y el 19 antes; donde no existe la
    llamada falla en silencio y la barra queda como estaba.
    """
    global _ESCALA
    _ESCALA = max(1.0, root.winfo_fpixels('1i') / 96)
    if sys.platform != 'win32':
        return
    import ctypes
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        oscuro = ctypes.c_int(1)
        for atributo in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, atributo, ctypes.byref(oscuro), ctypes.sizeof(oscuro)) == 0:
                break
    except (AttributeError, OSError):
        pass


def px(n):
    """Una medida de diseno (pensada a 96 DPI) en pixeles de esta pantalla."""
    return int(round(n * _ESCALA))


def fuente(size=9, bold=False):
    """Manrope si esta instalada, si no la alternativa de la hoja de estilos."""
    global _FAMILIA
    if _FAMILIA is None:
        import tkinter.font as tkfont
        familias = set(tkfont.families())
        _FAMILIA = FONT if FONT in familias else FONT_FALLBACK
    return (_FAMILIA, size, 'bold' if bold else 'normal')


class RoundedButton(tk.Canvas):
    """Boton de esquinas redondeadas dibujado a mano.

    tkinter no sabe redondear un Button, y el borde recto es justo lo que hace
    que una ventana se vea vieja. La forma se pinta con Pillow (ya viene con
    matplotlib, no suma peso al .exe) a 4x y se reduce: el poligono suavizado
    del Canvas no tiene antialiasing y el borde salia dentado.
    """

    def __init__(self, parent, text, command, fill=ACCENT, hover=ACCENT_HOVER,
                 fg=FG, width=None, height=34, radius=RADIUS_PILL, bold=False,
                 outline='', **kw):
        import tkinter.font as tkfont
        self._font = fuente(9, bold)
        alto = px(height)
        ancho = px(width) if width else (
            tkfont.Font(font=self._font).measure(text) + px(36))
        super().__init__(parent, width=ancho, height=alto, bg=parent['bg'],
                         highlightthickness=0, bd=0, cursor='hand2', **kw)
        self._command = command
        self._fill, self._hover, self._fg = fill, hover, fg
        self._enabled = True

        # El radio se acota a la mitad del alto: con el valor de pildora del
        # sistema de diseno (99px) la forma se deformaria
        r = min(px(radius), alto // 2)
        self._imgs = {
            'normal': self._forma(ancho, alto, r, fill, outline),
            'hover': self._forma(ancho, alto, r, hover, outline),
            'disabled': self._forma(ancho, alto, r, BLUE_DIM, ''),
        }
        self._shape = self.create_image(0, 0, anchor='nw', image=self._imgs['normal'])
        self._label = self.create_text(ancho / 2, alto / 2, text=text,
                                       fill=fg, font=self._font)

        self.bind('<Enter>', lambda _e: self._paint('hover'))
        self.bind('<Leave>', lambda _e: self._paint('normal'))
        self.bind('<Button-1>', self._click)

    def _forma(self, ancho, alto, r, color, outline):
        from PIL import Image, ImageDraw, ImageTk
        k = 4   # sobremuestreo: se dibuja grande y se reduce con filtro
        img = Image.new('RGBA', (ancho * k, alto * k), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle(
            (0, 0, ancho * k - 1, alto * k - 1), radius=r * k, fill=color,
            outline=outline or None, width=k if outline else 0)
        return ImageTk.PhotoImage(img.resize((ancho, alto), Image.LANCZOS),
                                  master=self)

    def _paint(self, estado):
        if self._enabled:
            self.itemconfig(self._shape, image=self._imgs[estado])

    def _click(self, _event):
        if self._enabled and self._command:
            self._command()

    def config(self, **kw):
        """Acepta state y text, como un Button, para no cambiar a quien lo usa."""
        if 'state' in kw:
            self._enabled = kw.pop('state') != 'disabled'
            self.itemconfig(self._shape, image=self._imgs[
                'normal' if self._enabled else 'disabled'])
            self.itemconfig(self._label, fill=self._fg if self._enabled else DIM)
            super().config(cursor='hand2' if self._enabled else '')
        if 'text' in kw:
            self.itemconfig(self._label, text=kw.pop('text'))
        if kw:
            super().config(**kw)

    configure = config


def boton(padre, texto, comando, principal=False, **kw):
    """Principal en azul de marca; secundario con contorno, como en la ticketera."""
    if principal:
        return RoundedButton(padre, texto, comando, fill=BLUE, hover=BLUE_HOVER,
                             height=38, bold=True, **kw)
    return RoundedButton(padre, texto, comando, outline=BORDER, **kw)


def tarjeta(padre, **kw):
    """Marco con contorno de 1px, el contenedor tipico del sistema de diseno.

    Devuelve (exterior, interior): el de afuera pinta el borde y el de adentro
    es donde va el contenido. tkinter no tiene borde con color propio, asi que
    se simula con un marco de un pixel de relleno.
    """
    exterior = tk.Frame(padre, bg=BORDER, highlightthickness=0, **kw)
    interior = tk.Frame(exterior, bg=PANEL)
    interior.pack(fill='both', expand=True, padx=1, pady=1)
    return exterior, interior


def estilo_controles(style):
    """Radios y casillas con indicador vacio cuando no estan elegidos.

    En clam el color del indicador sale de indicatorbackground, no de
    indicatorcolor: con la opcion equivocada quedaban los circulos blancos
    por defecto. Apagado toma el fondo del panel con contorno tenue, elegido
    el azul de marca.
    """
    for nombre, fondo in (('Barra', BG), ('Panel', PANEL)):
        for clase in ('TRadiobutton', 'TCheckbutton'):
            estilo = f'{nombre}.{clase}'
            style.configure(estilo, background=fondo, foreground=FG,
                            indicatorbackground=fondo, indicatorforeground=FG,
                            upperbordercolor=DIM, lowerbordercolor=DIM,
                            indicatormargin=(0, 0, px(6), 0),
                            focuscolor=fondo, font=fuente(9), padding=(2, 0))
            style.map(
                estilo,
                background=[('active', fondo)],
                foreground=[('active', BLUE_SOFT), ('selected', FG),
                            ('!selected', DIM)],
                indicatorbackground=[('selected', BLUE), ('pressed', BLUE_HOVER),
                                     ('!selected', fondo)],
                upperbordercolor=[('selected', BLUE), ('active', BLUE_SOFT)],
                lowerbordercolor=[('selected', BLUE), ('active', BLUE_SOFT)],
            )

    # El deslizador de clam nace gris claro y sobre fondo oscuro se ve como si
    # estuviera deshabilitado
    for nombre, fondo in (('Barra', BG), ('Panel', PANEL)):
        estilo = f'{nombre}.Horizontal.TScale'
        style.configure(estilo, background=fondo, troughcolor=INPUT_BG,
                        borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
        style.map(estilo, background=[('active', fondo)],
                  troughcolor=[('active', INPUT_BG)])


def _estilo_pestanas(style):
    """Pestanas del Notebook sobre el fondo de la ventana, la elegida en panel.

    Las de clam son grises claras y con borde en relieve, lo unico de la
    ventana que seguia con cara de Windows clasico. Se saca el elemento de
    foco para que no aparezca el recuadro punteado al hacer clic.
    """
    style.configure('TNotebook', background=BG, borderwidth=0,
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=PANEL,
                    tabmargins=(0, 0, 0, 0))
    style.configure('TNotebook.Tab', background=BG, foreground=DIM,
                    bordercolor=BG, lightcolor=BG, darkcolor=BG, borderwidth=0,
                    padding=(px(18), px(8)), font=fuente(9, bold=True))
    style.map('TNotebook.Tab',
              background=[('selected', PANEL), ('active', ACCENT)],
              foreground=[('selected', FG), ('active', FG)],
              lightcolor=[('selected', PANEL), ('active', ACCENT)],
              darkcolor=[('selected', PANEL), ('active', ACCENT)],
              bordercolor=[('selected', BORDER), ('active', ACCENT)],
              expand=[('selected', (0, 0, 0, 0))])
    style.layout('TNotebook.Tab', [('Notebook.tab', {'sticky': 'nswe', 'children': [
        ('Notebook.padding', {'sticky': 'nswe', 'children': [
            ('Notebook.label', {'sticky': 'nswe'})]})]})])


def _estilo_barras(style):
    """Barras de desplazamiento finas y sin flechas, como las de un navegador.

    clam pinta el estado deshabilitado (tabla vacia) en gris claro, que sobre
    el panel oscuro era la mancha mas visible de la ventana.
    """
    for orient in ('Vertical', 'Horizontal'):
        estilo = f'{orient}.TScrollbar'
        style.layout(estilo, [(f'{orient}.Scrollbar.trough', {
            'sticky': 'nswe', 'children': [
                (f'{orient}.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure(estilo, background=ACCENT_HOVER, troughcolor=PANEL,
                        bordercolor=PANEL, lightcolor=ACCENT_HOVER,
                        darkcolor=ACCENT_HOVER, arrowsize=px(10), gripsize=0,
                        borderwidth=0)
        estados = [('disabled', PANEL), ('pressed', BLUE), ('active', BLUE_DIM)]
        style.map(estilo, background=estados, lightcolor=estados,
                  darkcolor=estados, bordercolor=[('disabled', PANEL)])


def _estilo_campos(style):
    """Combos con el mismo fondo que los Entry, y su lista desplegable a tono."""
    style.configure('TCombobox', fieldbackground=INPUT_BG, background=INPUT_BG,
                    foreground=FG, arrowcolor=DIM, bordercolor=BORDER,
                    lightcolor=INPUT_BG, darkcolor=INPUT_BG, insertcolor=BLUE_SOFT,
                    selectbackground=INPUT_BG, selectforeground=FG,
                    padding=(px(6), px(3)))
    style.map('TCombobox',
              fieldbackground=[('readonly', INPUT_BG)],
              background=[('active', ACCENT_HOVER), ('readonly', INPUT_BG)],
              foreground=[('readonly', FG)],
              arrowcolor=[('active', BLUE_SOFT)],
              bordercolor=[('focus', BLUE_SOFT)],
              selectbackground=[('readonly', INPUT_BG)],
              selectforeground=[('readonly', FG)])
    # La lista desplegable es un Listbox de tk, no de ttk: se tine por opciones
    raiz = style.master
    if raiz is not None:
        raiz.option_add('*TCombobox*Listbox.background', INPUT_BG)
        raiz.option_add('*TCombobox*Listbox.foreground', FG)
        raiz.option_add('*TCombobox*Listbox.selectBackground', BLUE_DIM)
        raiz.option_add('*TCombobox*Listbox.selectForeground', FG)
        raiz.option_add('*TCombobox*Listbox.font', fuente(9))


def estilo_tabla(style, rowheight=36):
    """Aplica el aspecto de la ticketera a los widgets ttk de la ventana."""
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    estilo_controles(style)
    _estilo_pestanas(style)
    _estilo_barras(style)
    _estilo_campos(style)
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL,
                    foreground=FG, borderwidth=0, rowheight=px(rowheight),
                    bordercolor=PANEL, lightcolor=PANEL, font=fuente(9))
    style.configure('Treeview.Heading', background=BG, foreground=DIM,
                    borderwidth=0, relief='flat', padding=(px(8), px(8)),
                    bordercolor=BG, lightcolor=BG, darkcolor=BG,
                    font=fuente(8, bold=True))
    style.map('Treeview.Heading', background=[('active', ACCENT)],
              foreground=[('active', FG)])
    style.map('Treeview', background=[('selected', BLUE_DIM)],
              foreground=[('selected', FG)])
    style.configure('TProgressbar', background=BLUE, troughcolor=PANEL,
                    bordercolor=PANEL, borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
