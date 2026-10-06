"""Aspecto compartido por las dos ventanas del proyecto.

Los valores salen del sistema de diseno de la ticketera
(TicketOnlineFrontend/src/styles/_variables.scss). Estan aca y no repetidos en
cada ventana para que el descargador y el analizador no se vayan separando con
el tiempo: son dos caras de la misma herramienta y tienen que verse igual.

Cada constante lleva anotado de que variable SCSS viene, asi actualizar una es
buscarla alla y copiar el valor.
"""
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
    que una ventana se vea vieja. Dibujarlo sobre un Canvas cuesta poco y es la
    diferencia de aspecto mas grande por linea de codigo.
    """

    def __init__(self, parent, text, command, fill=ACCENT, hover=ACCENT_HOVER,
                 fg=FG, width=None, height=34, radius=RADIUS_PILL, bold=False,
                 outline='', **kw):
        ancho = width or (len(text) * 8 + 36)
        super().__init__(parent, width=ancho, height=height, bg=parent['bg'],
                         highlightthickness=0, bd=0, **kw)
        self._command = command
        self._fill, self._hover, self._fg = fill, hover, fg
        self._enabled = True

        # El radio se acota a la mitad del alto: con el valor de pildora del
        # sistema de diseno (99px) el poligono se deformaria
        r = min(radius, height // 2)
        self._shape = self._round_rect(1, 1, ancho - 1, height - 1, r, fill, outline)
        self._label = self.create_text(ancho / 2, height / 2, text=text,
                                       fill=fg, font=fuente(9, bold))

        self.bind('<Enter>', lambda _e: self._paint(self._hover))
        self.bind('<Leave>', lambda _e: self._paint(self._fill))
        self.bind('<Button-1>', self._click)

    def _round_rect(self, x1, y1, x2, y2, r, color, outline=''):
        # Un poligono con esquinas suavizadas: mas simple que componer arcos y
        # rectangulos, y a este tamano el resultado es identico
        puntos = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r,
                  x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
                  x1, y1 + r, x1, y1]
        return self.create_polygon(puntos, smooth=True, splinesteps=24, fill=color,
                                   outline=outline, width=1 if outline else 0)

    def _paint(self, color):
        if self._enabled:
            self.itemconfig(self._shape, fill=color)

    def _click(self, _event):
        if self._enabled and self._command:
            self._command()

    def config(self, **kw):
        """Acepta state y text, como un Button, para no cambiar a quien lo usa."""
        if 'state' in kw:
            self._enabled = kw.pop('state') != 'disabled'
            self.itemconfig(self._shape, fill=self._fill if self._enabled else BLUE_DIM)
            self.itemconfig(self._label, fill=self._fg if self._enabled else DIM)
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

    Los de tkinter pintan el recuadro del indicador con un solo color en los
    dos estados, asi que el no elegido se ve azul lleno y parece activo. Los de
    ttk permiten distinguirlos: apagado toma el fondo del panel, encendido el
    azul de marca.
    """
    for nombre, fondo in (('Barra', BG), ('Panel', PANEL)):
        for clase in ('TRadiobutton', 'TCheckbutton'):
            estilo = f'{nombre}.{clase}'
            style.configure(estilo, background=fondo, foreground=FG,
                            indicatorcolor=fondo, indicatorrelief='flat',
                            focuscolor=fondo, font=fuente(9), padding=(2, 0))
            style.map(
                estilo,
                background=[('active', fondo)],
                foreground=[('active', BLUE_SOFT), ('selected', FG)],
                # Vacio cuando esta apagado, azul de marca cuando esta elegido
                indicatorcolor=[('selected', BLUE), ('pressed', BLUE_HOVER),
                                ('!selected', fondo)],
            )

    # El deslizador de clam nace gris claro y sobre fondo oscuro se ve como si
    # estuviera deshabilitado
    for nombre, fondo in (('Barra', BG), ('Panel', PANEL)):
        estilo = f'{nombre}.Horizontal.TScale'
        style.configure(estilo, background=fondo, troughcolor=INPUT_BG,
                        borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
        style.map(estilo, background=[('active', fondo)],
                  troughcolor=[('active', INPUT_BG)])


def estilo_tabla(style, rowheight=36):
    """Aplica el aspecto de la ticketera a los Treeview de la ventana."""
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    estilo_controles(style)
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL,
                    foreground=FG, borderwidth=0, rowheight=rowheight,
                    font=fuente(9))
    style.configure('Treeview.Heading', background=BG, foreground=DIM,
                    borderwidth=0, relief='flat', padding=(8, 8),
                    font=fuente(8, bold=True))
    style.map('Treeview.Heading', background=[('active', BG)])
    style.map('Treeview', background=[('selected', BLUE_DIM)],
              foreground=[('selected', FG)])
    style.configure('Vertical.TScrollbar', background=BLUE_DIM, troughcolor=PANEL,
                    borderwidth=0, arrowcolor=DIM)
    style.configure('Horizontal.TScrollbar', background=BLUE_DIM, troughcolor=PANEL,
                    borderwidth=0, arrowcolor=DIM)
    style.configure('TProgressbar', background=BLUE, troughcolor=PANEL,
                    borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
