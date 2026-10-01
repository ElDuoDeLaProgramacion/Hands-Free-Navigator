"""ClaudeAssistant / extract_command: solo lo que se puede probar sin microfono, red ni
dependencias opcionales instaladas (como en esta maquina de pruebas)."""
from hands_free.assistant import ClaudeAssistant, extract_command
from hands_free.config import Config


# --------------------------------------------------------------------- extract_command
def test_extract_command_finds_wake_phrase_with_trailing_question():
    assert extract_command("oye claude que hora es", "oye claude") == "que hora es"


def test_extract_command_is_case_and_accent_insensitive():
    assert extract_command("OYE CLÁUDE que hora es", "oye claude") == "que hora es"
    assert extract_command("oye claude", "OYE CLÁUDE") == ""


def test_extract_command_wake_phrase_alone_returns_empty_string():
    assert extract_command("oye claude", "oye claude") == ""


def test_extract_command_returns_none_when_wake_phrase_absent():
    assert extract_command("que hora es", "oye claude") is None


def test_extract_command_finds_wake_phrase_in_the_middle():
    # el reconocimiento de voz a veces mete palabras antes por ruido de fondo
    assert extract_command("bueno oye claude apaga la pantalla", "oye claude") == "apaga la pantalla"


def test_extract_command_does_not_match_partial_word():
    # "claudia" no debe confundirse con "claude"
    assert extract_command("oye claudia que tal", "oye claude") is None


# --------------------------------------------------------------------- ClaudeAssistant
def test_assistant_starts_inactive():
    a = ClaudeAssistant(Config())
    assert a.active is False
    assert a.status == "apagado"


def test_start_without_optional_dependencies_fails_cleanly_with_a_reason():
    """Sin SpeechRecognition/pyttsx3/anthropic instalados (como en esta maquina de
    pruebas), start() debe devolver False y explicar por que, nunca lanzar."""
    a = ClaudeAssistant(Config())
    import hands_free.assistant as assistant_mod
    if assistant_mod.sr and assistant_mod.pyttsx3 and assistant_mod.anthropic:
        return   # entorno con todo instalado: este test no aplica aqui
    ok = a.start()
    assert ok is False
    assert a.error and "dependencias" in a.error.lower()
    assert a.active is False


def test_stop_without_start_does_not_raise():
    a = ClaudeAssistant(Config())
    a.stop()   # no debe lanzar aunque nunca se haya iniciado
    assert a.active is False
    assert a.status == "apagado"


def test_toggle_mute_without_start_does_not_raise():
    a = ClaudeAssistant(Config())
    a.toggle_mute()
    assert a.muted is True
    a.toggle_mute()
    assert a.muted is False
