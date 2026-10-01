# Hands-Free Navigator

Controla el computador (scroll, clic, cambio de pestana) con gestos de la mano frente a la camara.

## Instalacion (Windows)
```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Usa Python 3.9-3.12 (MediaPipe 0.10.14 no soporta 3.13). La app arranca en PAUSA: haz **clic en la ventana de la camara** (o `p` / espacio) para activar. El teclado solo llega si esa ventana esta en primer plano, no Cursor.

Tests sin camara: `pip install pytest` y `pytest -q` en la raiz.

Para calibrar en la cama sin clics reales, pon `preview_only = True` en `config.py`. El HUD muestra por dedo el alcance actual/referencia (`[ABAJO]` cuando cuenta como bajado), la separacion `gap` (juntos/separados), el estado del raton, `thumb_dy`, `trail_dx`/`trail_dy` y la pose.

## Gestos
Indice y medio son los dedos de trabajo; anular y menique van cerrados.

| Gesto | Accion |
|---|---|
| Indice + medio arriba y **juntos** | Mover el cursor (relativo, como un touchpad) |
| ...bajar **ambos** dedos y subirlos (toque corto) | Clic izquierdo (se dispara al subir) |
| ...bajar y subir **dos veces** seguidas, sin mover la mano | Doble clic (abrir archivos) |
| ...bajar **solo el medio** y subirlo | Clic derecho |
| ...bajar ambos, **mantener 0.6 s y mover la mano** | Arrastrar / seleccionar; al subir los dedos se suelta |
| Indice + medio arriba y **separados** (V), bajar el dedo **derecho** | Selector de apps: un paso adelante (Alt se mantiene) |
| Indice + medio en V, bajar el dedo **izquierdo** | Un paso atras. Se elige al dejar 2 s o al hacer un clic |
| Puno cerrado con pulgar **arriba** / **abajo** (mantener) | Scroll arriba / abajo |
| Palma abierta deslizada a izquierda / derecha | Pestana anterior / siguiente (Ctrl+RePag/AvPag). Un salto por gesto: para repetir, deja la mano quieta un instante |
| Puno cerrado (pulgar sin apuntar arriba/abajo) | Reposo: no hace nada y cancela cualquier gesto en curso |
| **Indice + menique** ("cuernos") mantenidos 1 s | Pausar / reanudar |

Los clics solo se aceptan si los dos dedos estuvieron arriba y juntos al menos 0.15 s antes, asi que un puno suelto nunca hace clic.

## Dos manos (opcional)
Por defecto una sola mano hace todo. Poniendo `two_hand_mode = True` en `config.py`:

- **Con UNA sola mano visible** (la que sea), esa mano hace TODO lo de siempre (mover,
  clic, scroll...), igual que con el modo de una sola mano.
- **En cuanto se ven las DOS a la vez**, dejan de mover el cursor o hacer cualquier otro
  gesto: lo UNICO que hacen es zoom. Pellizca (pulgar+indice) con las DOS manos A LA VEZ
  y sepáralas para zoom in, acércalas para zoom out (Ctrl + rueda, el zoom del
  navegador). En cuanto una suelta el pellizco, el zoom se apaga solo.

Un cambio de numero de manos (aparece/desaparece una, o la camara la pierde un instante)
tarda `hand_mode_debounce_s` (0.2 s) en confirmarse, para no reiniciar el clic o el tab en
curso por un parpadeo de la deteccion. Mientras tanto se sigue siempre la mano mas
cercana a la que ya se estaba usando, nunca "la primera que reporte la camara": si por 1-2
frames MediaPipe cree ver una segunda mano de mas, no se cuelan sus landmarks a mitad de
un gesto (eso causaba que, alguna vez, un intento de cambiar de app (tab) se registrara
como clic o clic derecho).

## Grabar pantalla + anclar la ventana
Tecla **r**: graba toda la pantalla a un video (`recordings/grabacion_<fecha>.avi`) y
ancla la ventana de la camara: queda siempre visible (no se tapa al cambiar de app con
los gestos) e inamovible (si se arrastra por error, vuelve sola a su sitio cada frame).
Otra vez `r` lo detiene todo y la ventana vuelve a comportarse normal (movible, sin estar
siempre encima). Necesita `pip install mss` (ya esta en `requirements.txt`); solo
funciona en Windows (como el resto del proyecto). Ajustable en `config.py`: `record_dir`,
`record_fps`, `record_codec`, `record_ext`.

## Asistente de voz ("Oye Claude")
Di **"oye claude"** seguido de tu pregunta (o solo "oye claude" y espera: te escucha la
frase siguiente) y te contesta hablando, sin tocar el teclado ni el raton. Apagado por
defecto; para activarlo pon `assistant_enabled = True` en `config.py`. Tecla **c** mientras
el programa esta corriendo: silencia/reactiva el asistente sin apagarlo del todo (deja de
escuchar, pero no suelta el microfono).

Hace falta:
1. Instalar las dependencias nuevas: `pip install -r requirements.txt` (incluye
   `SpeechRecognition`, `pyttsx3`, `anthropic` y `pyaudio`). En Windows, `pyaudio` a veces
   falla con pip normal por falta de compilador; si pasa eso, prueba
   `pip install pipwin` y luego `pipwin install pyaudio`.
2. **Tu propia API key de Anthropic**, en la variable de entorno `ANTHROPIC_API_KEY` —
   **nunca la pongas en `config.py` ni en ningun archivo del repo: este repositorio es
   publico en GitHub**, y cualquiera que la vea puede gastar tu saldo. En una terminal de
   Windows:
   ```
   setx ANTHROPIC_API_KEY "tu-clave-aqui"
   ```
   y reinicia la terminal (o ponla en Panel de control > Variables de entorno). Puedes
   conseguir una clave en el panel de desarrolladores de Anthropic (console.anthropic.com);
   es una cuenta y facturacion aparte de cualquier suscripcion de Claude que ya tengas.
3. Microfono y altavoces/auriculares.

**Privacidad y coste, importante:** mientras el asistente esta encendido (y no silenciado
con `c`), cada fragmento de voz que detecta se manda al servicio **gratuito** de
reconocimiento de voz de Google para transcribirlo — esto pasa con CUALQUIER frase que
digas cerca del microfono, no solo cuando dices "oye claude" (Google no sabe cual es tu
palabra clave; eso se filtra despues, ya en tu PC). Y cada pregunta que de verdad le hagas
a Claude (tras decir la palabra clave) tiene el coste normal de uso de la API de
Anthropic, ademas de cualquier suscripcion de Claude que ya pagues por separado. Si no
quieres ninguna de las dos cosas, deja `assistant_enabled = False` (por defecto).

Ajustable en `config.py`: `assistant_wake_phrase` (palabra clave), `assistant_language`
(idioma para el reconocimiento de voz), `assistant_model`, `assistant_max_tokens`,
`assistant_history_len` (cuanta conversacion previa recuerda).

## Arranque automatico al iniciar Windows
El archivo `iniciar.bat` (en la raiz del proyecto) activa el entorno virtual y lanza
`python main.py`. Dos formas de que se ejecute solo al encender el PC:

**Opcion A - Carpeta de Inicio (mas simple):**
1. Pulsa `Win + R`, escribe `shell:startup` y dale a Enter (abre tu carpeta de Inicio).
2. Crea ahi un acceso directo a `iniciar.bat` (clic derecho sobre `iniciar.bat` > "Enviar
   a" > "Escritorio (crear acceso directo)", y luego mueve ese acceso directo a la carpeta
   de Inicio que acabas de abrir).

**Opcion B - Programador de tareas (mas control, p. ej. arrancar antes de iniciar sesion):**
1. Abre "Programador de tareas" (busca "Task Scheduler" en el menu de inicio).
2. "Crear tarea basica..." > nombre, p. ej. "Hands-Free Navigator".
3. Desencadenador: "Al iniciar sesion".
4. Accion: "Iniciar un programa" > selecciona `iniciar.bat` (usa la ruta completa, p. ej.
   `P:\Hands-Free Navigator\iniciar.bat`).
5. Termina el asistente. En las propiedades de la tarea (pestana "General") puedes marcar
   "Ejecutar tanto si el usuario inicio sesion como si no" si quieres que arranque sin
   esperar a que abras sesion.

La ventana de la camara arranca en PAUSA (como siempre): aunque el programa se abra solo,
no movera el raton hasta que hagas clic en su ventana o pulses `p`/espacio.

## Estructura
- `main.py` + `hands_free/hud.py`: bucle de camara, teclas y overlay de calibracion.
- `hands_free/gestures.py`: landmarks -> gestos (sin efectos secundarios); incluye `CursorTracker` (mano de solo-cursor).
- `hands_free/actions.py`: gestos -> raton/teclado.
- `hands_free/recorder.py`: grabar pantalla + anclar ventana (efectos del sistema, como actions.py).
- `hands_free/assistant.py`: asistente de voz "Oye Claude" (efecto del sistema/red, como recorder.py).
- `hands_free/config.py`: umbrales (Claude) e interfaz (`preview_only`, dos manos, grabacion, asistente; Cursor).
- `iniciar.bat`: activa el entorno virtual y lanza `main.py` (para arranque automatico, ver mas arriba).
- `tests/`: pytest sin webcam.

## Seguridad
Arranca en pausa. El cursor nunca llega al pixel exacto de una esquina de la pantalla
(se recorta un poco antes), y si pyautogui aborta igual por algun otro motivo, se
ignora esa accion en vez de cerrar el programa entero.

## Licencia

MIT. Ver el archivo `LICENSE`.
