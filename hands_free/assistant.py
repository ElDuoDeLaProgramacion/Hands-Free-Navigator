"""Asistente de voz (Claude) integrado: di "oye claude" y tu pregunta por el microfono,
te contesta por voz. Efecto del sistema/red (como recorder.py y actions.py): nada de
logica de gestos aqui.

Necesita, ademas de instalar las dependencias nuevas (ver requirements.txt):
  - Una API key de Anthropic en la variable de entorno ANTHROPIC_API_KEY. NUNCA la pongas
    en config.py ni en ningun archivo de este repo: es publico en GitHub. En Windows:
    `setx ANTHROPIC_API_KEY "tu-clave"` en una terminal y reiniciarla (o System
    Properties > Variables de entorno). Cada pregunta que le hagas a Claude tiene el
    coste normal de la API de Anthropic (aparte de cualquier suscripcion de Claude que
    ya tengas: la API se paga por separado).
  - Microfono y altavoces/auriculares. El habla se transcribe con el servicio GRATUITO de
    reconocimiento de voz de Google (por eso hace falta internet): mientras el asistente
    esta encendido, manda fragmentos cortos de audio ahi cada vez que detecta que dijiste
    algo, no solo cuando aciertas la palabra clave.

Si falta cualquier dependencia, la API key, o el microfono, `start()` devuelve False y
deja dicho el motivo en `.error` -- nunca rompe el resto del programa.
"""
from __future__ import annotations

import os
import threading
import unicodedata
from typing import List, Optional

try:
    import speech_recognition as sr
except ImportError:          # permite importar/testear sin SpeechRecognition instalado
    sr = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    import anthropic
except ImportError:
    anthropic = None

from .config import Config

_SYSTEM_PROMPT = (
    "Eres un asistente de voz integrado en un programa de control del computador por "
    "gestos de mano (Hands-Free Navigator), pensado para usarse tumbado en la cama con "
    "las manos ocupadas. La pregunta te llega ya transcrita por voz, asi que puede traer "
    "algun error de transcripcion; interpreta la intencion mas probable. Responde en "
    "espanol, corto y en frases habladas (tu respuesta se lee en voz alta con un "
    "sintetizador), sin listas, sin markdown y sin asteriscos."
)


def _normalize(word: str) -> str:
    """minusculas y sin acentos, para comparar sin depender de como transcribio Google."""
    nfkd = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def extract_command(text: str, wake_phrase: str) -> Optional[str]:
    """Si `text` contiene `wake_phrase` como secuencia de palabras (sin distinguir
    mayusculas ni acentos), devuelve lo que se dijo DESPUES de ella -- puede ser "" si
    solo se dijo la palabra clave. Si no aparece, devuelve None.

    Pura y sin efectos secundarios: se puede testear sin microfono, red ni voz.
    """
    words = text.split()
    norm_words = [_normalize(w) for w in words]
    wake_words = [_normalize(w) for w in wake_phrase.split()]
    n = len(wake_words)
    if n == 0:
        return None
    for i in range(len(norm_words) - n + 1):
        if norm_words[i:i + n] == wake_words:
            return " ".join(words[i + n:]).strip()
    return None


class ClaudeAssistant:
    """"Oye <palabra clave>" + tu pregunta -> Claude -> te contesta por voz. Escucha en
    un hilo aparte (no bloquea el bucle de gestos/camara). Nunca lanza: cualquier fallo
    (sin red, sin API key, Claude no responde...) queda en `.error`/`.status`, nunca
    interrumpe el resto del programa.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.status = "apagado"
        self.error: Optional[str] = None
        self.muted = False
        self._client = None
        self._model = cfg.assistant_model
        self._recognizer = None
        self._mic = None
        self._stop_listening = None
        self._history: List[dict] = []
        self._awaiting_question = False
        self._busy = threading.Lock()
        self._tts_engine = None

    @property
    def active(self) -> bool:
        return self._stop_listening is not None

    def _waiting_label(self) -> str:
        return f'esperando "{self.cfg.assistant_wake_phrase}"'

    def start(self) -> bool:
        if self.active:
            return True
        missing = [pkg for pkg, mod in (
            ("SpeechRecognition", sr), ("pyttsx3", pyttsx3), ("anthropic", anthropic),
        ) if mod is None]
        if missing:
            self.error = "faltan dependencias (pip install " + " ".join(missing) + ")"
            self.status = "error"
            return False
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self.error = "falta la variable de entorno ANTHROPIC_API_KEY (ver README)"
            self.status = "error"
            return False
        self._model = os.environ.get("ANTHROPIC_MODEL", self.cfg.assistant_model)
        try:
            self._client = anthropic.Anthropic(api_key=api_key)
            self._recognizer = sr.Recognizer()
            self._mic = sr.Microphone()
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            self._tts_engine = pyttsx3.init()
        except Exception as exc:                    # sin microfono, drivers raros, etc.
            self.error = f"no se pudo iniciar microfono/voz: {exc}"
            self.status = "error"
            return False
        self.error = None
        self.muted = False
        self._history.clear()
        self.status = self._waiting_label()
        self._stop_listening = self._recognizer.listen_in_background(
            self._mic, self._on_audio, phrase_time_limit=15)
        return True

    def stop(self) -> None:
        if self._stop_listening is not None:
            self._stop_listening(wait_for_stop=False)
            self._stop_listening = None
        self.status = "apagado"

    def toggle_mute(self) -> None:
        """Tecla de emergencia: silencia sin apagar del todo (deja de escuchar/mandar
        audio a Google, sin perder el microfono ya abierto)."""
        self.muted = not self.muted
        if self.active:
            self.status = "silenciado (tecla)" if self.muted else self._waiting_label()

    # ------------------------------------------------------------------ nucleo
    def _on_audio(self, recognizer, audio) -> None:
        """Callback de `listen_in_background`: llega en su propio hilo por cada frase que
        detecta (silencio de por medio). `_busy` evita procesar dos a la vez (p. ej. si
        Claude tarda en contestar y mientras tanto se detecta otra frase)."""
        if self.muted or not self._busy.acquire(blocking=False):
            return
        try:
            self._handle_audio(recognizer, audio)
        finally:
            self._busy.release()

    def _handle_audio(self, recognizer, audio) -> None:
        try:
            text = recognizer.recognize_google(audio, language=self.cfg.assistant_language)
        except sr.UnknownValueError:
            return                                   # no se entendio nada: ignorar
        except sr.RequestError as exc:
            self.error = f"Google no respondio: {exc}"
            return
        if self._awaiting_question:
            self._awaiting_question = False
            self._ask(text)
            return
        command = extract_command(text, self.cfg.assistant_wake_phrase)
        if command is None:
            return                                   # no se dijo la palabra clave
        if command:
            self._ask(command)
        else:
            self._awaiting_question = True
            self.status = "te escucho..."

    def _ask(self, question: str) -> None:
        self.status = "pensando..."
        self._history.append({"role": "user", "content": question})
        del self._history[:-self.cfg.assistant_history_len]
        try:
            reply = self._client.messages.create(
                model=self._model,
                max_tokens=self.cfg.assistant_max_tokens,
                system=_SYSTEM_PROMPT,
                messages=self._history,
            )
            answer = "".join(
                block.text for block in reply.content if getattr(block, "type", "") == "text"
            ).strip()
            if not answer:
                answer = "No he sabido que responder a eso."
        except Exception as exc:                     # sin internet, API key mala, etc.
            self._history.pop()                      # no dejar la pregunta huerfana en el historial
            self.error = f"Claude no respondio: {exc}"
            self.status = self._waiting_label()
            return
        self._history.append({"role": "assistant", "content": answer})
        self.status = "hablando..."
        self._speak(answer)
        self.status = self._waiting_label()

    def _speak(self, text: str) -> None:
        try:
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
        except Exception as exc:
            self.error = f"no se pudo hablar la respuesta: {exc}"
