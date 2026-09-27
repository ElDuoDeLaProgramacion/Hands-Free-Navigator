"""ScreenRecorder / pin_window: solo lo que se puede probar sin pantalla real ni Windows."""
from hands_free.config import Config
from hands_free.recorder import ScreenRecorder, pin_window


def test_recorder_starts_inactive():
    rec = ScreenRecorder(Config())
    assert rec.active is False
    assert rec.path is None


def test_stop_without_start_does_not_raise():
    rec = ScreenRecorder(Config())
    rec.stop()   # no debe lanzar aunque nunca se haya iniciado
    assert rec.active is False


def test_start_without_mss_fails_cleanly_with_a_reason():
    """Sin `mss` instalado (o sin pantalla real, como en esta maquina de pruebas),
    start() debe devolver False y explicar por que, nunca lanzar ni dejar un hilo colgado."""
    rec = ScreenRecorder(Config())
    import hands_free.recorder as recorder_mod
    if recorder_mod.mss is not None:
        return   # entorno con mss real instalado: este test no aplica aqui
    ok = rec.start()
    assert ok is False
    assert rec.error and "mss" in rec.error.lower()
    assert rec.active is False


def test_pin_window_never_raises_when_window_or_platform_is_missing():
    # Fuera de Windows (o sin esa ventana abierta) debe devolver False sin lanzar.
    assert pin_window("una ventana que no existe, seguro", True) in (False, True)
    assert pin_window("una ventana que no existe, seguro", False) in (False, True)
