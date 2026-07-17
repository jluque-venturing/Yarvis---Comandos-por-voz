import base64
import io
import subprocess
import webbrowser

import mss
import pyautogui
import pygetwindow as gw
from PIL import Image
from pynput.keyboard import Controller

_kb = Controller()


# --- Esquema de tools para la Claude API (Fases 1 y 3) ---
TOOLS = [
    {
        "name": "open_app",
        "description": "Abre una aplicacion por nombre (ej. 'chrome', 'notepad', 'spotify').",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "open_url",
        "description": "Abre una URL en el navegador por defecto.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "type_text",
        "description": "Escribe texto en la ventana con foco, como si el usuario tecleara (soporta acentos y UTF-8).",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "press_hotkey",
        "description": "Presiona una combinacion de teclas, ej. 'ctrl+c', 'alt+tab', 'win+d', 'enter'.",
        "input_schema": {
            "type": "object",
            "properties": {"keys": {"type": "string"}},
            "required": ["keys"],
        },
    },
    {
        "name": "focus_window",
        "description": "Trae al frente la ventana cuyo titulo contenga el texto dado.",
        "input_schema": {
            "type": "object",
            "properties": {"title_substring": {"type": "string"}},
            "required": ["title_substring"],
        },
    },
    {
        "name": "list_windows",
        "description": "Lista los titulos de las ventanas abiertas.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "screenshot",
        "description": "Toma una captura de pantalla y la devuelve para que el modelo la vea.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "click",
        "description": "Hace click en coordenadas de pantalla (x, y). button: left|right|double.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right", "double"]},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "run_shell",
        "description": "Ejecuta un comando de shell de Windows. USO RESTRINGIDO: los comandos peligrosos requieren confirmacion del usuario.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "media_key",
        "description": "Controla multimedia/volumen: play_pause, next, prev, volup, voldown, mute.",
        "input_schema": {
            "type": "object",
            "properties": {"action": {"type": "string"}},
            "required": ["action"],
        },
    },
    {
        "name": "computer_agent",
        "description": (
            "Fallback agentico: delega una tarea que no se resuelve con las tools especificas "
            "(ej. 'ordena los iconos', 'hace clic en el boton azul de la esquina'). "
            "Ve la pantalla y decide clicks por si mismo. Usar solo cuando las tools directas no alcanzan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
    },
]


def open_app(name):
    # start "" evita que el primer argumento entre comillas se tome como titulo de ventana
    subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
    return f"Abriendo {name}"


def open_url(url):
    webbrowser.open(url)
    return f"Abriendo {url}"


def type_text(text):
    _kb.type(text)
    return "Texto escrito"


_KEY_ALIASES = {
    "win": "winleft",
    "windows": "winleft",
    "cmd": "winleft",
    "control": "ctrl",
    "escape": "esc",
    "return": "enter",
    "intro": "enter",
    "espacio": "space",
    "supr": "delete",
    "borrar": "backspace",
}


def press_hotkey(keys):
    parts = [_KEY_ALIASES.get(k.strip().lower(), k.strip().lower()) for k in keys.split("+")]
    pyautogui.hotkey(*parts)
    return f"Tecla {keys}"


def focus_window(title_substring):
    for w in gw.getAllWindows():
        title = w.title or ""
        if title_substring.lower() in title.lower():
            try:
                if w.isMinimized:
                    w.restore()
                w.activate()
            except Exception:
                pass
            return f"Ventana enfocada: {title}"
    return f"No encontre una ventana con '{title_substring}'"


def list_windows():
    titles = [t for t in gw.getAllTitles() if t and t.strip()]
    if not titles:
        return "No hay ventanas con titulo."
    return "Ventanas abiertas:\n" + "\n".join(f"- {t}" for t in titles)


def screenshot():
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", raw.size, raw.rgb)
    img.thumbnail((1280, 800))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        }
    ]


def click(x, y, button="left"):
    if button == "double":
        pyautogui.doubleClick(x, y)
    elif button == "right":
        pyautogui.click(x, y, button="right")
    else:
        pyautogui.click(x, y, button="left")
    return f"Click {button} en ({x}, {y})"


def run_shell(command):
    r = subprocess.run(
        ["cmd", "/c", command],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=45,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip() or "(sin salida)"
    return out[:2000]


_MEDIA = {
    "play_pause": "playpause",
    "next": "nexttrack",
    "prev": "prevtrack",
    "volup": "volumeup",
    "voldown": "volumedown",
    "mute": "volumemute",
}


def media_key(action):
    key = _MEDIA.get(action)
    if not key:
        return f"Accion multimedia desconocida: {action}"
    pyautogui.press(key)
    return f"Multimedia: {action}"


def computer_agent(task):
    from core import computer_use

    return computer_use.run_computer_task(task)


DISPATCH = {
    "open_app": lambda i: open_app(i["name"]),
    "open_url": lambda i: open_url(i["url"]),
    "type_text": lambda i: type_text(i["text"]),
    "press_hotkey": lambda i: press_hotkey(i["keys"]),
    "focus_window": lambda i: focus_window(i["title_substring"]),
    "list_windows": lambda i: list_windows(),
    "screenshot": lambda i: screenshot(),
    "click": lambda i: click(i["x"], i["y"], i.get("button", "left")),
    "run_shell": lambda i: run_shell(i["command"]),
    "media_key": lambda i: media_key(i["action"]),
    "computer_agent": lambda i: computer_agent(i["task"]),
}
