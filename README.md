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

## Estructura
- `main.py` + `hands_free/hud.py`: bucle de camara, teclas y overlay de calibracion.
- `hands_free/gestures.py`: landmarks -> gestos (sin efectos secundarios); incluye `CursorTracker` (mano de solo-cursor).
- `hands_free/actions.py`: gestos -> raton/teclado.
- `hands_free/recorder.py`: grabar pantalla + anclar ventana (efectos del sistema, como actions.py).
- `hands_free/config.py`: umbrales (Claude) e interfaz (`preview_only`, dos manos, grabacion; Cursor).
- `tests/`: pytest sin webcam.

## Seguridad
Arranca en pausa. El cursor nunca llega al pixel exacto de una esquina de la pantalla
(se recorta un poco antes), y si pyautogui aborta igual por algun otro motivo, se
ignora esa accion en vez de cerrar el programa entero.

## Licencia

MIT. Ver el archivo `LICENSE`.
