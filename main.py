"""Punto de entrada. Foco en la ventana de la camara:
   clic o p / espacio = pausar/reanudar     r = grabar pantalla + anclar ventana     q o ESC = salir
"""
from __future__ import annotations

import sys

import cv2
import mediapipe as mp

from hands_free.actions import ActionExecutor
from hands_free.config import Config
from hands_free.gestures import CursorState, CursorTracker, Gesture, GestureDetector
from hands_free.hud import draw_hud, hud_lines
from hands_free.recorder import ScreenRecorder, pin_window

WINDOW = "Hands-Free Navigator"


def main() -> int:
    cfg = Config()
    cap = cv2.VideoCapture(cfg.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.frame_height)
    if not cap.isOpened():
        print("No se pudo abrir la camara. Cambia camera_index en config.py.")
        return 1

    # Dos manos (cfg.two_hand_mode): una SOLO mueve el cursor, la otra hace el resto de
    # gestos (ver CursorTracker en gestures.py). Pedimos 2 manos a MediaPipe automatico,
    # sin depender de que tambien se haya puesto max_hands=2 a mano en config.py.
    hands = mp.solutions.hands.Hands(
        max_num_hands=2 if cfg.two_hand_mode else cfg.max_hands,
        min_detection_confidence=cfg.detection_confidence,
        min_tracking_confidence=cfg.tracking_confidence,
    )
    drawer = mp.solutions.drawing_utils
    detector = GestureDetector(cfg)             # mano de gestos (o la unica mano, si two_hand_mode=False)
    cursor_tracker = CursorTracker(cfg)          # solo se usa si cfg.two_hand_mode
    actions = ActionExecutor(cfg)
    recorder = ScreenRecorder(cfg)
    state = {"paused": cfg.start_paused}
    last_event = ""

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    def toggle_pause() -> None:
        state["paused"] = not state["paused"]
        detector.reset()
        cursor_tracker.reset()
        print("PAUSA" if state["paused"] else "ACTIVO", flush=True)

    def toggle_recording() -> str:
        if recorder.active:
            recorder.stop()
            pin_window(WINDOW, False)
            return "grabacion: off"
        ok = recorder.start()
        pin_window(WINDOW, True)
        return "grabacion: on" if ok else f"grabacion: error ({recorder.error})"

    def on_mouse(event, _x, _y, _flags, _param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            toggle_pause()

    cv2.setMouseCallback(WINDOW, on_mouse)
    print("Clic en la ventana de la camara, o pulsa p / espacio. "
          "r = grabar pantalla y anclar la ventana. q sale.", flush=True)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if cfg.mirror:
                frame = cv2.flip(frame, 1)

            result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            all_hands = result.multi_hand_landmarks or []

            if cfg.two_hand_mode:
                gesture_hand = cursor_hand = None
                for lm_obj, handed in zip(all_hands, result.multi_handedness or []):
                    label = handed.classification[0].label.lower()   # "left" | "right"
                    if label == cfg.cursor_hand:
                        cursor_hand = lm_obj
                    else:
                        gesture_hand = lm_obj
                det = detector.update(gesture_hand.landmark if gesture_hand else None)
                cpos = cursor_tracker.update(cursor_hand.landmark if cursor_hand else None)
                cursor_state = CursorState(cpos.active, cpos.x, cpos.y, detector.dragging, cpos.mode)
                preview_hands = [h for h in (cursor_hand, gesture_hand) if h is not None]
            else:
                gesture_hand = all_hands[0] if all_hands else None
                det = detector.update(gesture_hand.landmark if gesture_hand else None)
                cursor_state = detector.cursor
                preview_hands = [gesture_hand] if gesture_hand else []

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
                actions.update_cursor(cursor_state)  # mover raton / arrastrar
            else:
                actions.release_all()

            if cfg.show_preview:
                for h in preview_hands:
                    drawer.draw_landmarks(frame, h, mp.solutions.hands.HAND_CONNECTIONS)
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
            if key in (ord("r"), ord("R")):
                last_event = toggle_recording()
    finally:
        recorder.stop()
        pin_window(WINDOW, False)
        cap.release()
        hands.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
