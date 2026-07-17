import base64
import io
import time

import anthropic
import mss
import pyautogui
from PIL import Image

import config

client = anthropic.Anthropic()

# Verificar en la doc oficial la version de tool y el header beta vigentes al construir.
BETA_HEADER = "computer-use-2025-11-24"
TOOL_TYPE = "computer_20251124"

# Resolucion "logica" que ve el modelo. Las coordenadas se escalan a la pantalla real.
TARGET_W, TARGET_H = 1280, 800
MAX_LOOPS = 20

_KEYMAP = {
    "Return": "enter",
    "Escape": "esc",
    "BackSpace": "backspace",
    "Tab": "tab",
    "space": "space",
    "Page_Up": "pageup",
    "Page_Down": "pagedown",
    "Delete": "delete",
    "Up": "up",
    "Down": "down",
    "Left": "left",
    "Right": "right",
    "Home": "home",
    "End": "end",
}


def _shot_b64():
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", raw.size, raw.rgb).resize((TARGET_W, TARGET_H))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def _img_block():
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": _shot_b64()},
        }
    ]


def _to_real(coord):
    rw, rh = pyautogui.size()
    x, y = coord
    return int(x * rw / TARGET_W), int(y * rh / TARGET_H)


def _press_key(text):
    parts = text.split("+")
    mapped = [_KEYMAP.get(p, p.lower()) for p in parts]
    if len(mapped) > 1:
        pyautogui.hotkey(*mapped)
    else:
        pyautogui.press(mapped[0])


def _exec(action_input):
    action = action_input.get("action")
    coord = action_input.get("coordinate")

    if action == "screenshot":
        return _img_block()
    if action == "mouse_move":
        pyautogui.moveTo(*_to_real(coord))
        return _img_block()
    if action in ("left_click", "right_click", "middle_click", "double_click"):
        x, y = _to_real(coord)
        if action == "double_click":
            pyautogui.doubleClick(x, y)
        elif action == "right_click":
            pyautogui.click(x, y, button="right")
        elif action == "middle_click":
            pyautogui.click(x, y, button="middle")
        else:
            pyautogui.click(x, y)
        time.sleep(0.4)
        return _img_block()
    if action == "left_click_drag":
        pyautogui.dragTo(*_to_real(coord), duration=0.3)
        return _img_block()
    if action == "type":
        pyautogui.typewrite(action_input.get("text", ""), interval=0.01)
        return _img_block()
    if action == "key":
        _press_key(action_input.get("text", ""))
        time.sleep(0.2)
        return _img_block()
    if action == "scroll":
        amount = int(action_input.get("scroll_amount", 3))
        direction = action_input.get("scroll_direction", "down")
        if coord:
            pyautogui.moveTo(*_to_real(coord))
        pyautogui.scroll(amount * (1 if direction == "up" else -1) * 100)
        return _img_block()
    if action == "wait":
        time.sleep(float(action_input.get("duration", 1)))
        return _img_block()
    if action == "cursor_position":
        x, y = pyautogui.position()
        return f"cursor en ({x}, {y})"
    return f"accion no soportada: {action}"


def run_computer_task(task, model=None):
    model = model or config.ORCHESTRATOR_MODEL
    tools_cu = [
        {
            "type": TOOL_TYPE,
            "name": "computer",
            "display_width_px": TARGET_W,
            "display_height_px": TARGET_H,
        }
    ]
    messages = [{"role": "user", "content": task}]

    for _ in range(MAX_LOOPS):
        resp = client.beta.messages.create(
            model=model,
            max_tokens=2048,
            tools=tools_cu,
            betas=[BETA_HEADER],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "pause_turn":
            continue
        if resp.stop_reason != "tool_use":
            return (
                "".join(
                    b.text for b in resp.content if getattr(b, "type", None) == "text"
                ).strip()
                or "Tarea completada."
            )

        results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                out = _exec(block.input)
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": out}
                )
        messages.append({"role": "user", "content": results})

    return "Alcance el limite de pasos del modo agentico."
