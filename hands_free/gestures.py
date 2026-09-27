"""Deteccion de gestos a partir de los 21 landmarks de MediaPipe Hands.

Este modulo NO toca el sistema operativo: solo convierte landmarks en eventos
(Gesture) y en un estado de cursor (CursorState). Asi se puede probar y ajustar
sin mover el raton de verdad.

Esquema de gestos (indice = I, medio = M):

  I+M arriba y JUNTOS      -> mover el cursor
     bajar I+M (y subir)   -> clic izquierdo         (2 veces: doble clic)
     bajar solo M (y subir)-> clic derecho
     bajar I+M y mantener + mover la mano -> arrastrar
  I+M arriba y SEPARADOS   -> cambio de aplicacion: bajar el dedo izq/der = paso atras/adelante
  puno + pulgar arriba/abajo -> scroll
  palma abierta deslizada  -> pestana anterior/siguiente
  puno neutral             -> reposo (no hace nada)
  indice + menique ("cuernos") mantenidos -> pausar / reanudar

Robustez frente al ruido real de MediaPipe:
  * Cada dedo se clasifica con HISTERESIS (dos umbrales) para que no parpadee.
  * "Dedo abajo" se mide RELATIVO a como estaba ese mismo dedo cuando estaba arriba
    (alcance punta-nudillo / tamano de mano), asi vale tanto doblar el dedo como
    bajarlo desde el nudillo (el dedo se acorta en la imagen).
  * Clic izquierdo vs derecho se decide por el TIEMPO que pasa cada combinacion de
    dedos abajo durante el toque, no por el primer frame (los dedos rara vez bajan
    exactamente a la vez).
  * Juntos/separados usa la mediana de la separacion de las puntas en los ultimos frames;
    izquierda/derecha usa las PUNTAS (bien separadas), no los nudillos (casi pegados).
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from .config import Config

# Indices de landmarks de MediaPipe
WRIST, THUMB_MCP, THUMB_TIP = 0, 2, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_MCP, RING_PIP, RING_TIP = 13, 14, 16
PINKY_MCP, PINKY_PIP, PINKY_TIP = 17, 18, 20

FINGERS = [(INDEX_PIP, INDEX_TIP), (MIDDLE_PIP, MIDDLE_TIP),
           (RING_PIP, RING_TIP), (PINKY_PIP, PINKY_TIP)]
_MCP_TIP = ((INDEX_MCP, INDEX_TIP), (MIDDLE_MCP, MIDDLE_TIP),
            (RING_MCP, RING_TIP), (PINKY_MCP, PINKY_TIP))


class Gesture(Enum):
    CLICK = auto()          # I+M bajan y suben
    SCROLL_UP = auto()
    SCROLL_DOWN = auto()
    SWIPE_LEFT = auto()
    SWIPE_RIGHT = auto()
    APP_NEXT = auto()       # dos dedos separados: baja el dedo derecho
    APP_PREV = auto()       # dos dedos separados: baja el dedo izquierdo
    RIGHT_CLICK = auto()    # dos dedos juntos: baja solo el medio y sube
    DOUBLE_CLICK = auto()   # segundo clic rapido: completa el doble clic del sistema
    TOGGLE_PAUSE = auto()   # cuernos (indice + menique) mantenidos: pausar / reanudar
    ZOOM_IN = auto()        # dos manos, modo dos manos: pellizco en ambas y SEPARARLAS
    ZOOM_OUT = auto()       # pellizco en ambas manos y ACERCARLAS


@dataclass
class Detection:
    gesture: Optional[Gesture]  # evento a ejecutar en este frame (o None)
    pose: str                   # pose actual, para mostrar en pantalla
    hand_present: bool


@dataclass
class DebugInfo:
    """Valores numericos por frame para el HUD. NO forma parte de Detection.

    Se lee en `detector.debug` justo despues de `detector.update(...)`.
    """
    hand_present: bool = False
    pose: str = "sin mano"
    pinch_ratio: float = 0.0   # (obsoleto, informativo) dist(pulgar,indice)/tamano_mano
    pinch_mid_ratio: float = 0.0  # (obsoleto, informativo)
    thumb_dy: float = 0.0      # inclinacion del pulgar / tamano_mano. < -thumb_tilt = arriba
    trail_dx: float = 0.0      # desplazamiento horizontal de la palma en la ventana (frac. ancho)
    trail_dy: float = 0.0      # desplazamiento vertical de la palma en la ventana
    pinching: bool = False     # (obsoleto) siempre False
    open_palm: bool = False
    fist: bool = False         # los 4 dedos largos cerrados
    two_fingers: bool = False  # indice y medio arriba
    finger_drop: str = ""      # "left"/"right": dedo bajado en el modo separado
    tap_armed: bool = False    # armado (dos dedos arriba el tiempo suficiente)
    cursor_mode: str = ""      # "move" | "drag" | ""
    finger_gap: float = 0.0    # dist(punta indice, punta medio)/tamano_mano (este frame)
    spread: str = ""           # "together" | "apart"  (segun la mediana reciente)
    mouse_state: str = "idle"  # idle | armed | dip | drag
    toggle_progress: float = 0.0  # 0-1 mantenimiento del gesto de pausa
    fingers: str = "0000"      # I M R P: 1 = extendido (con histeresis)
    reach_i: float = 0.0       # dist(punta, nudillo)/tamano_mano del indice
    reach_m: float = 0.0
    base_i: float = 0.0        # alcance de referencia con el dedo arriba
    base_m: float = 0.0
    idx_down: bool = False     # indice "abajo" (relativo a su referencia)
    mid_down: bool = False
    dip_s: float = 0.0         # duracion del toque en curso
    dip_dominant: str = ""     # both | mid | idx: combinacion de dedos abajo mas larga


@dataclass
class CursorState:
    """Posicion de control del raton este frame. Se lee en `detector.cursor`.

    x, y: nudillo del indice normalizado 0-1 (ya suavizado). El movimiento es RELATIVO:
    ActionExecutor mueve el cursor por la diferencia entre frames consecutivos activos.
    """
    active: bool = False
    x: float = 0.0
    y: float = 0.0
    dragging: bool = False     # boton pulsado (arrastre)
    mode: str = ""             # "move" | "drag" | ""


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _hand_size(lm) -> float:
    return max(_dist(lm[WRIST], lm[MIDDLE_MCP]), 1e-6)


def _median(vals):
    s = sorted(vals)
    return s[len(s) // 2]


def _ema_point(prev, p, alpha: float):
    """Suaviza un punto (x, y) con media movil exponencial. `prev=None` ancla sin salto."""
    if prev is None:
        return (p.x, p.y)
    return (alpha * p.x + (1 - alpha) * prev[0], alpha * p.y + (1 - alpha) * prev[1])


class GestureDetector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ext_state = [False] * 4          # extendido por dedo (con histeresis)
        # scroll
        self._thumb_state: Optional[Gesture] = None
        self._thumb_since = 0.0
        self._last_scroll = 0.0
        self._use_hand_axis = False
        # palma / paginas
        self._trail: deque = deque()  # (t, x, y) de la palma abierta
        self._last_swipe = 0.0
        self._swipe_armed = True
        # raton (dos dedos)
        self._mstate = "idle"          # idle | armed | dip | drag
        self._spread = "together"      # con histeresis sobre la mediana
        self._armed_spread = "together"
        self._both_since: Optional[float] = None
        self._ref: deque = deque()     # (t, reach_i, reach_m, gap, dx_puntas) con los dedos arriba
        self._base = None              # (alcance_ref_indice, alcance_ref_medio)
        self._idx_left = True          # el indice esta a la izquierda del medio (por las puntas)
        self._idx_down = False
        self._mid_down = False
        self._dip_since = 0.0
        self._dip_last = 0.0
        self._dip_prev: Optional[str] = None
        self._bucket = {"both": 0.0, "mid": 0.0, "idx": 0.0}
        self._dip_xy = (0.0, 0.0)
        self._dip_thumb_since: Optional[float] = None
        self._drag_up_since: Optional[float] = None
        self._last_click = 0.0
        self._click_count = 0
        self._click_pos = (0.0, 0.0)
        self._last_rclick = 0.0
        # cambio de app (dos dedos separados)
        self._drop_side: Optional[str] = None
        self._drop_since = 0.0
        self._tap_hold = False
        self._last_tap = 0.0
        # pausa
        self._horns_since: Optional[float] = None
        self._horns_fired = False
        self._last_toggle = -1e9
        # cursor
        self._cursor_xy = None
        self.cursor = CursorState()
        self.debug = DebugInfo()

    # ------------------------------------------------------------------ utilidades
    def _classify_fingers(self, lm, size: float):
        """Extendido por dedo con histeresis. Devuelve (ext, reach)."""
        cfg = self.cfg
        reach = []
        for k, ((pip, tip), (mcp, _)) in enumerate(zip(FINGERS, _MCP_TIP)):
            ratio = _dist(lm[tip], lm[WRIST]) / max(_dist(lm[pip], lm[WRIST]), 1e-6)
            rc = _dist(lm[tip], lm[mcp]) / size
            reach.append(rc)
            if self._ext_state[k]:
                self._ext_state[k] = not (ratio < cfg.ext_off or rc < cfg.reach_off)
            else:
                self._ext_state[k] = ratio > cfg.ext_on and rc > cfg.reach_on
        return list(self._ext_state), reach

    def _thumb_dy(self, lm, size: float) -> float:
        """Inclinacion del pulgar / tamano_mano. Negativo = 'arriba', positivo = 'abajo'.

        'image': usa el eje Y de la imagen. 'hand': usa el eje muneca->nudillo del medio,
        asi funciona con la mano girada (de lado, camara inclinada). Con la mano vertical
        ambos coinciden.
        """
        vx = lm[THUMB_TIP].x - lm[THUMB_MCP].x
        vy = lm[THUMB_TIP].y - lm[THUMB_MCP].y
        image_dy = vy / size
        mode = self.cfg.thumb_axis
        if mode == "image":
            return image_dy
        ux = lm[MIDDLE_MCP].x - lm[WRIST].x
        uy = lm[MIDDLE_MCP].y - lm[WRIST].y
        n = max(math.hypot(ux, uy), 1e-9)
        hand_dy = -(vx * ux + vy * uy) / n / size
        if mode == "hand":
            return hand_dy
        # auto: sentado (mano casi vertical) se queda en Y de imagen. Solo de lado
        # (~90°) usa el eje de la mano. Histeresis evita que thumb_dy salte a 0.
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, -uy / n))))
        on = self.cfg.thumb_axis_tilt_deg
        off = max(0.0, on - self.cfg.thumb_axis_hysteresis_deg)
        if self._use_hand_axis:
            if tilt < off:
                self._use_hand_axis = False
        elif tilt > on:
            self._use_hand_axis = True
        # Solo se usa el eje de la mano si el pulgar realmente apunta a lo largo de el.
        # Un pulgar arriba real con los dedos de lado es perpendicular al eje de la mano
        # (hand_dy ~ 0) pero sigue apuntando arriba en la imagen: ahi gana image_dy.
        if self._use_hand_axis and abs(hand_dy) >= abs(image_dy):
            return hand_dy
        return image_dy

    def _set_cursor(self, lm, mode: str) -> None:
        # el nudillo del indice (INDEX_MCP) casi no se mueve al doblar los dedos
        self._cursor_xy = _ema_point(self._cursor_xy, lm[INDEX_MCP], self.cfg.move_smoothing)
        xy = self._cursor_xy
        self.cursor = CursorState(True, xy[0], xy[1], mode == "drag", mode)
        self.debug.cursor_mode = mode

    @property
    def dragging(self) -> bool:
        """Para el modo de dos manos: si esta mano esta en pleno arrastre (bajar ambos
        dedos, mantener y mover), independientemente de que su CursorState se use o no
        para mover el raton (en dos manos, la posicion la da la otra mano)."""
        return self._mstate == "drag"

    def _cancel_mouse(self) -> None:
        self._mstate = "idle"
        self._both_since = None
        self._ref.clear()
        self._base = None
        self._idx_down = self._mid_down = False
        self._dip_prev = None
        self._dip_thumb_since = None
        self._drag_up_since = None
        self._drop_side = None
        self._tap_hold = False

    def reset(self) -> None:
        self._ext_state = [False] * 4
        self._thumb_state = None
        self._use_hand_axis = False
        self._trail.clear()
        self._swipe_armed = True
        self._cancel_mouse()
        self._horns_since = None
        self._horns_fired = False
        self._cursor_xy = None

    # ------------------------------------------------------------------ API
    def update(self, lm, now: Optional[float] = None) -> Detection:
        """lm: lista de 21 landmarks normalizados (o None si no hay mano).

        Contrato estable: devuelve Detection(gesture, pose, hand_present).
        Los numeros de debug quedan en `self.debug` (DebugInfo) y el cursor en `self.cursor`.
        """
        now = time.monotonic() if now is None else now
        self.debug = DebugInfo()
        self.cursor = CursorState()
        det = self._update(lm, now)
        if not self.cursor.active:
            self._cursor_xy = None   # al reactivar, el movimiento relativo se re-ancla
        dbg = self.debug
        dbg.hand_present = det.hand_present
        dbg.pose = det.pose
        dbg.mouse_state = self._mstate
        dbg.tap_armed = self._mstate == "armed"
        if self._base is not None:
            dbg.base_i, dbg.base_m = self._base
        dbg.idx_down, dbg.mid_down = self._idx_down, self._mid_down
        if self._mstate == "dip":
            dbg.dip_s = now - self._dip_since
            dbg.dip_dominant = max(self._bucket, key=self._bucket.get) if any(self._bucket.values()) else ""
        return det

    # ------------------------------------------------------------------ nucleo
    def _update(self, lm, now: float) -> Detection:
        if lm is None:
            self.reset()
            return Detection(None, "sin mano", False)

        size = _hand_size(lm)
        dbg = self.debug
        ext, reach = self._classify_fingers(lm, size)
        dbg.fingers = "".join("1" if e else "0" for e in ext)
        dbg.reach_i, dbg.reach_m = reach[0], reach[1]
        dbg.open_palm = all(ext)
        dbg.fist = not any(ext)
        thumb_dy = self._thumb_dy(lm, size)
        dbg.thumb_dy = thumb_dy
        dbg.pinch_ratio = _dist(lm[THUMB_TIP], lm[INDEX_TIP]) / size
        dbg.pinch_mid_ratio = _dist(lm[THUMB_TIP], lm[MIDDLE_TIP]) / size
        gap = _dist(lm[INDEX_TIP], lm[MIDDLE_TIP]) / size
        dbg.finger_gap = gap

        # 0) Pausar / reanudar
        det = self._toggle_step(now, ext)
        if det is not None:
            return det

        # 1) Raton: dos dedos juntos (mover, clics, arrastre) o separados (cambio de app)
        det = self._mouse_step(lm, now, ext, gap, reach, thumb_dy)
        if det is not None:
            return det

        # 2) Puno NEUTRAL: 4 dedos plegados hasta la palma y pulgar sin apuntar arriba/abajo = reposo.
        fist_strict = all(_dist(lm[tip], lm[WRIST]) < _dist(lm[mcp], lm[WRIST]) for mcp, tip in _MCP_TIP)
        if fist_strict and dbg.fist and abs(thumb_dy) <= self.cfg.thumb_tilt:
            self._thumb_state = None
            self._trail.clear()
            self._swipe_armed = True
            return Detection(None, "puno (neutral)", True)

        # 3) Scroll: puno con el pulgar arriba/abajo
        wanted: Optional[Gesture] = None
        if dbg.fist:
            if thumb_dy < -self.cfg.thumb_tilt:
                wanted = Gesture.SCROLL_UP
            elif thumb_dy > self.cfg.thumb_tilt:
                wanted = Gesture.SCROLL_DOWN
        if wanted is not None:
            self._trail.clear()
            if wanted != self._thumb_state:
                self._thumb_state, self._thumb_since = wanted, now
            held = now - self._thumb_since >= self.cfg.scroll_hold_s
            if held and now - self._last_scroll >= self.cfg.scroll_interval_s:
                self._last_scroll = now
                return Detection(wanted, wanted.name.lower(), True)
            return Detection(None, wanted.name.lower(), True)
        self._thumb_state = None

        # 4) Palma abierta deslizada en horizontal: pestana anterior/siguiente
        if dbg.open_palm:
            c = lm[MIDDLE_MCP]
            self._trail.append((now, c.x, c.y))
            while self._trail and now - self._trail[0][0] > self.cfg.swipe_window_s:
                self._trail.popleft()
            if len(self._trail) >= 2:
                dbg.trail_dx = self._trail[-1][1] - self._trail[0][1]
                dbg.trail_dy = self._trail[-1][2] - self._trail[0][2]
            if not self._swipe_armed and len(self._trail) >= 2:
                # "quieta" = todo el recorrido reciente cabe en un cuadro pequeno (no solo inicio~fin:
                # agitar la mano de ida y vuelta termina cerca de donde empezo)
                span = now - self._trail[0][0]
                xs = [p[1] for p in self._trail]
                ys = [p[2] for p in self._trail]
                if (span >= self.cfg.swipe_rearm_still_s - 1e-6
                        and max(xs) - min(xs) < self.cfg.swipe_rearm_move
                        and max(ys) - min(ys) < self.cfg.swipe_rearm_move):
                    self._swipe_armed = True
            if (self._swipe_armed and len(self._trail) >= 4
                    and now - self._last_swipe >= self.cfg.swipe_cooldown_s):
                dx = self._trail[-1][1] - self._trail[0][1]
                dy = self._trail[-1][2] - self._trail[0][2]
                if abs(dx) >= self.cfg.swipe_min_dx and abs(dy) <= self.cfg.swipe_max_dy:
                    self._last_swipe = now
                    self._swipe_armed = False
                    self._trail.clear()
                    g = Gesture.SWIPE_RIGHT if dx > 0 else Gesture.SWIPE_LEFT
                    return Detection(g, "palma abierta", True)
            return Detection(None, "palma abierta", True)

        self._trail.clear()
        self._swipe_armed = True     # rompio la pose de palma: nuevo intento
        return Detection(None, "neutral", True)

    # ------------------------------------------------------------------ pausa
    def _toggle_step(self, now: float, ext) -> Optional[Detection]:
        i, m, r, p = ext
        horns = i and p and not m and not r
        if not horns:
            self._horns_since = None
            self._horns_fired = False
            return None
        if self._horns_since is None:
            self._horns_since = now
        held = now - self._horns_since
        self.debug.toggle_progress = min(1.0, held / max(self.cfg.toggle_hold_s, 1e-6))
        self._cancel_mouse()
        self._trail.clear()
        if (not self._horns_fired and held >= self.cfg.toggle_hold_s - 1e-6
                and now - self._last_toggle >= self.cfg.toggle_cooldown_s):
            self._horns_fired = True
            self._last_toggle = now
            return Detection(Gesture.TOGGLE_PAUSE, "pausa / activar", True)
        return Detection(None, "cuernos (mantener)", True)

    # ------------------------------------------------------------------ raton
    def _pose_two(self) -> str:
        return "dos dedos juntos" if self._spread == "together" else "dos dedos separados"

    def _refresh_ref(self, now: float, reach, gap: float, lm) -> None:
        """Actualiza la referencia (alcance con los dedos arriba, separacion, lado)."""
        cfg = self.cfg
        self._ref.append((now, reach[0], reach[1], gap, lm[INDEX_TIP].x - lm[MIDDLE_TIP].x))
        while self._ref and now - self._ref[0][0] > cfg.ref_window_s:
            self._ref.popleft()
        n = len(self._ref)
        q = int(0.75 * (n - 1))
        self._base = (sorted(r[1] for r in self._ref)[q], sorted(r[2] for r in self._ref)[q])
        recent = [r for r in self._ref if now - r[0] <= cfg.spread_window_s] or [self._ref[-1]]
        med_gap = _median([r[3] for r in recent])
        if med_gap < cfg.finger_together:
            self._spread = "together"
        elif med_gap > cfg.finger_apart:
            self._spread = "apart"
        self._idx_left = _median([r[4] for r in recent]) < 0

    def _update_down(self, reach, i: bool, m: bool):
        """Dedo 'abajo' relativo a su referencia, con histeresis."""
        cfg = self.cfg
        bi, bm = self._base
        fi = reach[0] / bi if bi > 1e-6 else 1.0
        fm = reach[1] / bm if bm > 1e-6 else 1.0
        if self._idx_down:
            self._idx_down = not (fi > cfg.up_frac and i)
        else:
            self._idx_down = fi < cfg.down_frac or not i
        if self._mid_down:
            self._mid_down = not (fm > cfg.up_frac and m)
        else:
            self._mid_down = fm < cfg.down_frac or not m
        return self._idx_down, self._mid_down

    @staticmethod
    def _bucket_of(down_i: bool, down_m: bool) -> Optional[str]:
        if down_i and down_m:
            return "both"
        if down_m:
            return "mid"
        if down_i:
            return "idx"
        return None

    def _left_click(self, lm, now: float) -> Optional[Detection]:
        cfg = self.cfg
        gap = now - self._last_click
        here = (lm[INDEX_MCP].x, lm[INDEX_MCP].y)
        moved = math.hypot(here[0] - self._click_pos[0], here[1] - self._click_pos[1])
        if (self._click_count == 1 and cfg.double_click_min_gap_s <= gap <= cfg.double_click_window_s
                and moved <= cfg.double_click_max_move):
            self._last_click = now
            self._click_count = 2
            return Detection(Gesture.DOUBLE_CLICK, "doble clic", True)
        if self._click_count == 2 and gap <= cfg.double_click_window_s:
            return None                       # tercer clic rapido: se ignora
        if gap >= cfg.click_cooldown_s:
            self._last_click = now
            self._click_count = 1
            self._click_pos = here
            return Detection(Gesture.CLICK, "clic", True)
        return None

    def _finish_dip(self, lm, now: float) -> Optional[Detection]:
        """Los dedos volvieron a subir: si fue un toque breve, decide clic izquierdo o derecho."""
        cfg = self.cfg
        total = now - self._dip_since
        if total < cfg.dip_min_s - 1e-6 or total > cfg.click_max_down_s + 1e-6:
            return None
        both, mid, idx = self._bucket["both"], self._bucket["mid"], self._bucket["idx"]
        need = cfg.dip_min_s * 0.6
        if both >= need and both > max(mid, idx):
            return self._left_click(lm, now)
        if mid >= need and mid > max(both, idx) and now - self._last_rclick >= cfg.click_cooldown_s:
            self._last_rclick = now
            return Detection(Gesture.RIGHT_CLICK, "clic derecho", True)
        return None

    def _mouse_step(self, lm, now: float, ext, gap: float, reach, thumb_dy: float) -> Optional[Detection]:
        """Maquina de estados de los dos dedos. Devuelve Detection si consume el frame."""
        cfg, dbg = self.cfg, self.debug
        i, m, r, p = ext
        palm_like = r and p                      # anular y menique arriba: es una palma, no dos dedos
        both_up_abs = i and m and not palm_like
        st = self._mstate

        # ---- reposo: esperar a que los dos dedos lleven arriba `arm_s`
        if st == "idle":
            if not both_up_abs:
                self._both_since = None
                return None
            self._refresh_ref(now, reach, gap, lm)
            dbg.spread = self._spread
            dbg.two_fingers = True
            if self._both_since is None:
                self._both_since = now
            if now - self._both_since >= cfg.arm_s - 1e-6:
                self._mstate = "armed"
                self._idx_down = self._mid_down = False
                self._armed_spread = self._spread
                if self._spread == "together":
                    self._set_cursor(lm, "move")
            return Detection(None, self._pose_two(), True)

        if palm_like or self._base is None:
            self._cancel_mouse()
            return None
        down_i, down_m = self._update_down(reach, i, m)
        dbg.two_fingers = True
        dbg.spread = self._spread

        # ---- armado: ambos arriba, o alguno bajando
        if st == "armed":
            if not down_i and not down_m:
                if both_up_abs:
                    self._refresh_ref(now, reach, gap, lm)
                    dbg.spread = self._spread
                self._armed_spread = self._spread
                self._tap_hold = False
                self._drop_side = None
                if self._spread == "together":
                    self._set_cursor(lm, "move")
                return Detection(None, self._pose_two(), True)
            if self._armed_spread == "together":
                self._mstate = "dip"
                self._dip_since = self._dip_last = now
                self._dip_prev = self._bucket_of(down_i, down_m)
                self._bucket = {"both": 0.0, "mid": 0.0, "idx": 0.0}
                self._dip_xy = (lm[INDEX_MCP].x, lm[INDEX_MCP].y)
                self._dip_thumb_since = None
                return Detection(None, "dedos abajo", True)
            return self._tab_step(now, down_i, down_m)

        # ---- toque en curso (dedos juntos): acumular tiempo por combinacion
        if st == "dip":
            dt = now - self._dip_last
            self._dip_last = now
            if self._dip_prev is not None:
                self._bucket[self._dip_prev] += dt
            cur = self._bucket_of(down_i, down_m)
            self._dip_prev = cur
            if cur is None:                       # los dos subieron: fin del toque
                ret = self._finish_dip(lm, now)
                self._mstate = "armed"
                self._armed_spread = self._spread
                if self._spread == "together":
                    self._set_cursor(lm, "move")
                return ret if ret is not None else Detection(None, self._pose_two(), True)
            total = now - self._dip_since
            dominant = max(self._bucket, key=self._bucket.get)
            # Puno real para hacer scroll (los 4 dedos abajo Y el pulgar claramente
            # arriba/abajo), no un clic: sin esto se queda "atascado" aqui esperando el
            # timeout de clic/arrastre (hasta drag_window_s = 2 s) antes de dejar pasar el
            # scroll, lo que se sentia como que el puno "hacia" el gesto de mover el cursor.
            if dominant == "both" and abs(thumb_dy) > cfg.thumb_tilt:
                if self._dip_thumb_since is None:
                    self._dip_thumb_since = now
                elif now - self._dip_thumb_since >= cfg.fist_scroll_break_s - 1e-6:
                    self._mstate = "idle"
                    self._both_since = None
                    self._dip_thumb_since = None
                    return None
            else:
                self._dip_thumb_since = None
            if (cfg.drag_enabled and dominant == "both" and total >= cfg.drag_hold_s - 1e-6):
                moved = math.hypot(lm[INDEX_MCP].x - self._dip_xy[0], lm[INDEX_MCP].y - self._dip_xy[1])
                if moved >= cfg.drag_move:
                    self._mstate = "drag"
                    self._drag_up_since = None
                    self._set_cursor(lm, "drag")
                    return Detection(None, "arrastrar", True)
            drag_possible = cfg.drag_enabled and dominant == "both"
            if total > cfg.drag_window_s or (total > cfg.click_max_down_s and not drag_possible):
                self._mstate = "idle"
                self._both_since = None
                return None
            return Detection(None, "dedos abajo", True)

        # ---- arrastre: el boton sigue pulsado hasta que los dos dedos suben un momento
        if st == "drag":
            if down_i or down_m:
                self._drag_up_since = None
                self._set_cursor(lm, "drag")
                return Detection(None, "arrastrar", True)
            if self._drag_up_since is None:
                self._drag_up_since = now
            if now - self._drag_up_since >= cfg.drag_release_s - 1e-6:
                self._mstate = "armed"
                self._armed_spread = self._spread
                if self._spread == "together":
                    self._set_cursor(lm, "move")
                return Detection(None, self._pose_two(), True)
            self._set_cursor(lm, "drag")
            return Detection(None, "arrastrar", True)
        return None

    def _tab_step(self, now: float, down_i: bool, down_m: bool) -> Detection:
        """Dos dedos SEPARADOS: bajar uno cambia de aplicacion (izquierdo = atras, derecho = adelante)."""
        cfg, dbg = self.cfg, self.debug
        if down_i == down_m:                      # los dos abajo: no es un toque
            self._drop_side = None
            return Detection(None, "dedos abajo", True)
        dropped_is_index = down_i
        side = "left" if dropped_is_index == self._idx_left else "right"
        dbg.finger_drop = side
        label = f"dedo {'izq' if side == 'left' else 'der'}"
        if side != self._drop_side:
            self._drop_side, self._drop_since = side, now
        if (not self._tap_hold
                and now - self._drop_since >= cfg.app_tap_confirm_s - 1e-6
                and now - self._last_tap >= cfg.app_tap_cooldown_s - 1e-6):
            self._last_tap = now
            self._tap_hold = True
            g = Gesture.APP_NEXT if side == "right" else Gesture.APP_PREV
            return Detection(g, label, True)
        return Detection(None, label, True)


class CursorTracker:
    """Una mano SOLO mueve el cursor: mientras este visible lo sigue (igual que el modo
    "mover" de una sola mano), sin clic, arrastre ni ningun otro gesto; al perderla de
    vista se desactiva y se reengancha sin salto cuando reaparece.

    NOTA: `main.py` HOY NO usa esta clase (`cfg.two_hand_mode` reparte "una mano = todo,
    dos manos = solo zoom", ver TwoHandZoom mas abajo, para no confundir mover el cursor
    con el pellizco del zoom). Se deja aqui, probada, por si mas adelante hace falta un
    modo que reparta roles entre las dos manos otra vez:

        pos = cursor_tracker.update(lm_mano_cursor)
        det = gesture_hand.update(lm_mano_gestos, now=now)
        final = CursorState(pos.active, pos.x, pos.y, gesture_hand.dragging, pos.mode)
        actions.update_cursor(final)
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._xy = None
        self.cursor = CursorState()

    def update(self, lm) -> CursorState:
        if lm is None:
            self._xy = None
            self.cursor = CursorState()
            return self.cursor
        self._xy = _ema_point(self._xy, lm[INDEX_MCP], self.cfg.move_smoothing)
        self.cursor = CursorState(True, self._xy[0], self._xy[1], False, "move")
        return self.cursor

    def reset(self) -> None:
        self._xy = None
        self.cursor = CursorState()


def _pinch_ratio(lm) -> float:
    return _dist(lm[THUMB_TIP], lm[INDEX_TIP]) / _hand_size(lm)


def _pinch_point(lm):
    t, i = lm[THUMB_TIP], lm[INDEX_TIP]
    return ((t.x + i.x) / 2.0, (t.y + i.y) / 2.0)


class TwoHandZoom:
    """Modo de dos manos: pellizco (pulgar+indice) en AMBAS manos A LA VEZ. Acercarlas o
    separarlas hace zoom (Ctrl + rueda). Mientras las dos esten pellizcando, esto manda
    sobre el cursor y los gestos normales de esas manos (en main.py: si `zoom.active`,
    no se mueve el raton ni se procesan sus otros gestos ese frame). En cuanto UNA se
    suelta se apaga solo, sin dejar nada a medias, y hay que pellizcar con las dos otra
    vez para reactivarlo (asi no se dispara zoom por un pellizco de una sola mano).
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._active = False
        self._ref_dist: Optional[float] = None

    @property
    def active(self) -> bool:
        return self._active

    def update(self, lm_a, lm_b) -> Optional[Gesture]:
        """lm_a, lm_b: landmarks de cada mano (o None si no se ve). El orden no importa."""
        pinching_a = lm_a is not None and _pinch_ratio(lm_a) < self.cfg.zoom_pinch_ratio
        pinching_b = lm_b is not None and _pinch_ratio(lm_b) < self.cfg.zoom_pinch_ratio
        if not (pinching_a and pinching_b):
            self._active = False
            self._ref_dist = None
            return None
        pa, pb = _pinch_point(lm_a), _pinch_point(lm_b)
        dist = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
        if not self._active:
            self._active = True     # primer frame pellizcando con las dos: solo fija la referencia
            self._ref_dist = dist
            return None
        delta = dist - self._ref_dist
        step = self.cfg.zoom_step
        if delta >= step:
            self._ref_dist = dist
            return Gesture.ZOOM_IN
        if delta <= -step:
            self._ref_dist = dist
            return Gesture.ZOOM_OUT
        return None

    def reset(self) -> None:
        self._active = False
        self._ref_dist = None
