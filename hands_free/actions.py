"""Traduce gestos a acciones reales del sistema (raton/teclado) con pyautogui."""
from __future__ import annotations

import atexit
import sys
import threading
import time

try:
    import pyautogui
    pyautogui.PAUSE = 0          # sin retardo artificial entre acciones
    pyautogui.FAILSAFE = True    # raton a una esquina de la pantalla aborta el programa
except ImportError:              # permite importar/testear sin pyautogui
    pyautogui = None

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
        atexit.register(self.close)   # nunca dejar Alt pulsado al salir

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
            self.kb.click()
        elif gesture is Gesture.DOUBLE_CLICK:
            now = self._clock()
            fast = (self._last_click_t is not None
                    and now - self._last_click_t < self.cfg.os_double_click_s)
            self._last_click_t = now
            if fast:
                self.kb.click()          # el 1er clic ya se envio: este lo completa como doble clic
            else:
                self.kb.doubleClick()    # 1er clic fuera del tiempo del sistema: doble clic completo
        elif gesture is Gesture.RIGHT_CLICK:
            self.kb.click(button="right")
        elif gesture is Gesture.SCROLL_UP:
            self.kb.scroll(self.cfg.scroll_amount)
        elif gesture is Gesture.SCROLL_DOWN:
            self.kb.scroll(-self.cfg.scroll_amount)
        elif gesture is Gesture.SWIPE_RIGHT:
            self._page(forward=True)
        elif gesture is Gesture.SWIPE_LEFT:
            self._page(forward=False)

    # --- Selector de aplicaciones: Alt mantenido + Tab / Shift+Tab ---
    def _app(self, forward: bool) -> None:
        with self._lock:
            if not self._switcher_open:
                self.kb.keyDown(self._mod)
                self._switcher_open = True
                time.sleep(0.05)      # Windows necesita ver Alt antes del primer Tab
            if forward:
                self.kb.press("tab")
            else:
                self.kb.keyDown("shift")
                self.kb.press("tab")
                self.kb.keyUp("shift")
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
                self.kb.moveRel(ix, iy)
        self._last_xy = (c.x, c.y)
        self._set_button(c.dragging)

    def _set_button(self, down: bool) -> None:
        if down and not self._button_down:
            self._button_down = True
            self.kb.mouseDown()
        elif not down and self._button_down:
            self._button_down = False
            self.kb.mouseUp()

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
                self.kb.keyUp(self._mod)
        self._set_button(False)   # nunca dejar el boton pulsado al salir

    @property
    def switcher_open(self) -> bool:
        return self._switcher_open

    def _page(self, forward: bool) -> None:
        if self.cfg.swipe_mode == "history":
            self.kb.hotkey("alt", "right" if forward else "left", interval=0.02)
        else:  # tabs: RePag/AvPag = pestana anterior/siguiente en orden (Ctrl+Tab puede ir en orden MRU)
            self.kb.hotkey("ctrl", "pagedown" if forward else "pageup", interval=0.02)
