"""Punto de entrada. Foco en la ventana de la camara:
   clic o p / espacio = pausar/reanudar     q o ESC = salir
"""
from __future__ import annotations

import sys

import cv2
import mediapipe as mp

from hands_free.actions import ActionExecutor
from hands_free.config import Config
from hands_free.gestures import Gesture, GestureDetector
from hands_free.hud import draw_hud, hud_lines

WINDOW = "Hands-Free Navigator"


def main() -> int:
    cfg = Config()
    cap = cv2.VideoCapture(cfg.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.frame_height)
    if not cap.isOpened():
        print("No se pudo abrir la camara. Cambia camera_index en config.py.")
        return 1

    hands = mp.solutions.hands.Hands(
        max_num_hands=cfg.max_hands,
        min_detection_confidence=cfg.detection_confidence,
        min_tracking_confidence=cfg.tracking_confidence,
    )
    drawer = mp.solutions.drawing_utils
    detector = GestureDetector(cfg)
    actions = ActionExecutor(cfg)
    state = {"paused": cfg.start_paused}
    last_event = ""

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    def toggle_pause() -> None:
        state["paused"] = not state["paused"]
        detector.reset()
        print("PAUSA" if state["paused"] else "ACTIVO", flush=True)

    def on_mouse(event, _x, _y, _flags, _param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            toggle_pause()

    cv2.setMouseCallback(WINDOW, on_mouse)
    print("Clic en la ventana de la camara, o pulsa p / espacio. q sale.", flush=True)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if cfg.mirror:
                frame = cv2.flip(frame, 1)

            result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            hand = result.multi_hand_landmarks[0] if result.multi_hand_landmarks else None
            det = detector.update(hand.landmark if hand else None)
            dbg = detector.debug
            paused = state["paused"]

            if det.gesture is Gesture.TOGGLE_PAUSE:   # gesto de cuernos: funciona tambien en pausa
                toggle_pause()
                paused = state["paused"]
                last_event = "PAUSA" if paused else "ACTIVO"
                det = det.__class__(None, det.pose, det.hand_present)

            armed = (not paused) and (not cfg.preview_only)
            if det.gesture and armed:
                actions.run(det.gesture)
                last_event = det.gesture.name
            elif det.gesture and cfg.preview_only and not paused:
                last_event = f"{det.gesture.name} (vista)"

            if armed:
                actions.update_cursor(detector.cursor)  # mover raton / arrastrar
            else:
                actions.release_all()

            if cfg.show_preview:
                if hand:
                    drawer.draw_landmarks(frame, hand, mp.solutions.hands.HAND_CONNECTIONS)
                draw_hud(frame, hud_lines(
                    cfg, dbg,
                    paused=paused,
                    last_event=last_event,
                    preview_only=cfg.preview_only,
                ))
            cv2.imshow(WINDOW, frame)
            key = cv2.waitKey(20) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("p"), ord("P"), ord(" ")):
                toggle_pause()
    finally:
        cap.release()
        hands.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
