"""ActionExecutor con teclado falso: sin pyautogui ni camara."""
import time

from hands_free.actions import ActionExecutor
from hands_free.config import Config
from hands_free.gestures import CursorState, Gesture


class FakeKB:
    def __init__(self):
        self.calls = []
    def size(self):
        return (1000, 500)
    def __getattr__(self, name):
        def f(*a, **k):
            self.calls.append((name,) + a)
        return f


def make(confirm=0.05):
    cfg = Config(); cfg.app_switch_confirm_s = confirm
    kb = FakeKB()
    ex = ActionExecutor(cfg, backend=kb)
    ex._mod = "alt"
    return ex, kb


def test_app_next_holds_alt_and_presses_tab_without_releasing():
    ex, kb = make(confirm=5)
    ex.run(Gesture.APP_NEXT)
    assert kb.calls == [("keyDown", "alt"), ("press", "tab")]
    assert ex.switcher_open
    ex.close()

def test_repeated_next_keeps_alt_held_and_cycles():
    ex, kb = make(confirm=5)
    ex.run(Gesture.APP_NEXT); ex.run(Gesture.APP_NEXT); ex.run(Gesture.APP_NEXT)
    assert kb.calls.count(("keyDown", "alt")) == 1          # Alt solo se pulsa una vez
    assert kb.calls.count(("press", "tab")) == 3
    assert ("keyUp", "alt") not in kb.calls
    ex.close()

def test_prev_uses_shift_tab_while_alt_held():
    ex, kb = make(confirm=5)
    ex.run(Gesture.APP_NEXT); ex.run(Gesture.APP_PREV)
    assert kb.calls[-3:] == [("keyDown", "shift"), ("press", "tab"), ("keyUp", "shift")]
    assert ex.switcher_open
    ex.close()

def test_selection_confirms_after_idle_timeout():
    ex, kb = make(confirm=0.05)
    ex.run(Gesture.APP_NEXT)
    time.sleep(0.2)
    assert ("keyUp", "alt") in kb.calls and not ex.switcher_open

def test_each_step_extends_the_timeout():
    ex, kb = make(confirm=0.15)
    ex.run(Gesture.APP_NEXT); time.sleep(0.1)
    ex.run(Gesture.APP_NEXT); time.sleep(0.1)               # 0.2 s en total, pero < 0.15 desde el ultimo
    assert ex.switcher_open
    time.sleep(0.2)
    assert not ex.switcher_open and kb.calls.count(("keyUp", "alt")) == 1

def test_click_confirms_selection_and_does_not_click():
    ex, kb = make(confirm=5)
    ex.run(Gesture.APP_NEXT); ex.run(Gesture.CLICK)
    assert kb.calls[-1] == ("keyUp", "alt") and ("click",) not in kb.calls
    assert not ex.switcher_open

def test_other_gesture_confirms_first_then_acts():
    ex, kb = make(confirm=5)
    ex.run(Gesture.APP_NEXT); ex.run(Gesture.SCROLL_UP)
    names = [c[0] for c in kb.calls]
    assert names.index("keyUp") < names.index("scroll")

def test_click_without_switcher_clicks_normally():
    ex, kb = make()
    ex.run(Gesture.CLICK)
    assert kb.calls == [("click",)]

def test_new_cycle_after_confirm_presses_alt_again():
    ex, kb = make(confirm=5)
    ex.run(Gesture.APP_NEXT); ex.close(); ex.run(Gesture.APP_NEXT)
    assert kb.calls.count(("keyDown", "alt")) == 2
    ex.close()

def test_close_is_safe_when_closed():
    ex, kb = make()
    ex.close(); ex.close()
    assert kb.calls == []


# ---------------- Raton ----------------
def _moves(kb):
    return [c[1:] for c in kb.calls if c[0] == "moveRel"]

def test_first_active_frame_only_anchors_no_jump():
    ex, kb = make()
    ex.update_cursor(CursorState(True, 0.5, 0.5, False, "move"))
    assert _moves(kb) == []

def test_relative_move_scales_by_gain_and_screen():
    ex, kb = make(); ex.cfg.move_gain = 2.0
    ex.update_cursor(CursorState(True, 0.50, 0.50, False, "move"))
    ex.update_cursor(CursorState(True, 0.60, 0.50, False, "move"))   # +0.1 ancho
    assert _moves(kb) == [(200, 0)]                                  # 0.1 * 2 * 1000 px

def test_fractional_pixels_accumulate():
    ex, kb = make(); ex.cfg.move_gain = 1.0
    ex.update_cursor(CursorState(True, 0.0, 0.0, False, "move"))
    for i in range(1, 11):                                            # 10 pasos de 0.0004 -> 0.4 px c/u
        ex.update_cursor(CursorState(True, 0.0004 * i, 0.0, False, "move"))
    assert sum(m[0] for m in _moves(kb)) == 4                         # 4 px totales, no 0

def test_reactivation_reanchors_no_jump():
    ex, kb = make()
    ex.update_cursor(CursorState(True, 0.2, 0.2, False, "move"))
    ex.update_cursor(CursorState())                                   # mano levantada / fuera de gesto
    ex.update_cursor(CursorState(True, 0.8, 0.8, False, "move"))     # aparece lejos
    assert _moves(kb) == []

def test_drag_presses_once_and_releases_once():
    ex, kb = make()
    ex.update_cursor(CursorState(True, 0.5, 0.5, True, "drag"))
    ex.update_cursor(CursorState(True, 0.6, 0.5, True, "drag"))
    ex.update_cursor(CursorState(True, 0.7, 0.5, True, "drag"))
    assert kb.calls.count(("mouseDown",)) == 1 and ("mouseUp",) not in kb.calls
    ex.update_cursor(CursorState(True, 0.7, 0.5, False, "move"))     # suelta el pellizco
    assert kb.calls.count(("mouseUp",)) == 1
    assert len(_moves(kb)) == 2                                       # se movio arrastrando

def test_losing_hand_during_drag_releases_button():
    ex, kb = make()
    ex.update_cursor(CursorState(True, 0.5, 0.5, True, "drag"))
    ex.update_cursor(CursorState())
    assert kb.calls[-1] == ("mouseUp",)

def test_release_all_frees_button_and_switcher():
    ex, kb = make(confirm=5)
    ex.update_cursor(CursorState(True, 0.5, 0.5, True, "drag"))
    ex.run(Gesture.APP_NEXT)
    ex.release_all()
    assert ("mouseUp",) in kb.calls and ("keyUp", "alt") in kb.calls

def test_close_releases_mouse_button():
    ex, kb = make()
    ex.update_cursor(CursorState(True, 0.5, 0.5, True, "drag"))
    ex.close()
    assert kb.calls[-1] == ("mouseUp",)


# ---------------- Zoom (dos manos) ----------------
def test_zoom_in_holds_ctrl_around_a_positive_scroll():
    ex, kb = make(); ex.cfg.zoom_scroll_amount = 100
    ex.run(Gesture.ZOOM_IN)
    assert kb.calls == [("keyDown", "ctrl"), ("scroll", 100), ("keyUp", "ctrl")]

def test_zoom_out_holds_ctrl_around_a_negative_scroll():
    ex, kb = make(); ex.cfg.zoom_scroll_amount = 100
    ex.run(Gesture.ZOOM_OUT)
    assert kb.calls == [("keyDown", "ctrl"), ("scroll", -100), ("keyUp", "ctrl")]


# ---------------- Paginas / clic derecho / doble clic ----------------
def test_tab_swipe_uses_pagedown_pageup():
    ex, kb = make()
    ex.run(Gesture.SWIPE_RIGHT); ex.run(Gesture.SWIPE_LEFT)
    assert kb.calls == [("hotkey", "ctrl", "pagedown"), ("hotkey", "ctrl", "pageup")] or \
        [c[:3] for c in kb.calls] == [("hotkey", "ctrl", "pagedown"), ("hotkey", "ctrl", "pageup")]
def test_right_click_uses_button_kwarg():
    calls = []
    class KB(FakeKB):
        def click(self, *a, **k):
            calls.append((a, k))
    ex = ActionExecutor(Config(), backend=KB())
    ex.run(Gesture.RIGHT_CLICK)
    assert calls == [((), {"button": "right"})]

def _clocked(t):
    calls = []
    class KB(FakeKB):
        def click(self, *a, **k):
            calls.append(("click", a, k))
        def doubleClick(self, *a, **k):
            calls.append(("doubleClick", a, k))
    ex = ActionExecutor(Config(), backend=KB())
    ex._clock = lambda: t[0]
    return ex, calls

def test_fast_double_click_sends_one_more_click():
    t = [100.0]; ex, calls = _clocked(t)
    ex.run(Gesture.CLICK); t[0] += 0.3; ex.run(Gesture.DOUBLE_CLICK)
    assert [c[0] for c in calls] == ["click", "click"]          # 2 clics, no 3

def test_slow_double_click_sends_full_double_click():
    t = [100.0]; ex, calls = _clocked(t)
    ex.run(Gesture.CLICK); t[0] += 0.7; ex.run(Gesture.DOUBLE_CLICK)   # 0.7 s > tiempo del sistema
    assert [c[0] for c in calls] == ["click", "doubleClick"]

def test_double_click_confirms_switcher_and_does_not_click():
    ex, kb = make(confirm=5)
    ex.run(Gesture.APP_NEXT); ex.run(Gesture.DOUBLE_CLICK)
    assert kb.calls[-1] == ("keyUp", "alt") and ("click",) not in kb.calls


def test_toggle_pause_is_ignored_by_actions():
    ex, kb = make()
    ex.run(Gesture.TOGGLE_PAUSE)
    assert kb.calls == []


# ---------------- Esquinas de pantalla (failsafe de pyautogui) ----------------
class PositionedKB(FakeKB):
    """Simula un raton real: mantiene una posicion y la recorta a los bordes de la pantalla."""
    def __init__(self, start=(500, 250)):
        super().__init__()
        self._pos = list(start)

    def position(self):
        self.calls.append(("position",))
        return tuple(self._pos)

    def moveRel(self, dx, dy):
        self.calls.append(("moveRel", dx, dy))
        w, h = self.size()
        self._pos[0] = min(max(self._pos[0] + dx, 0), w - 1)
        self._pos[1] = min(max(self._pos[1] + dy, 0), h - 1)


def test_move_into_corner_stops_short_of_the_exact_pixel():
    """Antes: `moveRel` a ciegas podia dejar el cursor en (0,0) y pyautogui abortaba
    el programa entero (failsafe) la siguiente vez que se movia o hacia clic."""
    cfg = Config(); cfg.move_gain = 2.0
    kb = PositionedKB(start=(3, 3))
    ex = ActionExecutor(cfg, backend=kb)
    ex.update_cursor(CursorState(True, 0.5, 0.5, False, "move"))
    ex.update_cursor(CursorState(True, 0.0, 0.0, False, "move"))   # movimiento grande hacia (0,0)
    x, y = kb.position()
    assert (x, y) != (0, 0)
    assert x >= cfg.edge_margin_px and y >= cfg.edge_margin_px


def test_failsafe_exception_does_not_crash_the_program():
    """Red de seguridad: si pyautogui llega a abortar igualmente, se ignora ese frame
    en vez de propagar la excepcion y tumbar el bucle principal."""
    from hands_free import actions as actions_mod

    class Boom(Exception):
        pass

    class FlakyKB(FakeKB):
        def click(self):
            raise Boom("raton en la esquina")

    old_exc = actions_mod._FAILSAFE_EXC
    actions_mod._FAILSAFE_EXC = Boom
    try:
        ex = ActionExecutor(Config(), backend=FlakyKB())
        ex.run(Gesture.CLICK)   # no debe lanzar
    finally:
        actions_mod._FAILSAFE_EXC = old_exc
