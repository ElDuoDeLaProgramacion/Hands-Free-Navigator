"""Punto de entrada. Foco en la ventana de la camara:
   clic o p / espacio = pausar/reanudar     r = grabar pantalla + anclar ventana     q o ESC = salir
"""
from __future__ import annotations

import sys
import time

import cv2
import mediapipe as mp

from hands_free.actions import ActionExecutor
from hands_free.config import Config
from hands_free.gestures import CursorState, DebugInfo, Detection, Gesture, GestureDetector, TwoHandZoom
from hands_free.hud import draw_hud, hud_lines
from hands_free.recorder import ScreenRecorder, get_window_position, pin_window

WINDOW = "Hands-Free Navigator"


def main() -> int:
    cfg = Config()
    cap = cv2.VideoCapture(cfg.camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.frame_height)
    if not cap.isOpened():
        print("No se pudo abrir la camara. Cambia camera_index en config.py.")
        return 1

    # Dos manos (cfg.two_hand_mode): con UNA sola mano visible (la que sea) se hace TODO
    # lo de siempre (mover, clic, scroll...); con las DOS a la vez, lo UNICO que hacen es
    # zoom con pellizco (ver TwoHandZoom en gestures.py) — nada de repartir roles, para
    # que la segunda mano nunca se confunda con "mover el cursor" o cualquier otro gesto.
    hands = mp.solutions.hands.Hands(
        max_num_hands=2 if cfg.two_hand_mode else cfg.max_hands,
        min_detection_confidence=cfg.detection_confidence,
        min_tracking_confidence=cfg.tracking_confidence,
    )
    drawer = mp.solutions.drawing_utils
    detector = GestureDetector(cfg)      # la mano (unica) cuando solo se ve una
    zoom = TwoHandZoom(cfg)              # zoom cuando se ven las dos
    actions = ActionExecutor(cfg)
    recorder = ScreenRecorder(cfg)
    # `hand_mode_*`: cuantas manos hay (0/1/2) se "confirma" solo tras verse igual durante
    # `hand_mode_debounce_s` seguidos. Sin esto, un parpadeo de MediaPipe (un frame donde
    # cree ver una segunda mano fantasma, o pierde la unica un instante) reiniciaba el
    # clic/tab/cursor en curso todo el rato: eso se sentia como que el raton "se quedaba
    # quieto" a veces, o que el tab y el clic derecho se confundian de golpe.
    state = {
        "paused": cfg.start_paused,
        "hand_mode": "zero",
        "hand_mode_pending": "zero",
        "hand_mode_pending_since": time.monotonic(),
        "last_lm": None,           # ultimos landmarks vistos en modo "una mano" (ver mas abajo)
        "last_seen_at": -1e9,
        "pin_pos": None,           # (x, y) donde se ancla la ventana mientras se graba (ver mas abajo)
    }
    last_event = ""

    def resolve_lone_hand(lone, now):
        """Modo de una mano: si `lone` es None (MediaPipe no vio la mano ESTE frame en
        concreto) pero se la vio hace muy poco, se reutilizan sus ultimos landmarks en
        vez de pasarle None al detector. Pasar None dispara un reset completo (pierde el
        historial de junto/separado, cualquier clic a medio camino...), y pedirle 2 manos
        a MediaPipe hace que la deteccion de la unica mano parpadee mas seguido: sin esto,
        cada parpadeo de 1-2 frames se sentia como que el raton "se quedaba quieto" y de
        paso barajaba de nuevo si el gesto era tab o clic derecho."""
        if lone is not None:
            state["last_lm"] = lone.landmark
            state["last_seen_at"] = now
            return lone.landmark
        if now - state["last_seen_at"] < cfg.hand_mode_debounce_s:
            return state["last_lm"]
        return None

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    def toggle_pause() -> None:
        state["paused"] = not state["paused"]
        detector.reset()
        zoom.reset()
        print("PAUSA" if state["paused"] else "ACTIVO", flush=True)

    def toggle_recording() -> str:
        if recorder.active:
            recorder.stop()
            pin_window(WINDOW, False)
            state["pin_pos"] = None   # deja de "devolver" la ventana a un sitio fijo
            return "grabacion: off"
        ok = recorder.start()
        pin_window(WINDOW, True)
        # Ancla tambien la POSICION (ademas de topmost): mientras se graba, la ventana no
        # debe poder arrastrarse ni taparse. OpenCV no permite bloquear el arrastre en si,
        # asi que se lee su sitio actual una vez aqui y cada frame del bucle principal se
        # la "devuelve" ahi con cv2.moveWindow si el usuario la movio.
        state["pin_pos"] = get_window_position(WINDOW)
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
                n_hands = len(all_hands)
                raw_mode = "two" if n_hands >= 2 else ("one" if n_hands == 1 else "zero")
                now = time.monotonic()
                if raw_mode != state["hand_mode_pending"]:
                    state["hand_mode_pending"] = raw_mode
                    state["hand_mode_pending_since"] = now
                if (raw_mode == state["hand_mode_pending"]
                        and raw_mode != state["hand_mode"]
                        and now - state["hand_mode_pending_since"] >= cfg.hand_mode_debounce_s - 1e-6):
                    # El conteo de manos llevaba estable el tiempo suficiente: recien
                    # ahora se confirma el cambio de modo (y se reinicia, para no dejar
                    # un clic a medias ni un salto de cursor entre un modo y otro).
                    detector.reset()
                    zoom.reset()
                    state["hand_mode"] = raw_mode
                hand_mode = state["hand_mode"]

                if hand_mode == "two":
                    # Las DOS manos a la vez SOLO hacen zoom (pellizco); nada de mover el
                    # cursor ni ningun otro gesto con ellas mientras se vean las dos.
                    # OJO: `hand_mode` es el modo YA CONFIRMADO (con antirrebote); este
                    # frame en concreto puede tener menos de 2 manos todavia (una acaba de
                    # desaparecer y el cambio de modo aun no se confirmo) - sin este chequeo
                    # `all_hands[1]` revienta con IndexError.
                    if len(all_hands) >= 2:
                        zoom_gesture = zoom.update(all_hands[0].landmark, all_hands[1].landmark)
                        pose = "zoom (pellizco)" if zoom.active else "dos manos (sin pellizco)"
                        preview_hands = all_hands[:2]
                    else:
                        zoom_gesture = None
                        pose = "dos manos (esperando)"
                        preview_hands = list(all_hands)
                    det = Detection(zoom_gesture, pose, True)
                    cursor_state = CursorState()
                    dbg = DebugInfo(pose=pose, hand_present=True)   # el HUD no muestra datos viejos
                elif hand_mode == "one":
                    # Solo se ve una mano (aunque el modo de dos manos este activo): esa
                    # mano hace TODO (mover, clic, scroll...), igual que con una sola mano.
                    lone = all_hands[0] if all_hands else None
                    det = detector.update(resolve_lone_hand(lone, now))
                    cursor_state = detector.cursor
                    preview_hands = [lone] if lone else []
                    dbg = detector.debug
                else:
                    det = detector.update(None)
                    cursor_state = CursorState()
                    preview_hands = []
                    dbg = detector.debug
            else:
                gesture_hand = all_hands[0] if all_hands else None
                det = detector.update(resolve_lone_hand(gesture_hand, time.monotonic()))
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
            if state["pin_pos"] is not None:
                # "Inamovible": si se arrastro la ventana este frame, se la devuelve a su
                # sitio anclado. cv2.waitKey ya proceso el evento de arrastre antes de
                # esto, asi que el salto de vuelta se ve casi al instante, no con retraso.
                cv2.moveWindow(WINDOW, *state["pin_pos"])
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
