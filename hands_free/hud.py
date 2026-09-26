"""HUD de calibracion. hud_lines no depende de OpenCV (tests sin camara)."""
from __future__ import annotations

from typing import List, Tuple

from .config import Config
from .gestures import DebugInfo

_OK = (0, 220, 0)
_WARN = (0, 200, 255)
_IDLE = (220, 220, 220)
_BG = (0, 0, 0)


def hud_lines(
    cfg: Config,
    dbg: DebugInfo,
    *,
    paused: bool,
    last_event: str,
    preview_only: bool,
) -> List[str]:
    """Texto estable para tests y para pintar. Un string por linea."""
    mode = "PAUSA (p)" if paused else "ACTIVO (p)"
    if preview_only:
        mode += " | solo vista"
    thumb_hit = "-"
    if dbg.fist:
        if dbg.thumb_dy < -cfg.thumb_tilt:
            thumb_hit = "UP"
        elif dbg.thumb_dy > cfg.thumb_tilt:
            thumb_hit = "DOWN"
    swipe_ok = (
        dbg.open_palm
        and abs(dbg.trail_dx) >= cfg.swipe_min_dx
        and abs(dbg.trail_dy) <= cfg.swipe_max_dy
    )
    swipe_hit = "SWIPE" if swipe_ok else "-"
    flags = []
    if dbg.open_palm:
        flags.append("palm")
    if dbg.fist:
        flags.append("fist")
    flag_s = " ".join(flags) if flags else "-"
    return [
        f"{mode} | pose: {dbg.pose}",
        f"ultimo: {last_event or '-'}",
        (f"dedos IMRP={dbg.fingers}  gap {dbg.finger_gap:.2f} "
         f"[{dbg.spread or '-'}]  juntos<{cfg.finger_together:.2f} sep>{cfg.finger_apart:.2f}"),
        (f"alcance I {dbg.reach_i:.2f}/{dbg.base_i:.2f}{' [ABAJO]' if dbg.idx_down else ''}  "
         f"M {dbg.reach_m:.2f}/{dbg.base_m:.2f}{' [ABAJO]' if dbg.mid_down else ''}  "
         f"(abajo<{cfg.down_frac:.2f})"),
        (f"thumb_dy {dbg.thumb_dy:+.2f}  tilt={cfg.thumb_tilt:.2f}  "
         f"[{thumb_hit}]  (UP si < -{cfg.thumb_tilt:.2f})"),
        (f"trail dx={dbg.trail_dx:+.2f} dy={dbg.trail_dy:+.2f}  "
         f"|dx|>={cfg.swipe_min_dx:.2f} |dy|<={cfg.swipe_max_dy:.2f}  [{swipe_hit}]"),
        (f"estado: {dbg.mouse_state}  toque {dbg.dip_s:.2f}s ({dbg.dip_dominant or '-'})"
         f"  cursor: {dbg.cursor_mode or '-'}"),
        (f"pausa (cuernos): {dbg.toggle_progress * 100:.0f}%" if dbg.toggle_progress > 0 else
         "pausa: indice+menique 1 s"),
        f"flags: {flag_s}",
        "clic o p/espacio: pausa   q: salir",
    ]


def _line_color(line: str) -> Tuple[int, int, int]:
    if "[ABAJO]" in line or "[UP]" in line or "[DOWN]" in line or "[SWIPE]" in line:
        return _WARN
    if line.startswith("PAUSA") or line.startswith("ACTIVO"):
        return _OK
    return _IDLE


def draw_hud(frame, lines: List[str]) -> None:
    import cv2

    pad, lh = 8, 22
    font = cv2.FONT_HERSHEY_SIMPLEX
    width = max(cv2.getTextSize(s, font, 0.5, 1)[0][0] for s in lines) + pad * 2
    height = lh * len(lines) + pad
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (width, height), _BG, -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
    for i, line in enumerate(lines):
        y = pad + (i + 1) * lh - 6
        cv2.putText(frame, line, (pad, y), font, 0.5, _line_color(line), 1, cv2.LINE_AA)
