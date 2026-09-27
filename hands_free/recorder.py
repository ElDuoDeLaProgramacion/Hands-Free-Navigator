"""Grabacion de pantalla + anclar la ventana de vista previa. Efectos del sistema
operativo (como actions.py): nada de logica de gestos aqui.

Se activa/desactiva con una sola tecla desde main.py (ver README): mientras esta
activo, graba TODA la pantalla a un archivo de video y ancla la ventana de la camara
(siempre visible) para que los gestos de cambiar de app no la tapen; al desactivar,
se suelta la ventana y se cierra el video.
"""
from __future__ import annotations

import ctypes
import datetime
import os
import threading
import time
from typing import Optional

try:
    import mss
except ImportError:          # permite importar/testear sin mss instalado
    mss = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

from .config import Config

_HWND_TOPMOST, _HWND_NOTOPMOST = -1, -2
_SWP_NOMOVE, _SWP_NOSIZE = 0x0002, 0x0001


def pin_window(title: str, on: bool) -> bool:
    """Ancla (siempre visible, por encima de las demas) o desancla la ventana de OpenCV
    que tenga este `title`. Solo Windows (como el resto del proyecto); en cualquier otro
    caso, o si no encuentra la ventana, no hace nada y devuelve False. Nunca lanza.
    """
    user32 = getattr(ctypes, "windll", None)
    if user32 is None:
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        flag = _HWND_TOPMOST if on else _HWND_NOTOPMOST
        user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE)
        return True
    except Exception:
        return False


class ScreenRecorder:
    """Graba toda la pantalla a un archivo de video en un hilo aparte, a `cfg.record_fps`.

    `start()` / `stop()` se pueden llamar cada frame sin problema (no repiten trabajo si
    ya esta en el estado pedido). El archivo queda en `cfg.record_dir` con la fecha y
    hora en el nombre. Si faltan `mss`/`opencv`/`numpy`, `start()` devuelve False y deja
    el motivo en `.error` en vez de fallar a medias.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._path: Optional[str] = None
        self.error: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def path(self) -> Optional[str]:
        return self._path

    def start(self) -> bool:
        if self.active:
            return True
        if mss is None or cv2 is None or np is None:
            self.error = "faltan dependencias (pip install mss; opencv y numpy ya deberian estar)"
            return False
        self.error = None
        os.makedirs(self.cfg.record_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = os.path.join(self.cfg.record_dir, f"grabacion_{stamp}.{self.cfg.record_ext}")
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if not self.active:
            return
        self._stop_evt.set()
        self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        fps = max(1, self.cfg.record_fps)
        interval = 1.0 / fps
        writer = None
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]   # 0 = todos los monitores juntos
                w, h = monitor["width"], monitor["height"]
                fourcc = cv2.VideoWriter_fourcc(*self.cfg.record_codec)
                writer = cv2.VideoWriter(self._path, fourcc, fps, (w, h))
                if not writer.isOpened():
                    self.error = f"no se pudo abrir el video de salida ({self._path})"
                    return
                next_t = time.monotonic()
                while not self._stop_evt.is_set():
                    frame = np.array(sct.grab(monitor))[:, :, :3]   # BGRA -> BGR
                    writer.write(frame)
                    next_t += interval
                    delay = next_t - time.monotonic()
                    if delay > 0:
                        self._stop_evt.wait(delay)
                    else:
                        next_t = time.monotonic()   # ya vamos tarde: no acumular retraso
        except Exception as exc:                    # nunca tumbar el hilo en silencio
            self.error = str(exc)
        finally:
            if writer is not None:
                writer.release()
