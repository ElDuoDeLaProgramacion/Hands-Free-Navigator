"""Tests de GestureDetector sin camara. Ejecutar:  pytest -q"""
from hands_free import fixtures as fx
from hands_free.config import Config
from hands_free.gestures import Detection, DebugInfo, Gesture, GestureDetector

T0 = 100.0  # los cooldowns comparan contra 0.0 inicial: empezar lejos de cero


def run(det, frames, t0=T0, dt=0.05):
    """Alimenta frames con reloj simulado; devuelve lista de (t, Detection)."""
    return [(t0 + i * dt, det.update(lm, now=t0 + i * dt)) for i, lm in enumerate(frames)]

def events(results):
    return [d.gesture for _, d in results if d.gesture is not None]

def new():
    cfg = Config()
    return GestureDetector(cfg), cfg


# ---------------- Contrato ----------------
def test_no_hand():
    det, _ = new()
    d = det.update(None, now=T0)
    assert d == Detection(None, "sin mano", False)
    assert isinstance(det.debug, DebugInfo) and not det.debug.hand_present

def test_thumb_up_requires_hold_then_scrolls_up():
    det, cfg = new()
    res = run(det, [fx.fist_thumb_up()] * 12, dt=0.05)   # 0.55 s
    first = next(t for t, d in res if d.gesture is Gesture.SCROLL_UP)
    assert first - T0 >= cfg.scroll_hold_s - 1e-9
    assert all(d.gesture is None for t, d in res if t - T0 < cfg.scroll_hold_s)

def test_thumb_up_repeats_at_interval():
    det, cfg = new()
    res = run(det, [fx.fist_thumb_up()] * 30, dt=0.05)   # 1.5 s
    n = len(events(res))
    assert n >= 5 and set(events(res)) == {Gesture.SCROLL_UP}

def test_thumb_down_scrolls_down():
    det, cfg = new()
    res = run(det, [fx.fist_thumb_down()] * 12)
    assert set(events(res)) == {Gesture.SCROLL_DOWN}

def test_thumb_released_before_hold_does_not_scroll():
    det, cfg = new()
    res = run(det, [fx.fist_thumb_up()] * 3 + [fx.fist_neutral()] * 3)  # 0.15 s < hold
    assert events(res) == []


# ---------------- d) Swipe ----------------
def test_swipe_right():
    det, _ = new()
    assert events(run(det, fx.swipe_right())) == [Gesture.SWIPE_RIGHT]

def test_swipe_left():
    det, _ = new()
    assert events(run(det, fx.swipe_left())) == [Gesture.SWIPE_LEFT]

def test_rising_open_palm_is_not_swipe_or_scroll():
    det, _ = new()
    assert events(run(det, fx.rising_open_palm())) == []
    assert det.debug.trail_dy < -0.15                # el HUD debe verlo como vertical

def test_rising_fist_is_not_scroll():
    det, _ = new()
    assert events(run(det, fx.rising_fist())) == []


# ---------------- f) Palma quieta: NO swipe ----------------
def test_still_palm_is_not_swipe():
    det, _ = new()
    res = run(det, fx.still_palm())
    assert events(res) == [] and res[-1][1].pose == "palma abierta"
    assert abs(det.debug.trail_dx) < 1e-6


# ---------------- Higiene de estado ----------------
def test_losing_hand_resets_thumb_hold():
    det, cfg = new()
    run(det, [fx.fist_thumb_up()] * 4)               # 0.2 s acumulados
    det.update(None, now=T0 + 0.25)                  # se pierde la mano
    res = run(det, [fx.fist_thumb_up()] * 3, t0=T0 + 0.3)
    assert events(res) == []                         # el hold empieza de cero


# ---------------- Swipe corto/lento (ajuste tras prueba de cama: 0/20) ----------------
def _palm_path(x0, x1, y0, y1, n):
    return [fx.open_palm(x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1))
            for i in range(n)]

def test_short_slow_swipe_right_is_detected():
    det, _ = new()
    frames = _palm_path(0.40, 0.62, 0.5, 0.5, 12)     # dx=0.22 en 0.55 s
    assert events(run(det, frames)) == [Gesture.SWIPE_RIGHT]

def test_short_slow_swipe_left_is_detected():
    det, _ = new()
    frames = _palm_path(0.62, 0.40, 0.5, 0.5, 12)
    assert events(run(det, frames)) == [Gesture.SWIPE_LEFT]

def test_small_jitter_is_not_swipe():
    det, _ = new()
    frames = _palm_path(0.50, 0.56, 0.5, 0.52, 12)    # temblor de ~6 % del ancho
    assert events(run(det, frames)) == []

def test_diagonal_motion_is_not_swipe():
    det, _ = new()
    frames = _palm_path(0.40, 0.62, 0.40, 0.60, 12)   # dx=0.22 pero dy=0.20 > max_dy
    assert events(run(det, frames)) == []


# ---------------- Eje del pulgar con la mano girada (de lado) ----------------
def _scroll_events(frames, cfg=None):
    det = GestureDetector(cfg or Config())
    return events(run(det, frames)), det

def test_upright_hand_thumb_axis_unchanged():
    ev, det = _scroll_events([fx.fist_thumb_up()] * 12)
    assert set(ev) == {Gesture.SCROLL_UP} and abs(det.debug.thumb_dy + 0.67) < 0.02

def test_seated_40deg_tilt_still_scrolls_on_image_axis():
    """Mano sentada ~40° no debe saltar al eje 'hand' (el umbral 35° lo rompía)."""
    ev, det = _scroll_events([fx.rotate(fx.fist_thumb_up(), 40)] * 12)
    assert set(ev) == {Gesture.SCROLL_UP}
    assert det.debug.thumb_dy < -0.5

def test_rotated_90_thumb_up_scrolls_up():
    ev, _ = _scroll_events([fx.rotate(fx.fist_thumb_up(), 90)] * 12)
    assert set(ev) == {Gesture.SCROLL_UP}

def test_rotated_90_thumb_down_scrolls_down():
    ev, _ = _scroll_events([fx.rotate(fx.fist_thumb_down(), 90)] * 12)
    assert set(ev) == {Gesture.SCROLL_DOWN}

def test_rotated_minus90_thumb_up_scrolls_up():
    ev, _ = _scroll_events([fx.rotate(fx.fist_thumb_up(), -90)] * 12)
    assert set(ev) == {Gesture.SCROLL_UP}

def test_upside_down_hand_uses_hand_axis():
    ev, _ = _scroll_events([fx.rotate(fx.fist_thumb_up(), 180)] * 12)
    assert set(ev) == {Gesture.SCROLL_UP}       # con eje de imagen saldria SCROLL_DOWN

def test_image_axis_mode_still_available():
    cfg = Config(); cfg.thumb_axis = "image"
    ev, _ = _scroll_events([fx.rotate(fx.fist_thumb_up(), 180)] * 12, cfg)
    assert set(ev) == {Gesture.SCROLL_DOWN}     # comportamiento antiguo, opt-in

def test_rotated_neutral_fist_is_not_scroll():
    ev, _ = _scroll_events([fx.rotate(fx.fist_neutral(), 90)] * 12)
    assert ev == []

def test_rotated_open_palm_swipe_is_not_scroll():
    ev, _ = _scroll_events([fx.rotate(fx.open_palm(), 90)] * 12)
    assert ev == []


# ---------------- Swipe: gesto de retorno no debe disparar el contrario ----------------
def test_return_stroke_does_not_fire_opposite_swipe():
    det, _ = new()
    res = run(det, fx.swipe_right() + fx.swipe_left())   # ida y vuelta en ~0.8 s
    assert events(res) == [Gesture.SWIPE_RIGHT]

def test_slow_vertical_drift_with_small_dx_is_not_swipe():
    det, _ = new()
    frames = _palm_path(0.45, 0.50, 0.7, 0.4, 12)        # sube despacio, dx 0.05
    assert events(run(det, frames)) == []


# ---------------- Regresion: pulgar arriba REAL con la mano de lado ----------------
def test_sideways_fist_thumb_up_in_image_scrolls_up():
    """Con dedos horizontales (tilt ~90) el pulgar sigue apuntando arriba en la imagen."""
    ev, det = _scroll_events([fx.fist_sideways_thumb("up")] * 12)
    assert set(ev) == {Gesture.SCROLL_UP} and det.debug.thumb_dy < -0.5

def test_sideways_fist_thumb_down_in_image_scrolls_down():
    ev, _ = _scroll_events([fx.fist_sideways_thumb("down")] * 12)
    assert set(ev) == {Gesture.SCROLL_DOWN}


# ---------------- Cambio de aplicacion: dos dedos deslizados (modo opt-in "swipe") ----------------
def test_neutral_fist_pose_and_no_events():
    det, _ = new()
    res = run(det, [fx.fist_neutral()] * 20)
    assert events(res) == [] and res[-1][1].pose == "puno (neutral)" and not det.cursor.active

def test_fist_thumb_up_down_still_scroll():
    ev, _ = _scroll_events([fx.fist_thumb_up()] * 12)
    assert set(ev) == {Gesture.SCROLL_UP}
    ev, _ = _scroll_events([fx.fist_thumb_down()] * 12)
    assert set(ev) == {Gesture.SCROLL_DOWN}

def test_waving_hand_back_and_forth_fires_only_once():
    det, _ = new()
    frames = (fx.swipe_right() + fx.swipe_left()) * 5           # ~4 s agitando la palma
    assert len(events(run(det, frames))) == 1

def test_continuous_slow_drift_across_screen_fires_once():
    det, _ = new()
    frames = [fx.open_palm(0.05 + 0.9 * i / 39, 0.5) for i in range(40)]  # 2 s en una direccion
    assert len(events(run(det, frames))) == 1

def test_very_slow_drift_does_not_fire_at_all():
    det, _ = new()
    frames = [fx.open_palm(0.1 + 0.8 * i / 79, 0.5) for i in range(80)]   # 0.2 pantallas/s
    assert events(run(det, frames)) == []

def test_swipe_again_after_hand_rests():
    det, _ = new()
    frames = fx.swipe_right() + [fx.open_palm(0.75)] * 30 + fx.swipe_left()
    assert events(run(det, frames)) == [Gesture.SWIPE_RIGHT, Gesture.SWIPE_LEFT]

def test_swipe_again_after_closing_palm_briefly():
    det, _ = new()
    frames = fx.swipe_right() + [fx.fist_neutral()] * 3 + fx.swipe_left()
    assert events(run(det, frames)) == [Gesture.SWIPE_RIGHT, Gesture.SWIPE_LEFT]



# =====================================================================================
#  Nuevo esquema: dos dedos (mover / clics / arrastre), cambio de app, pausa
# =====================================================================================
UP = 6      # frames (0.30 s) con los dos dedos arriba: sobra para armar (0.15 s)

def together(n): return [fx.two_together()] * n
def apart(n): return [fx.two_apart()] * n
def fold(n, cx=0.5): return [fx.fist_neutral(cx, 0.5)] * n


# ---------------- Contrato ----------------
def test_contract_enum_and_detection_fields():
    assert {g.name for g in Gesture} == {
        "CLICK", "SCROLL_UP", "SCROLL_DOWN", "SWIPE_LEFT", "SWIPE_RIGHT", "APP_NEXT", "APP_PREV",
        "RIGHT_CLICK", "DOUBLE_CLICK", "TOGGLE_PAUSE"}
    d = Detection(None, "x", True)          # posicional: gesture, pose, hand_present
    assert (d.gesture, d.pose, d.hand_present) == (None, "x", True)

def test_debug_fields_are_populated():
    det, _ = new()
    det.update(fx.two_together(), now=T0)
    assert 0.1 < det.debug.finger_gap < 0.3 and det.debug.spread == "together" and det.debug.two_fingers
    det.update(fx.fist_thumb_up(), now=T0 + 1)
    assert det.debug.thumb_dy < -0.5 and det.debug.fist
    det2, _ = new()
    res = run(det2, fx.swipe_right())
    assert det2.debug.trail_dx > 0 and abs(det2.debug.trail_dy) < 1e-6
    assert det2.debug.pose == res[-1][1].pose

def test_swipe_cooldown_blocks_double_fire():
    det, _ = new()
    res = run(det, fx.swipe_right() + fx.swipe_right())
    assert events(res).count(Gesture.SWIPE_RIGHT) == 1


# ---------------- Mover el cursor: dos dedos juntos ----------------
def _cursor_trace(det, frames, t0=T0, dt=0.05):
    out = []
    for i, lm in enumerate(frames):
        det.update(lm, now=t0 + i * dt)
        out.append(det.cursor)
    return out

def test_two_fingers_together_move_cursor_after_arm_delay():
    det, _ = new()
    tr = _cursor_trace(det, together(8))
    assert not tr[0].active and not tr[2].active
    assert tr[-1].active and tr[-1].mode == "move" and not tr[-1].dragging
    assert det.debug.pose == "dos dedos juntos" and det.debug.mouse_state == "armed"

def test_cursor_follows_hand_position():
    det, _ = new()
    frames = [fx.two_together(0.3 + 0.02 * i, 0.5) for i in range(14)]
    tr = [c for c in _cursor_trace(det, frames) if c.active]
    xs = [c.x for c in tr]
    assert len(tr) >= 4 and xs == sorted(xs) and xs[-1] - xs[0] > 0.05
    assert all(abs(c.y - tr[0].y) < 1e-6 for c in tr)

def test_cursor_is_smoothed():
    det, _ = new()
    _cursor_trace(det, [fx.two_together(0.3, 0.5)] * 8)
    det.update(fx.two_together(0.6, 0.5), now=T0 + 1.0)
    assert 0.3 < det.cursor.x < 0.6

def test_spread_fingers_do_not_move_cursor():
    det, _ = new()
    assert not any(c.active for c in _cursor_trace(det, apart(12)))
    assert det.debug.spread == "apart"

def test_single_finger_pointing_no_longer_moves_cursor():
    det, _ = new()
    assert not any(c.active for c in _cursor_trace(det, [fx.pointing()] * 12))

def test_no_cursor_in_other_poses():
    for lm in (fx.fist_neutral(), fx.open_palm(), fx.fist_thumb_up(), fx.horns()):
        det, _ = new()
        assert not any(c.active for c in _cursor_trace(det, [lm] * 10))

def test_losing_hand_deactivates_cursor():
    det, _ = new()
    _cursor_trace(det, together(8))
    det.update(None, now=T0 + 1.0)
    assert not det.cursor.active

def test_spread_classification_has_hysteresis():
    mid = 0.027                                   # gap ~0.38: entre together (0.30) y apart (0.45)
    det, _ = new()
    _cursor_trace(det, together(4) + [fx.two_apart(spread=mid)] * 6)
    assert det.debug.spread == "together" and det.cursor.active
    det2, _ = new()
    _cursor_trace(det2, apart(4) + [fx.two_apart(spread=mid)] * 6)
    assert det2.debug.spread == "apart" and not det2.cursor.active


# ---------------- Clic izquierdo: bajar ambos dedos y subir ----------------
def test_both_fingers_down_and_up_is_left_click_on_release():
    det, _ = new()
    res = run(det, together(UP) + fold(4) + together(3))
    assert events(res) == [Gesture.CLICK]
    first_up = T0 + (UP + 4) * 0.05
    assert next(t for t, d in res if d.gesture) == first_up      # dispara al SUBIR, no al bajar

def test_click_freezes_cursor_while_fingers_are_down():
    det, _ = new()
    tr = _cursor_trace(det, together(UP) + fold(4))
    assert not any(c.active for c in tr[UP:])

def test_fingers_held_down_too_long_is_not_a_click():
    det, _ = new()
    assert events(run(det, together(UP) + fold(14) + together(4))) == []     # 0.7 s > 0.55 s

def test_one_frame_flicker_is_not_a_click():
    det, _ = new()
    assert events(run(det, together(UP) + fold(1) + together(4))) == []

def test_fist_without_prior_two_fingers_never_clicks():
    det, _ = new()
    assert events(run(det, fold(10) + together(UP))) == []

def test_resting_fist_after_moving_does_nothing_and_becomes_neutral():
    det, _ = new()
    res = run(det, together(UP) + fold(60))       # 3 s con el puno cerrado
    assert events(res) == [] and res[-1][1].pose == "puno (neutral)"
    assert events(run(det, together(10), t0=T0 + 4)) == []       # y al abrir de nuevo tampoco

def test_click_needs_arming_first():
    det, _ = new()
    assert events(run(det, together(2) + fold(4) + together(3))) == []       # 0.10 s < arm_s

def test_thumb_position_never_causes_a_click():
    """Antes el pulgar sobre el puno se leia como pellizco: ahora no existe el pellizco."""
    for target in (8, 12):
        det, _ = new()
        fist = fx.fist_neutral()
        tip = fist[target]
        fist[4] = fx.LM(tip.x - 0.005, tip.y)
        assert events(run(det, [fist] * 12)) == []


# ---------------- Doble clic: bajar y subir 2 veces ----------------
def test_two_quick_dips_are_click_then_double_click():
    det, _ = new()
    assert events(run(det, together(UP) + fold(4) + together(4) + fold(4) + together(3))) == [
        Gesture.CLICK, Gesture.DOUBLE_CLICK]

def test_second_dip_after_window_is_a_new_single_click():
    det, _ = new()
    frames = together(UP) + fold(4) + together(20) + fold(4) + together(3)   # ~1.3 s entre clics
    assert events(run(det, frames)) == [Gesture.CLICK, Gesture.CLICK]

def test_third_quick_dip_after_double_is_ignored():
    det, _ = new()
    frames = together(UP) + (fold(4) + together(4)) * 3
    assert events(run(det, frames)) == [Gesture.CLICK, Gesture.DOUBLE_CLICK]

def test_second_dip_elsewhere_is_not_a_double_click():
    det, _ = new()
    frames = (together(UP) + fold(4) + [fx.two_together(0.5)] * 2 + [fx.two_together(0.75)] * 3
              + fold(4, cx=0.75) + [fx.two_together(0.75)] * 3)
    assert events(run(det, frames)) == [Gesture.CLICK, Gesture.CLICK]

def test_bounce_faster_than_min_gap_is_not_a_double_click():
    det, _ = new()
    frames = together(UP) + fold(2) + together(1) + fold(2) + together(3)    # gap ~0.15 s entre subidas
    res = run(det, frames)
    assert events(res).count(Gesture.DOUBLE_CLICK) == 0


# ---------------- Clic derecho: bajar solo el medio ----------------
def test_middle_finger_down_and_up_is_right_click():
    det, _ = new()
    res = run(det, together(UP) + [fx.two_drop("right")] * 4 + together(3))
    assert events(res) == [Gesture.RIGHT_CLICK]

def test_right_click_is_not_an_app_switch():
    """Queja anterior: el gesto parecido a 'dos dedos' cambiaba de app en vez de clic derecho."""
    det, _ = new()
    ev = events(run(det, together(UP) + [fx.two_drop("right")] * 8 + together(3)))
    assert Gesture.APP_NEXT not in ev and Gesture.APP_PREV not in ev and ev == [Gesture.RIGHT_CLICK]

def test_index_finger_down_alone_does_nothing_when_together():
    det, _ = new()
    assert events(run(det, together(UP) + [fx.two_drop("left")] * 4 + together(3))) == []

def test_middle_down_too_long_is_not_a_right_click():
    det, _ = new()
    assert events(run(det, together(UP) + [fx.two_drop("right")] * 14 + together(4))) == []

def test_right_click_does_not_left_click():
    det, _ = new()
    assert Gesture.CLICK not in events(run(det, together(UP) + [fx.two_drop("right")] * 4 + together(3)))


# ---------------- Arrastrar: bajar ambos, mantener y mover ----------------
def _drag_frames(hold_frames=13, steps=5):
    return (together(UP) + fold(hold_frames)
            + [fx.fist_neutral(0.5 + 0.02 * i, 0.5) for i in range(1, steps + 1)])

def test_hold_fold_and_move_starts_drag_and_follows_hand():
    det, _ = new()
    tr = _cursor_trace(det, _drag_frames())
    drag = [c for c in tr if c.dragging]
    assert drag and drag[-1].mode == "drag" and drag[-1].x > drag[0].x
    assert det.debug.pose == "arrastrar"

def test_raising_fingers_ends_drag_without_click():
    det, _ = new()
    res = run(det, _drag_frames() + together(4))
    assert events(res) == []
    assert det.cursor.active and not det.cursor.dragging and det.cursor.mode == "move"

def test_fold_and_hold_without_moving_never_drags():
    det, _ = new()
    tr = _cursor_trace(det, together(UP) + fold(30))
    assert not any(c.dragging for c in tr)

def test_drag_can_be_disabled():
    cfg = Config(); cfg.drag_enabled = False
    tr = _cursor_trace(GestureDetector(cfg), _drag_frames())
    assert not any(c.dragging for c in tr)


# ---------------- Cambio de aplicacion: dos dedos SEPARADOS ----------------
def _app_seq(side, arm=0.30, down=0.20, dt=0.05, mirror=False):
    m = fx.mirror_x if mirror else (lambda x: x)
    up = [m(fx.two_apart())] * int(round(arm / dt))
    dn = [m(fx.two_drop(side, spread=0.05))] * int(round(down / dt))
    return up + dn

def test_apart_drop_right_finger_is_app_next():
    det, _ = new()
    assert events(run(det, _app_seq("right"))) == [Gesture.APP_NEXT]

def test_apart_drop_left_finger_is_app_prev():
    det, _ = new()
    assert events(run(det, _app_seq("left"))) == [Gesture.APP_PREV]

def test_app_left_right_follow_the_image_not_the_finger_name():
    det, _ = new()
    assert events(run(det, _app_seq("left", mirror=True))) == [Gesture.APP_NEXT]   # el indice ahora esta a la derecha
    det2, _ = new()
    assert events(run(det2, _app_seq("right", mirror=True))) == [Gesture.APP_PREV]

def test_app_holding_finger_down_fires_once():
    det, _ = new()
    assert events(run(det, _app_seq("right", down=1.0))) == [Gesture.APP_NEXT]

def test_app_repeated_taps_each_fire():
    det, _ = new()
    frames = _app_seq("right") + _app_seq("right") + _app_seq("left")
    assert events(run(det, frames)) == [Gesture.APP_NEXT, Gesture.APP_NEXT, Gesture.APP_PREV]

def test_app_drop_without_arming_is_ignored():
    det, _ = new()
    frames = [fx.two_apart()] * 2 + [fx.two_drop("right", spread=0.05)] * 4
    assert events(run(det, frames)) == []

def test_app_single_frame_flicker_is_ignored():
    det, _ = new()
    frames = apart(8) + [fx.two_drop("right", spread=0.05)] + apart(4)
    assert events(run(det, frames)) == []

def test_app_fist_then_single_finger_is_not_a_tap():
    det, _ = new()
    assert events(run(det, fold(8) + [fx.two_drop("right", spread=0.05)] * 6)) == []

def test_apart_both_fingers_down_does_nothing():
    """Con los dedos separados, cerrar ambos no es clic (solo juntos hay clic)."""
    det, _ = new()
    assert events(run(det, apart(UP) + fold(4) + apart(3))) == []

def test_app_tap_never_clicks_or_moves_cursor():
    det, _ = new()
    tr = _cursor_trace(det, _app_seq("right", down=0.5))
    assert not any(c.active for c in tr)


# ---------------- Puno neutral ----------------
def test_closing_fist_from_move_mode_and_resting_never_fires_events():
    det, _ = new()
    assert events(run(det, together(UP) + fold(40))) == []


# ---------------- Pausa / reanudar: cuernos (indice + menique) ----------------
def test_horns_held_toggles_pause_once():
    det, cfg = new()
    res = run(det, [fx.horns()] * 25)                        # 1.2 s
    assert events(res) == [Gesture.TOGGLE_PAUSE]
    assert next(t for t, d in res if d.gesture) - T0 >= cfg.toggle_hold_s - 1e-6

def test_horns_released_early_does_nothing():
    det, _ = new()
    assert events(run(det, [fx.horns()] * 10 + fold(5))) == []

def test_horns_fires_only_once_per_hold():
    det, _ = new()
    assert events(run(det, [fx.horns()] * 80)) == [Gesture.TOGGLE_PAUSE]

def test_horns_again_after_release_toggles_again():
    det, _ = new()
    frames = [fx.horns()] * 25 + fold(10) + [fx.horns()] * 25
    assert events(run(det, frames)) == [Gesture.TOGGLE_PAUSE, Gesture.TOGGLE_PAUSE]

def test_horns_progress_is_reported():
    det, _ = new()
    run(det, [fx.horns()] * 11)
    assert 0.45 < det.debug.toggle_progress < 0.55 and det.debug.pose == "cuernos (mantener)"

def test_horns_cancels_armed_mouse_state():
    det, _ = new()
    frames = together(UP) + [fx.horns()] * 3 + fold(4) + together(3)
    assert events(run(det, frames)) == []

def test_other_poses_are_not_horns():
    for lm in (fx.two_together(), fx.two_drop("right"), fx.open_palm(), fx.fist_neutral(), fx.fist_thumb_up()):
        det, _ = new()
        assert Gesture.TOGGLE_PAUSE not in events(run(det, [lm] * 40))


# =====================================================================================
#  Robustez ante ruido real (dedos que no bajan a la vez, foreshortening, nudillos casi pegados)
# =====================================================================================
def test_right_click_survives_index_wobble():
    """Un frame en que el indice tambien se ve 'abajo' no debe convertirlo en clic izquierdo."""
    det, _ = new()
    frames = (together(UP) + [fx.two_drop("right"), fx.fist_neutral(), fx.two_drop("right"),
                              fx.two_drop("right")] + together(3))
    assert events(run(det, frames)) == [Gesture.RIGHT_CLICK]

def test_right_click_short_touch_at_30fps():
    det, _ = new()
    frames = [fx.two_together()] * 8 + [fx.two_drop("right")] * 3 + together(3)
    assert events(run(det, frames, dt=0.033)) == [Gesture.RIGHT_CLICK]

def test_left_click_with_staggered_fingers():
    """Los dedos casi nunca bajan a la vez: indice, luego ambos, luego solo el medio al subir."""
    det, _ = new()
    frames = (together(UP) + [fx.two_drop("left")] + fold(3) + [fx.two_drop("right")] + together(3))
    assert events(run(det, frames)) == [Gesture.CLICK]

def test_left_click_at_30fps():
    det, _ = new()
    frames = [fx.two_together()] * 8 + fold(4) + together(3)
    assert events(run(det, frames, dt=0.033)) == [Gesture.CLICK]

def test_left_click_with_ring_finger_noise():
    det, _ = new()
    noisy_fold = fx.make_hand(ring=True)              # indice y medio cerrados, anular suelto
    assert events(run(det, together(UP) + [noisy_fold] * 4 + together(3))) == [Gesture.CLICK]

def test_ring_finger_slightly_up_does_not_prevent_arming():
    det, _ = new()
    lm = fx.make_hand(index=True, middle=True, ring=True)
    tr = _cursor_trace(det, [lm] * 8)
    assert tr[-1].active and det.debug.mouse_state == "armed"

def test_fingers_bent_from_the_knuckle_still_click():
    """Bajar los dedos desde el nudillo (se acortan en la imagen) tambien cuenta."""
    det, _ = new()
    down = fx.pivot(fx.two_together(), 0.5)
    assert events(run(det, together(UP) + [down] * 4 + together(3))) == [Gesture.CLICK]
    assert det.debug.base_i > 0.9

def test_only_middle_bent_from_the_knuckle_is_right_click():
    det, _ = new()
    down = fx.pivot(fx.two_together(), 0.5, fingers=("middle",))
    assert events(run(det, together(UP) + [down] * 4 + together(3))) == [Gesture.RIGHT_CLICK]

def test_double_click_with_staggered_fingers_never_becomes_right_click():
    det, _ = new()
    dip = [fx.two_drop("left")] + fold(2) + [fx.two_drop("right")]
    frames = together(UP) + dip + together(3) + dip + together(3)
    ev = events(run(det, frames))
    assert ev == [Gesture.CLICK, Gesture.DOUBLE_CLICK]

def test_one_noisy_wide_frame_does_not_turn_right_click_into_tab():
    """La separacion se mide con la mediana de los ultimos frames, no con el ultimo."""
    det, _ = new()
    frames = together(UP) + [fx.two_apart()] + [fx.two_drop("right")] * 4 + together(3)
    ev = events(run(det, frames))
    assert ev == [Gesture.RIGHT_CLICK]

def test_tab_side_uses_fingertips_not_knuckles():
    """Con la mano ladeada el nudillo del indice puede quedar a la derecha del medio;
    las puntas (bien separadas) siguen diciendo cual es el dedo izquierdo."""
    def tilt(lm):
        lm[5] = fx.LM(0.56, lm[5].y)            # nudillo indice a la derecha del nudillo medio (0.5)
        return lm
    up = [tilt(fx.two_apart()) for _ in range(6)]
    dn = [tilt(fx.two_drop("left", spread=0.05)) for _ in range(4)]      # baja el indice (dedo izq)
    det, _ = new()
    assert events(run(det, up + dn)) == [Gesture.APP_PREV]

def test_tab_drop_survives_a_both_down_flicker():
    det, _ = new()
    frames = (apart(UP) + [fx.two_drop("right", spread=0.05), fx.fist_neutral()]
              + [fx.two_drop("right", spread=0.05)] * 4)
    assert events(run(det, frames)) == [Gesture.APP_NEXT]

def test_tab_left_finger_at_30fps():
    det, _ = new()
    frames = [fx.two_apart()] * 8 + [fx.two_drop("left", spread=0.05)] * 5
    assert events(run(det, frames, dt=0.033)) == [Gesture.APP_PREV]

def test_tab_never_produces_right_click():
    for side in ("left", "right"):
        det, _ = new()
        ev = events(run(det, _app_seq(side, down=0.4) + apart(4)))
        assert Gesture.RIGHT_CLICK not in ev and Gesture.CLICK not in ev

def test_partial_bend_between_thresholds_is_not_a_dip():
    """Un dedo que solo se acorta al 75 % (entre down_frac y up_frac) no cuenta como bajado."""
    det, _ = new()
    slight = fx.pivot(fx.two_together(), 0.75)
    assert events(run(det, together(UP) + [slight] * 6 + together(3))) == []
