"""Landmarks sinteticos (21 puntos, coordenadas normalizadas 0-1 como MediaPipe).

Sirven para probar GestureDetector sin camara. Cada landmark es un objeto con
.x .y .z. Convencion de imagen: x crece a la derecha, y crece HACIA ABAJO.

Geometria base (tamano de mano = dist(muneca, MCP del medio) = HAND_SIZE):
  muneca en (cx, cy + HAND_SIZE); MCP del medio en (cx, cy); dedos apuntan arriba.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

HAND_SIZE = 0.15

# indice de landmark -> (offset x del dedo respecto a cx)
_FINGER_X = {"index": -0.03, "middle": 0.0, "ring": 0.03, "pinky": 0.06}
# (mcp, pip, dip, tip)
_FINGER_IDX = {
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}


@dataclass
class LM:
    x: float
    y: float
    z: float = 0.0


def make_hand(
    cx: float = 0.5,
    cy: float = 0.5,
    *,
    index: bool = False,
    middle: bool = False,
    ring: bool = False,
    pinky: bool = False,
    thumb: str = "neutral",      # "neutral" | "up" | "down" | "pinch"
    pinch_ratio: float = 0.10,   # solo con thumb="pinch": dist(pulgar,dedo)/HAND_SIZE
    pinch_finger: str = "index",  # con thumb="pinch": "index" o "middle"
    spread: float = 0.0,          # separa la PUNTA del indice hacia la izquierda (dedos en V)
) -> List[LM]:
    """Construye una mano. index/middle/ring/pinky=True significa dedo extendido."""
    s = HAND_SIZE
    wy = cy + s
    lm = [LM(cx, wy) for _ in range(21)]
    lm[0] = LM(cx, wy)  # muneca

    ext = {"index": index, "middle": middle, "ring": ring, "pinky": pinky}
    for name, (mcp, pip, dip, tip) in _FINGER_IDX.items():
        x = cx + _FINGER_X[name]
        lm[mcp] = LM(x, cy)
        if ext[name]:   # extendido: punta lejos de la muneca
            sx = spread if name == "index" else 0.0
            lm[pip] = LM(x - sx * 0.5, wy - 1.45 * s)
            lm[dip] = LM(x - sx * 0.75, wy - 1.75 * s)
            lm[tip] = LM(x - sx, wy - 2.05 * s)
        else:           # curvado: punta plegada cerca de la muneca
            lm[pip] = LM(x, wy - 1.05 * s)
            lm[dip] = LM(x, wy - 0.85 * s)
            lm[tip] = LM(x, wy - 0.65 * s)

    # Pulgar: 1=CMC, 2=MCP, 3=IP, 4=TIP
    mx, my = cx - 0.06, wy - 0.04
    lm[1] = LM(cx - 0.04, wy - 0.01)
    lm[2] = LM(mx, my)
    if thumb == "up":
        lm[3] = LM(mx - 0.005, my - 0.05)
        lm[4] = LM(mx - 0.01, my - 0.10)      # thumb_dy = -0.10/0.15 ~ -0.67
    elif thumb == "down":
        lm[3] = LM(mx - 0.005, my + 0.05)
        lm[4] = LM(mx - 0.01, my + 0.10)      # thumb_dy ~ +0.67
    elif thumb == "pinch":
        t = lm[12] if pinch_finger == "middle" else lm[8]   # junto a la punta del dedo
        lm[4] = LM(t.x - pinch_ratio * s, t.y)
        lm[3] = LM((lm[2].x + lm[4].x) / 2, (lm[2].y + lm[4].y) / 2)
    else:  # neutral: pulgar recogido al costado, thumb_dy ~ 0
        lm[3] = LM(mx - 0.02, my)
        lm[4] = LM(mx - 0.04, my)
    return lm


def rotate(lm: List[LM], deg: float) -> List[LM]:
    """Gira la mano `deg` grados (sentido horario en pantalla) alrededor de la muneca.

    Simula mano de lado / camara inclinada. Mantiene las coordenadas dentro de 0-1
    si la mano original esta centrada (cx=0.5, cy=0.5).
    """
    import math
    c, sn = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    px, py = lm[0].x, lm[0].y
    return [LM(px + (p.x - px) * c - (p.y - py) * sn,
               py + (p.x - px) * sn + (p.y - py) * c, p.z) for p in lm]


# --- Poses estaticas ---------------------------------------------------------
def pinch(ratio: float = 0.10) -> List[LM]:
    """Pellizco: indice extendido y pulgar a `ratio` de distancia (relativa)."""
    return make_hand(index=True, thumb="pinch", pinch_ratio=ratio)

def fist_thumb_up() -> List[LM]:
    return make_hand(thumb="up")

def fist_thumb_down() -> List[LM]:
    return make_hand(thumb="down")

def fist_neutral(cx: float = 0.5, cy: float = 0.5) -> List[LM]:
    return make_hand(cx, cy, thumb="neutral")

def open_palm(cx: float = 0.5, cy: float = 0.5) -> List[LM]:
    return make_hand(cx, cy, index=True, middle=True, ring=True, pinky=True)


# --- Secuencias (una lista de frames; el test decide los timestamps) ---------
def _lerp(a: float, b: float, i: int, n: int) -> float:
    return a + (b - a) * i / (n - 1)

def swipe_right(n: int = 9, x0: float = 0.25, x1: float = 0.75) -> List[List[LM]]:
    """Palma abierta que se desliza a la derecha (dx = x1-x0 = 0.5 en n frames)."""
    return [open_palm(_lerp(x0, x1, i, n)) for i in range(n)]

def swipe_left(n: int = 9, x0: float = 0.75, x1: float = 0.25) -> List[List[LM]]:
    return [open_palm(_lerp(x0, x1, i, n)) for i in range(n)]

def rising_open_palm(n: int = 9, y0: float = 0.7, y1: float = 0.3) -> List[List[LM]]:
    """Palma abierta que sube en vertical: NO debe ser swipe ni scroll."""
    return [open_palm(0.5, _lerp(y0, y1, i, n)) for i in range(n)]

def rising_fist(n: int = 9, y0: float = 0.7, y1: float = 0.3) -> List[List[LM]]:
    """Puno (pulgar neutro) que sube: NO debe ser scroll."""
    return [fist_neutral(0.5, _lerp(y0, y1, i, n)) for i in range(n)]

def still_palm(n: int = 20) -> List[List[LM]]:
    """Palma abierta quieta: NO debe ser swipe."""
    return [open_palm() for _ in range(n)]


def fist_sideways_thumb(direction: str = "up") -> List[LM]:
    """Puno con los dedos apuntando a un lado (muneca->nudillo horizontal) y el pulgar
    apuntando arriba/abajo EN LA IMAGEN, perpendicular al eje de la mano. Es la forma
    real de un 'pulgar arriba' y rompe cualquier eje basado solo en muneca->nudillo."""
    lm = rotate(fist_neutral(), 90)
    mcp = lm[2]
    dy = -0.10 if direction == "up" else 0.10
    lm[3] = LM(mcp.x, mcp.y + dy / 2)
    lm[4] = LM(mcp.x, mcp.y + dy)
    return lm


def two_fingers(cx: float = 0.5, cy: float = 0.5) -> List[LM]:
    """Indice y medio extendidos, anular y menique cerrados (signo de paz)."""
    return make_hand(cx, cy, index=True, middle=True)


def two_fingers_drop(side: str, cx: float = 0.5, cy: float = 0.5) -> List[LM]:
    """Indice+medio arriba y UNO bajado. En la fixture el indice queda a la izquierda
    de la imagen y el medio a la derecha: side='left' baja el indice, 'right' el medio."""
    return make_hand(cx, cy, index=(side != "left"), middle=(side != "right"))


def mirror_x(lm: List[LM]) -> List[LM]:
    """Refleja la mano horizontalmente (equivale a la otra mano: el medio queda a la izquierda del indice)."""
    return [LM(1.0 - p.x, p.y, p.z) for p in lm]


def pointing(cx: float = 0.5, cy: float = 0.5) -> List[LM]:
    """Solo el indice extendido, pulgar recogido (mueve el cursor)."""
    return make_hand(cx, cy, index=True)


def pinch_at(cx: float = 0.5, cy: float = 0.5, ratio: float = 0.10) -> List[LM]:
    """Pellizco en la posicion (cx, cy)."""
    return make_hand(cx, cy, index=True, thumb="pinch", pinch_ratio=ratio)


def pinch_middle(cx: float = 0.5, cy: float = 0.5, ratio: float = 0.10) -> List[LM]:
    """Pulgar + dedo medio (medio extendido, indice/anular/menique cerrados)."""
    return make_hand(cx, cy, middle=True, thumb="pinch", pinch_ratio=ratio, pinch_finger="middle")


# --- Esquema de dos dedos ---------------------------------------------------
def two_together(cx: float = 0.5, cy: float = 0.5) -> List[LM]:
    """Indice y medio arriba y JUNTOS (gap ~0.2 tamanos de mano): mover / clics."""
    return make_hand(cx, cy, index=True, middle=True)


def two_apart(cx: float = 0.5, cy: float = 0.5, spread: float = 0.05) -> List[LM]:
    """Indice y medio arriba y SEPARADOS en V (gap ~0.53): cambio de aplicacion."""
    return make_hand(cx, cy, index=True, middle=True, spread=spread)


def two_drop(side: str, cx: float = 0.5, cy: float = 0.5, spread: float = 0.0) -> List[LM]:
    """Uno de los dos dedos bajado. En la fixture el indice esta a la izquierda de la imagen y el
    medio a la derecha: side='left' baja el indice, 'right' baja el medio."""
    return make_hand(cx, cy, index=(side != "left"), middle=(side != "right"), spread=spread)


def horns(cx: float = 0.5, cy: float = 0.5) -> List[LM]:
    """Indice + menique extendidos, medio y anular cerrados (gesto de pausa)."""
    return make_hand(cx, cy, index=True, pinky=True)


def pivot(lm: List[LM], factor: float = 0.5, fingers=("index", "middle")) -> List[LM]:
    """Dedos que bajan desde el NUDILLO sin doblarse: en la imagen se acortan (foreshortening).
    Escala PIP/DIP/punta hacia el nudillo. El alcance cae a `factor` pero la punta sigue mas
    lejos de la muneca que el PIP, asi que una regla absoluta los seguiria viendo 'arriba'."""
    out = [LM(p.x, p.y, p.z) for p in lm]
    for f in fingers:
        mcp, pip, dip, tip = _FINGER_IDX[f]
        m = out[mcp]
        for k in (pip, dip, tip):
            out[k] = LM(m.x + (out[k].x - m.x) * factor, m.y + (out[k].y - m.y) * factor)
    return out
