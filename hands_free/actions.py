"""Traduce gestos a acciones reales del sistema (raton/teclado) con pyautogui."""
from __future__ import annotations

import atexit
import sys
import threading
import time

try:
    import pyautogui
    pyautogui.PAUSE = 0          # sin retardo artificial entre acciones
    pyautogui.FAILSAFE = True    # raton a una esquina exacta de la pantalla aborta pyautogui
except ImportError:              # permite importar/testear sin pyautogui
    pyautogui = None

class _NoFailSafe(Exception):
    """Nunca se lanza; solo es el 'except' cuando no hay pyautogui real (tests)."""


_FAILSAFE_EXC = getattr(pyautogui, "FailSafeException", _NoFailSafe) if pyautogui else _NoFailSafe

from .config import Config
from .gestures import CursorState, Gesture


class ActionExecutor:
    def __init__(self, cfg: Config, backend=None):
        self.cfg = cfg
        self.kb = backend or pyautogui
        self._mod = "command" if sys.platform == "darwin" else "alt"
        self._switcher_open = False
        self._timer = None
        self._lock = threading.RLock()
        self._clock = time.monotonic
        self._last_click_t = None
        self._last_xy = None       # ultima posicion normalizada de la mano (movimiento relativo)
        self._rem = (0.0, 0.0)     # fraccion de pixel pendiente
        self._button_down = False
        self._screen = None
        self._failsafe_warned = False
        atexit.register(self.close)   # nunca dejar Alt pulsado al salir

    def _call(self, name: str, *args, **kwargs):
        """Llama a `self.kb.<name>(...)` sin dejar que un FailSafeException tumbe el programa.

        pyautogui aborta con excepcion si el cursor toca EXACTAMENTE una esquina de la
        pantalla. `update_cursor` ya evita empujarlo ahi (ver `_move_clamped`), pero esto
        es la red de seguridad: si aun asi ocurre (raton fisico, otra ventana, etc.) el
        gesto en curso se pierde en vez de matar el proceso entero.
        """
        try:
            return getattr(self.kb, name)(*args, **kwargs)
        except _FAILSAFE_EXC:
            if not self._failsafe_warned:
                self._failsafe_warned = True
                print("[hands_free] raton en la esquina (failsafe de pyautogui): "
                      "se ignora esta accion, no se cierra el programa.", file=sys.stderr)
            return None

    def run(self, gesture: Gesture) -> None:
        if gesture in (Gesture.APP_NEXT, Gesture.APP_PREV):
            self._app(forward=gesture is Gesture.APP_NEXT)
            return
        if self._switcher_open:
            # Cualquier otro gesto confirma la app resaltada antes de actuar.
            # El pellizco solo confirma (no hace clic encima del selector).
            self.close()
            if gesture in (Gesture.CLICK, Gesture.DOUBLE_CLICK):
                return
        if gesture is Gesture.CLICK:
            self._last_click_t = self._clock()
            self._call("click")
        elif gesture is Gesture.DOUBLE_CLICK:
            now = self._clock()
            fast = (self._last_click_t is not None
                    and now - self._last_click_t < self.cfg.os_double_click_s)
            self._last_click_t = now
            if fast:
                self._call("click")          # el 1er clic ya se envio: este lo completa como doble clic
            else:
                self._call("doubleClick")    # 1er clic fuera del tiempo del sistema: doble clic completo
        elif gesture is Gesture.RIGHT_CLICK:
            self._call("click", button="right")
        elif gesture is Gesture.SCROLL_UP:
            self._call("scroll", self.cfg.scroll_amount)
        elif gesture is Gesture.SCROLL_DOWN:
            self._call("scroll", -self.cfg.scroll_amount)
        elif gesture is Gesture.SWIPE_RIGHT:
            self._page(forward=True)
        elif gesture is Gesture.SWIPE_LEFT:
            self._page(forward=False)
        elif gesture is Gesture.ZOOM_IN:
            self._ctrl_scroll(self.cfg.zoom_scroll_amount)
        elif gesture is Gesture.ZOOM_OUT:
            self._ctrl_scroll(-self.cfg.zoom_scroll_amount)

    def _ctrl_scroll(self, amount: int) -> None:
        """Ctrl + rueda: el zoom que reconocen el navegador y la mayoria de apps."""
        self._call("keyDown", "ctrl")
        self._call("scroll", amount)
        self._call("keyUp", "ctrl")

    # --- Selector de aplicaciones: Alt mantenido + Tab / Shift+Tab ---
    def _app(self, forward: bool) -> None:
        with self._lock:
            if not self._switcher_open:
                self._call("keyDown", self._mod)
                self._switcher_open = True
                time.sleep(0.05)      # Windows necesita ver Alt antes del primer Tab
            if forward:
                self._call("press", "tab")
            else:
                self._call("keyDown", "shift")
                self._call("press", "tab")
                self._call("keyUp", "shift")
            self._arm_timer()

    def _arm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self.cfg.app_switch_confirm_s, self.close)
        self._timer.daemon = True
        self._timer.start()

    # --- Raton: movimiento relativo + arrastre ---
    def update_cursor(self, c: CursorState) -> None:
        """Llamar cada frame con `detector.cursor`. Mueve el raton y pulsa/suelta el boton."""
        if not c.active:
            self._last_xy = None
            self._rem = (0.0, 0.0)
            self._set_button(False)
            return
        if self._last_xy is not None:
            if self._screen is None:
                self._screen = tuple(self.kb.size())
            w, h = self._screen
            fx = (c.x - self._last_xy[0]) * self.cfg.move_gain * w + self._rem[0]
            fy = (c.y - self._last_xy[1]) * self.cfg.move_gain * h + self._rem[1]
            ix, iy = round(fx), round(fy)
            self._rem = (fx - ix, fy - iy)
            if ix or iy:
                self._move_clamped(ix, iy, w, h)
        self._last_xy = (c.x, c.y)
        self._set_button(c.dragging)

    def _move_clamped(self, dx: int, dy: int, w: int, h: int) -> None:
        """Mueve el raton por (dx, dy) sin dejar que TOQUE el pixel exacto de una esquina.

        pyautogui aborta el programa entero si el cursor llega a llegar a una esquina de
        la pantalla (failsafe). Antes se aplicaba `moveRel` a ciegas, asi que al mover el
        cursor hacia un borde el gesto lo terminaba empujando justo a la esquina y el
        programa se caia. Aqui se consulta la posicion real y se recorta el destino para
        que se quede a `edge_margin_px` del borde: se puede llegar muy cerca de cualquier
        lado de la pantalla, pero nunca al pixel exacto que dispara el failsafe.
        """
        margin = max(0, self.cfg.edge_margin_px)
        try:
            cx, cy = self.kb.position()
        except Exception:
            self._call("moveRel", dx, dy)
            return
        nx = min(max(cx + dx, margin), max(margin, w - 1 - margin))
        ny = min(max(cy + dy, margin), max(margin, h - 1 - margin))
        rdx, rdy = nx - cx, ny - cy
        if rdx or rdy:
            self._call("moveRel", rdx, rdy)

    def _set_button(self, down: bool) -> None:
        if down and not self._button_down:
            self._button_down = True
            self._call("mouseDown")
        elif not down and self._button_down:
            self._button_down = False
            self._call("mouseUp")

    def release_all(self) -> None:
        """Pausa / vista previa: soltar boton y dejar de seguir la mano."""
        self._last_xy = None
        self._rem = (0.0, 0.0)
        self._set_button(False)
        self.close()

    def close(self) -> None:
        """Suelta Alt: el sistema abre la app resaltada."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._switcher_open:
                self._switcher_open = False
                self._call("keyUp", self._mod)
        self._set_button(False)   # nunca dejar el boton pulsado al salir

    @property
    def switcher_open(self) -> bool:
        return self._switcher_open

    def _page(self, forward: bool) -> None:
        if self.cfg.swipe_mode == "history":
            self._call("hotkey", "alt", "right" if forward else "left", interval=0.02)
        else:  # tabs: RePag/AvPag = pestana anterior/siguiente en orden (Ctrl+Tab puede ir en orden MRU)
            self._call("hotkey", "ctrl", "pagedown" if forward else "pageup", interval=0.02)
