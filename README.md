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

## Estructura
- `main.py` + `hands_free/hud.py`: bucle de camara, teclas y overlay de calibracion.
- `hands_free/gestures.py`: landmarks -> gestos (sin efectos secundarios).
- `hands_free/actions.py`: gestos -> raton/teclado.
- `hands_free/config.py`: umbrales (Claude) e interfaz (`preview_only`, Cursor).
- `tests/`: pytest sin webcam.

## Seguridad
Arranca en pausa. Mover el raton a una esquina de la pantalla aborta el programa (pyautogui failsafe).
