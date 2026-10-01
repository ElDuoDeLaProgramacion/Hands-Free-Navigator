"""Ajustes centrales. Cambia aqui umbrales y atajos sin tocar la logica."""
from dataclasses import dataclass


@dataclass
class Config:
    # --- Camara ---
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    mirror: bool = True  # espejo: mover la mano a tu derecha = derecha en pantalla

    # --- MediaPipe ---
    max_hands: int = 1
    detection_confidence: float = 0.7
    tracking_confidence: float = 0.6

    # --- Dos manos (opcional) ---
    # False (por defecto): una sola mano hace todo (mover, clic, scroll, etc.), como hasta ahora.
    # True: con UNA mano visible (la que sea) se sigue haciendo TODO lo de siempre; en
    # cuanto se ven las DOS a la vez, dejan de mover el cursor o hacer cualquier otro
    # gesto y SOLO sirven para el zoom con pellizco (ver TwoHandZoom en gestures.py).
    # Nada de repartir "esta mano mueve, esta hace clic": eso confundia el zoom con mover
    # el raton. Cuando esta activo, main.py le pide a MediaPipe `max_num_hands=2`.
    two_hand_mode: bool = True
    # Cuanto debe mantenerse estable el numero de manos vistas (0, 1 o 2) antes de que se
    # confirme un cambio de modo. Sin esto, un parpadeo de MediaPipe de 1-2 frames (cree
    # ver una segunda mano fantasma, o pierde la unica un instante) reiniciaba el clic o
    # el tab en curso de golpe: eso se sentia como que el raton "se quedaba quieto" a
    # veces, o que el tab y el clic derecho se confundian sin motivo aparente.
    hand_mode_debounce_s: float = 0.20

    # Zoom: pellizco (pulgar+indice) en AMBAS manos A LA VEZ, solo con las dos visibles.
    # Separarlas = zoom in, acercarlas = zoom out (Ctrl + rueda). Mientras se este
    # pellizcando con las dos, esas manos no mueven el cursor ni hacen otros gestos.
    zoom_pinch_ratio: float = 0.35    # dist(pulgar,indice)/tamano_mano por debajo = pellizcando
    zoom_step: float = 0.15           # cuanto deben acercarse/separarse (fraccion de imagen) por paso
    zoom_scroll_amount: int = 100     # "muescas" de Ctrl+rueda por paso (como scroll_amount)

    # --- Dos dedos (indice + medio, anular y menique cerrados) ---
    # JUNTOS: mueven el cursor. Bajar ambos y subir = clic; dos veces = doble clic;
    # bajar solo el medio y subir = clic derecho; bajar ambos, mantener y mover = arrastrar.
    # SEPARADOS (V): bajar el dedo izquierdo/derecho = cambio de aplicacion (ver mas abajo).
    finger_together: float = 0.30     # mediana de dist(puntas)/tamano_mano por debajo = juntos
    finger_apart: float = 0.45        # por encima = separados (entre ambos se mantiene el estado anterior)
    spread_window_s: float = 0.30     # ventana de la mediana (evita que un frame ruidoso cambie el modo)
    # Clasificacion de cada dedo con histeresis (evita parpadeos). Extendido = punta mas lejos de la
    # muneca que su PIP (ratio) y con suficiente alcance punta-nudillo (/tamano mano).
    ext_on: float = 1.10
    ext_off: float = 1.00
    reach_on: float = 0.55
    reach_off: float = 0.45
    # "Dedo abajo" se mide RELATIVO a ese mismo dedo cuando estaba arriba (alcance punta-nudillo):
    # vale tanto doblarlo como bajarlo desde el nudillo (en la imagen se acorta).
    down_frac: float = 0.65           # abajo cuando su alcance cae por debajo de esta fraccion de la referencia
    up_frac: float = 0.82             # vuelve a "arriba" por encima de esta fraccion
    ref_window_s: float = 1.5         # ventana para la referencia con los dedos arriba
    arm_s: float = 0.15               # tiempo con los dos dedos arriba antes de aceptar clics/toques
    dip_min_s: float = 0.08           # un dedo bajado menos que esto es un parpadeo del detector, no un clic
    click_max_down_s: float = 0.55    # dedos abajo mas tiempo que esto = no es un clic (p. ej. puno de reposo)
    click_cooldown_s: float = 0.25
    # Doble clic: segundo clic en el mismo sitio dentro de `double_click_window_s` (entre clics).
    # Si llega antes de `os_double_click_s` (Windows: 0.5 s) se envia un clic mas; si llega despues,
    # un doble clic completo (asi siempre lo registra el sistema).
    os_double_click_s: float = 0.5
    double_click_max_move: float = 0.06    # movimiento max. de la mano entre clics (fraccion de imagen)
    double_click_window_s: float = 0.9
    double_click_min_gap_s: float = 0.15   # bajo esto se considera rebote, no un segundo clic
    # Arrastre: bajar ambos dedos, mantener `drag_hold_s` y mover la mano `drag_move` -> boton pulsado
    # hasta subir los dedos. Sin movimiento no hay arrastre (un puno de reposo no pulsa nada).
    drag_enabled: bool = True
    drag_hold_s: float = 0.60
    drag_move: float = 0.04           # fraccion de la imagen
    drag_window_s: float = 2.0        # despues de esto el puno pasa a reposo
    drag_release_s: float = 0.10      # tiempo con los dedos arriba para soltar el boton (evita cortes por un frame)
    # Si con los dos dedos "abajo" el pulgar se inclina claramente arriba/abajo (mismo
    # umbral que activa el scroll, `thumb_tilt`) durante esto, en realidad es un puno para
    # hacer scroll, no un clic: se suelta el estado ya mismo en vez de esperar el timeout
    # de clic/arrastre (evita el bloqueo de hasta 2 s que se sentia como "puno = mover").
    fist_scroll_break_s: float = 0.10

    # --- Pausa / reanudar ---
    # Gesto "cuernos": indice + menique extendidos, medio y anular cerrados, mantenido.
    toggle_hold_s: float = 1.0
    toggle_cooldown_s: float = 1.5

    # --- Scroll (pulgar arriba / abajo con el resto de dedos cerrados) ---
    scroll_amount: int = 120          # unidades de rueda por paso
    scroll_interval_s: float = 0.08   # cada cuanto se repite mientras se mantiene el gesto
    scroll_hold_s: float = 0.25       # tiempo minimo sosteniendo el gesto antes de activar
    # Eje del pulgar: "image" = eje Y de la imagen; "hand" = eje muneca->nudillo del medio;
    # "auto" = "image" si la mano esta casi vertical, "hand" si esta girada (de lado / boca arriba).
    thumb_axis: str = "auto"
    # 55° (no 35°): sentado la muñeca suele inclinarse 30–45° y "auto" saltaba
    # al eje de la mano; thumb_dy caía ~0 y el scroll arriba/abajo se perdía.
    thumb_axis_tilt_deg: float = 55.0
    thumb_axis_hysteresis_deg: float = 15.0  # vuelve a "image" solo bajo (tilt_deg - esto)
    thumb_tilt: float = 0.5           # cuanto debe apuntar el pulgar arriba/abajo (x tamano mano)

    # --- Mover el raton ---
    # Cursor RELATIVO (como un touchpad) siguiendo el nudillo del indice mientras los dos dedos
    # estan arriba y juntos: levanta la mano y recolocala para "reengancharte".
    move_gain: float = 2.0        # pantallas recorridas por cada ancho/alto de imagen que mueves la mano
    move_smoothing: float = 0.5   # 0-1: peso de la muestra nueva (menor = mas suave y mas lento)
    # No dejar que el cursor TOQUE el pixel exacto de una esquina/borde: ahi pyautogui
    # aborta el programa (failsafe). Se mantiene a esta distancia como minimo.
    edge_margin_px: int = 2

    # --- Cambio de pagina/pestana (deslizar palma abierta) ---
    swipe_window_s: float = 0.6       # ventana de tiempo para medir el deslizamiento
    swipe_min_dx: float = 0.18        # desplazamiento horizontal minimo (fraccion del ancho)
    swipe_max_dy: float = 0.10        # desplazamiento vertical maximo tolerado
    swipe_cooldown_s: float = 0.8
    # Tras un deslizamiento, otro solo se acepta cuando la mano estuvo casi quieta `swipe_rearm_still_s`
    # (o perdio la pose de palma). Evita disparos repetidos por el gesto de retorno o al agitar la mano.
    swipe_rearm_still_s: float = 0.25
    swipe_rearm_move: float = 0.05
    # "tabs" -> Ctrl+RePag / Ctrl+AvPag (pestana anterior/siguiente, sin orden MRU) ; "history" -> Alt+Izq / Alt+Der
    swipe_mode: str = "tabs"

    # --- Cambio de aplicacion (dos dedos SEPARADOS) ---
    # Se mantiene Alt pulsado y cada toque de dedo mueve la seleccion un paso: bajar el dedo derecho =
    # adelante, el izquierdo = atras (tal como se ven en la ventana de la camara, con imagen en espejo).
    # Se elige la app resaltada al dejar de tocar `app_switch_confirm_s` segundos.
    app_switch_confirm_s: float = 2.0
    app_tap_confirm_s: float = 0.10   # tiempo minimo con el dedo abajo (filtra parpadeos de 1 frame)
    app_tap_cooldown_s: float = 0.25  # pausa entre toques

    # --- Interfaz (Cursor). No cambies umbrales de gestos aqui. ---
    show_preview: bool = True
    start_paused: bool = True         # arranca en pausa; tecla 'p' para activar
    preview_only: bool = False        # True: detecta y pinta HUD, no mueve raton/teclado

    # --- Grabar pantalla + anclar la ventana (tecla 'r' en main.py, ver recorder.py) ---
    # Al activar: graba TODA la pantalla a un video y ancla la ventana de la camara
    # (siempre visible, no se tapa al cambiar de app). Al desactivar: para el video y
    # suelta la ventana. Necesita `pip install mss` (opencv y numpy ya son dependencias).
    record_dir: str = "recordings"
    record_fps: int = 10              # de sobra para un registro de uso; mas alto = archivos mas pesados
    record_codec: str = "XVID"        # con extension .avi se reproduce en Windows sin codecs aparte
    record_ext: str = "avi"

    # --- Asistente de voz "Oye Claude" (opcional, ver hands_free/assistant.py) ---
    # False por defecto: hace falta microfono, internet y tu propia API key de Anthropic
    # (variable de entorno ANTHROPIC_API_KEY, ver README) para que merezca la pena activarlo.
    assistant_enabled: bool = False
    assistant_wake_phrase: str = "oye claude"
    assistant_language: str = "es-ES"     # idioma para el reconocimiento de voz (Google)
    assistant_model: str = "claude-sonnet-4-5"   # se puede forzar con la variable ANTHROPIC_MODEL
    assistant_max_tokens: int = 300
    assistant_history_len: int = 6        # mensajes (usuario+asistente) que se mandan de contexto
