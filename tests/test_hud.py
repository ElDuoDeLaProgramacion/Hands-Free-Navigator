"""El HUD se alimenta de detector.debug; no cambia Detection."""
from hands_free.config import Config
from hands_free.gestures import DebugInfo
from hands_free.hud import hud_lines


def _text(dbg, **kw):
    args = dict(paused=False, last_event="", preview_only=False)
    args.update(kw)
    return "\n".join(hud_lines(Config(), dbg, **args))


def test_hud_includes_contract_fields():
    dbg = DebugInfo(hand_present=True, pose="palma abierta", thumb_dy=-0.12, trail_dx=0.31,
                    trail_dy=0.02, open_palm=True, fist=False)
    text = _text(dbg, paused=True, last_event="CLICK", preview_only=True)
    assert "pose: palma abierta" in text
    assert "thumb_dy" in text
    assert "trail dx=+0.31" in text
    assert "solo vista" in text
    assert "[SWIPE]" in text


def test_hud_shows_two_finger_diagnostics():
    dbg = DebugInfo(fingers="1100", finger_gap=0.21, spread="together", reach_i=0.95, base_i=1.0,
                    reach_m=0.30, base_m=1.0, mid_down=True, mouse_state="dip", dip_s=0.2,
                    dip_dominant="mid", cursor_mode="")
    text = _text(dbg)
    assert "IMRP=1100" in text and "gap 0.21" in text and "[together]" in text
    assert "M 0.30/1.00 [ABAJO]" in text and "I 0.95/1.00" in text
    assert "estado: dip" in text and "(mid)" in text


def test_hud_has_no_obsolete_pinch_line():
    assert "pinch" not in _text(DebugInfo(pinch_ratio=0.16)).lower()
    assert "[CLIC]" not in _text(DebugInfo(pinch_ratio=0.16))


def test_hud_pause_progress():
    assert "pausa (cuernos): 50%" in _text(DebugInfo(toggle_progress=0.5))
    assert "indice+menique" in _text(DebugInfo())
