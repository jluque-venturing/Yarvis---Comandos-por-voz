# PLAN DE BUILD — Asistente "Jarvis" para control de PC por voz y celular

> **Propósito de este documento**
> Este archivo es una **especificación ejecutable**. Está pensado para entregárselo a un agente de **Claude Code** (o a un desarrollador) y que pueda construir el sistema **de principio a fin, sin ambigüedades**. Contiene: arquitectura, stack, dependencias exactas, estructura de repo, esqueletos de código, fases con criterios de aceptación, comportamiento esperado y consideraciones de seguridad.
>
> **Instrucción para el agente que lo lea:** implementá **fase por fase**. No pases a la fase siguiente hasta cumplir *todos* los criterios de aceptación de la fase actual. Ante cualquier decisión no especificada, elegí la opción más simple y segura y dejala documentada en el `README.md`.

---

## 0. Resumen ejecutivo

Se construye un **agente residente** en una PC con **Windows** que:

1. Recibe instrucciones del usuario desde el **celular** (texto y notas de voz vía Telegram; luego modo "llamada" por voz).
2. Convierte voz → texto (STT) cuando aplica.
3. Envía la instrucción a un **orquestador LLM (Claude API)** que decide qué hacer.
4. Ejecuta acciones reales sobre la PC mediante **simulación de mouse/teclado y comandos** (el "emulador" que el usuario propuso). El SO recibe esos eventos como si fueran del usuario real.
5. Responde al celular (texto y/o voz TTS), incluyendo capturas de pantalla cuando ayuda.

**Idea clave de diseño:** el LLM **no** escribe en una consola de Claude. El LLM *es* el cerebro y llama a **herramientas** (tool use) que un ejecutor local corre. La parte "difícil" no es la plomería (capturar audio, simular teclas: eso está resuelto por librerías estándar), sino la **fiabilidad** de la interpretación y la **seguridad** (esto le da a un teléfono capacidad de ejecutar acciones en tu PC).

### Atajo alternativo (evaluar antes de construir)
Anthropic ya ofrece **computer use** en **Claude Cowork / Claude Code** con la función "mandá una tarea desde el teléfono y Claude la hace en tu compu". Es más maduro pero: (a) hoy es **Mac-first** (Windows es más limitado), (b) **no** trae la capa de voz tipo Jarvis. Si el usuario migrara a Mac y no necesitara voz, gran parte de esto ya existe listo. Como el objetivo incluye **Windows + voz + modo llamada**, se procede con el build propio y se usa la **API de computer use** solo como herramienta interna (Fase 3).

---

## 1. Arquitectura

```
  CELULAR (Telegram)                         PC WINDOWS (agente residente)
 ┌────────────────┐   internet   ┌───────────────────────────────────────────────┐
 │  texto / voz    │ ───────────▶ │  interfaces/telegram_bot.py                    │
 │  (y "llamada")  │ ◀─────────── │      │  (allowlist de chat_id)                 │
 └────────────────┘   respuesta   │      ▼                                          │
                                   │  core/stt.py  (voz → texto, si es nota de voz) │
                                   │      │                                          │
                                   │      ▼                                          │
                                   │  core/orchestrator.py  ── Claude API (tool use)│
                                   │      │        ▲                                 │
                                   │      │ tool_use│ tool_result                    │
                                   │      ▼        │                                 │
                                   │  core/tools.py  (open_app, type_text, click,   │
                                   │      │           run_shell [guarded], etc.)     │
                                   │      ▼                                          │
                                   │  Windows OS  ◀── eventos reales de mouse/tecla  │
                                   │      │                                          │
                                   │      ▼                                          │
                                   │  resultado / screenshot ──▶ core/tts.py ──▶ 📱  │
                                   └───────────────────────────────────────────────┘
```

**Red / acceso remoto:** todo el tráfico "celular → PC" pasa por los servidores de **Telegram** (polling saliente desde la PC), así que **no hace falta abrir puertos**. Para el modo "llamada" (Fase 4), que usa un servidor local, se accede vía **Tailscale** (VPN mesh, sin exponer nada a internet público).

---

## 2. Stack y dependencias

**Sistema:** Windows 10/11. Python **3.11+**.

### 2.1 Servicios/keys externas necesarias
- **Anthropic API key** → https://console.anthropic.com (para el orquestador y para computer use en Fase 3).
- **Telegram Bot token** → hablar con `@BotFather` en Telegram, comando `/newbot`.
- **Tailscale** (gratis, plan personal) → https://tailscale.com (solo para Fase 4).
- *(Opcional)* key de un TTS en la nube (ElevenLabs u OpenAI) si se quiere voz de mejor calidad que la local.

### 2.2 Dependencias Python (`requirements.txt`)
> Instalar con `pip install -r requirements.txt`. Verificar la última versión estable de cada paquete al construir; los mínimos indicados son orientativos.

```
anthropic>=0.40
python-telegram-bot>=21.0        # bot de Telegram (async)
python-dotenv>=1.0               # cargar .env
faster-whisper>=1.0              # STT local (rápido, corre en CPU o GPU)
sounddevice>=0.4                 # captura de audio (modo llamada)
numpy>=1.26
pyautogui>=0.9.54                # simular mouse/teclado (el "emulador")
pynput>=1.7                      # alternativa/lectura de teclas y hotkeys robustas
pygetwindow>=0.0.9               # enfocar/listar ventanas (Windows)
psutil>=5.9                      # procesos, comprobar si una app corre
mss>=9.0                         # capturas de pantalla rápidas
Pillow>=10.0                     # manipular/redimensionar imágenes para el modelo
pyttsx3>=2.90                    # TTS offline (voz local, sin costo)
requests>=2.31                   # llamadas a TTS/STT en la nube (opcional)
```

**Notas de instalación en Windows:**
- `faster-whisper` descarga el modelo la primera vez. Usar `"base"` o `"small"` para español rápido en CPU; `"medium"` si hay GPU NVIDIA (instalar CUDA/cuDNN o usar `device="cpu", compute_type="int8"`).
- `pyautogui` puede necesitar que la ventana de la app objetivo no esté minimizada para clicks por coordenadas.
- Para hotkeys globales y máxima fiabilidad de tipeo en apps con foco, `pynput` suele ser más confiable que `pyautogui.typewrite`.

### 2.3 (Opcional) Alternativa de STT/TTS en la nube
- **STT nube:** Groq o OpenAI Whisper API (más rápido que CPU local, requiere internet y key). Útil si la PC es lenta.
- **TTS nube:** OpenAI TTS o ElevenLabs (voz mucho más natural que `pyttsx3`).

### 2.4 ¿"Skills" o MCP requeridos por Claude Code?
Este proyecto **no requiere skills especiales de Claude Code** para funcionar; es Python estándar. Recomendaciones para el agente constructor:
- Crear un `CLAUDE.md` en la raíz del repo con las reglas de este documento (fases, seguridad) para mantener el contexto entre sesiones.
- No se necesitan servidores MCP para el build. (Los MCP servers son para que *Claude* hable con servicios externos; acá el que actúa es nuestro propio código.)

---

## 3. Estructura del repositorio

```
jarvis-pc/
├── README.md                 # instrucciones de setup y uso (generar al final de cada fase)
├── CLAUDE.md                 # reglas persistentes para el agente (copiar Fases + Seguridad)
├── requirements.txt
├── .env.example              # plantilla de variables
├── .env                      # real, NO commitear (añadir a .gitignore)
├── config.py                 # carga config desde .env
├── main.py                   # punto de entrada: arranca el bot de Telegram
├── core/
│   ├── __init__.py
│   ├── orchestrator.py       # loop de Claude API + dispatch de tools
│   ├── tools.py              # definiciones (schema) + implementación de tools
│   ├── stt.py                # voz → texto (faster-whisper)
│   ├── tts.py                # texto → voz (pyttsx3 / nube)
│   ├── computer_use.py       # loop agéntico de computer use (Fase 3)
│   └── security.py           # allowlist de usuarios, confirmaciones, logging
├── interfaces/
│   ├── __init__.py
│   ├── telegram_bot.py       # handlers de texto y voz
│   └── voice_call.py         # modo "llamada" push-to-talk (Fase 4)
└── logs/
    └── actions.log           # registro de toda acción ejecutada
```

### `.env.example`
```
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_USER_IDS=111111111        # coma-separado; SOLO estos IDs pueden mandar órdenes
ORCHESTRATOR_MODEL=claude-sonnet-5
WHISPER_MODEL=small
TTS_ENGINE=local                            # local | openai | elevenlabs
CONFIRM_DANGEROUS=true                      # pedir confirmación antes de acciones peligrosas
```

---

## 4. Contrato del orquestador (el "cerebro")

El orquestador implementa el **agent loop** estándar de tool use:

1. Manda a la Claude API el historial + la instrucción del usuario + la lista de **tools**.
2. Si la respuesta trae `stop_reason: "tool_use"`, ejecuta la(s) tool(s) localmente, agrega los `tool_result` al historial y **vuelve a llamar** a la API.
3. Repite hasta que la respuesta sea texto final. Ese texto se devuelve al usuario.

**Modelo por defecto:** `claude-sonnet-5` (buen balance costo/latencia, soporta el set completo de tools). Para tareas de razonamiento complejo, permitir escalar a `claude-opus-4-8` vía config.

### 4.1 Definición de tools (Fase 1) — schema para la API

```python
TOOLS = [
    {
        "name": "open_app",
        "description": "Abre una aplicación por nombre (ej. 'chrome', 'notepad', 'spotify').",
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
        "description": "Escribe texto en la ventana con foco, como si el usuario tecleara.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "press_hotkey",
        "description": "Presiona una combinación de teclas, ej. 'ctrl+c', 'alt+tab', 'win+d'.",
        "input_schema": {
            "type": "object",
            "properties": {"keys": {"type": "string"}},
            "required": ["keys"],
        },
    },
    {
        "name": "focus_window",
        "description": "Trae al frente la ventana cuyo título contenga el texto dado.",
        "input_schema": {
            "type": "object",
            "properties": {"title_substring": {"type": "string"}},
            "required": ["title_substring"],
        },
    },
    {
        "name": "list_windows",
        "description": "Lista los títulos de las ventanas abiertas.",
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
        "description": "Ejecuta un comando de shell de Windows. USO RESTRINGIDO: requiere confirmación si es peligroso.",
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
]
```

### 4.2 System prompt del orquestador (guía)
```
Sos un asistente que controla la PC Windows del usuario en tiempo real mediante herramientas.
Reglas:
- Preferí herramientas específicas (open_app, open_url, press_hotkey) antes que clicks por coordenadas.
- Si necesitás ubicar algo en pantalla, usá screenshot primero y razoná sobre la imagen antes de hacer click.
- Antes de acciones destructivas o irreversibles (borrar, cerrar sin guardar, comandos de sistema), explicá qué vas a hacer y esperá confirmación (la capa de seguridad la gestiona por vos).
- Sé conciso en las respuestas al usuario: confirmá qué hiciste en una o dos frases.
- Si una instrucción es ambigua o peligrosa, pedí aclaración en vez de adivinar.
```

### 4.3 Esqueleto del loop (`core/orchestrator.py`)
```python
import anthropic
from core import tools, security

client = anthropic.Anthropic()  # toma ANTHROPIC_API_KEY del entorno

def run_turn(user_text, history, model):
    history.append({"role": "user", "content": user_text})
    while True:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools.TOOLS,
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            # texto final
            return "".join(b.text for b in resp.content if b.type == "text"), history

        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                # capa de seguridad puede bloquear o pedir confirmación
                result = security.guarded_dispatch(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,   # texto o [{"type":"image",...}] para screenshot
                })
        history.append({"role": "user", "content": tool_results})
```

### 4.4 Esqueleto de una tool (`core/tools.py`)
```python
import pyautogui, pygetwindow as gw, subprocess, mss, base64, io
from PIL import Image

def open_app(name):
    subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
    return f"Abriendo {name}"

def type_text(text):
    pyautogui.typewrite(text, interval=0.01)  # o usar pynput para acentos/UTF-8
    return "Texto escrito"

def press_hotkey(keys):
    pyautogui.hotkey(*keys.split("+"))
    return f"Tecla {keys}"

def screenshot():
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", raw.size, raw.rgb)
    img.thumbnail((1280, 800))           # respetar límites de imagen del modelo
    buf = io.BytesIO(); img.save(buf, format="PNG")
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    return [{"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": b64}}]

# ... resto de tools ...

DISPATCH = {
    "open_app": lambda i: open_app(i["name"]),
    "type_text": lambda i: type_text(i["text"]),
    "press_hotkey": lambda i: press_hotkey(i["keys"]),
    "screenshot": lambda i: screenshot(),
    # ...
}
```

---

## 5. Fases de desarrollo

> Cada fase es entregable y probable por sí sola. **No avanzar sin cumplir los criterios de aceptación.**

### FASE 0 — Setup y esqueleto
**Objetivo:** entorno listo, secretos configurados, repo creado.
**Tareas:**
- Crear estructura de carpetas y `requirements.txt`; crear venv e instalar.
- Configurar `.env` con API key de Anthropic y token de Telegram.
- `config.py` que valida que todas las variables requeridas existan (fallar rápido si falta alguna).
- Prueba "hola mundo": un script que llame a la Claude API y devuelva texto, y un bot de Telegram que responda "pong" a "ping".
**Criterios de aceptación:**
- `python -c "import anthropic; ..."` responde con texto del modelo.
- El bot responde "pong" solo a un `chat_id` de la allowlist; ignora a cualquier otro.

### FASE 1 — Control por TEXTO desde el celular (MVP, ~un fin de semana)
**Objetivo:** escribir por Telegram → el orquestador ejecuta tools → confirma resultado.
**Tareas:**
- Implementar `orchestrator.py` (loop de tool use).
- Implementar en `tools.py`: `open_app`, `open_url`, `type_text`, `press_hotkey`, `focus_window`, `list_windows`, `media_key`.
- `telegram_bot.py`: handler de texto que llama al orquestador y devuelve la respuesta.
- Mantener **historial por usuario** (para pedidos encadenados: "ahora escribí X").
**Criterios de aceptación (probar exactamente estos):**
- "abrí el bloc de notas y escribí Hola mundo" → se abre Notepad y aparece el texto.
- "subí el volumen" / "pausá la música" → funciona vía `media_key`.
- "abrí youtube" → abre el navegador en youtube.com.
- "qué ventanas tengo abiertas" → devuelve la lista.
- Un usuario **no** autorizado que le escriba al bot es ignorado (verificar en logs).

### FASE 2 — VOZ: notas de voz + respuestas habladas
**Objetivo:** mandar una **nota de voz** por Telegram y que la ejecute; respuestas por voz (TTS).
**Tareas:**
- `stt.py`: descargar el `.ogg` de la nota de voz de Telegram, transcribir con `faster-whisper` (idioma español).
- Handler de voz en `telegram_bot.py`: transcribe → pasa el texto al mismo orquestador de Fase 1.
- `tts.py`: convertir la respuesta a audio (`pyttsx3` local por defecto) y responderla como nota de voz.
**Criterios de aceptación:**
- Nota de voz "abrí Spotify y buscá jazz" → se ejecuta.
- La respuesta llega como texto **y** como nota de voz.
- Latencia de transcripción aceptable (< 3 s para frases cortas con modelo `small` en CPU).

### FASE 3 — Modo agéntico (computer use) como herramienta interna
**Objetivo:** para tareas que no se resuelven con tools predefinidas ("ordená los íconos", "en esta web hacé clic en el botón azul de la esquina"), delegar a un loop de **computer use** que ve la pantalla y decide clicks.
**Detalles técnicos (verificar en docs al construir):**
- Tool de computer use: `type: "computer_20251124"`, con `display_width_px`/`display_height_px` reales del monitor.
- Header beta: `anthropic-beta: computer-use-2025-11-24`.
- Modelos compatibles: familia Claude 4.x / Sonnet 5 (confirmar en la doc oficial de tool reference).
- **Advertencia de seguridad de la propia doc:** computer use es susceptible a *prompt injection* (una web puede intentar redirigir a Claude). Correrlo con precaución; no darle acceso a cuentas/datos sensibles sin supervisión.
- **Windows:** la doc nota que computer use funciona mejor en macOS por APIs de accesibilidad; en Windows el mapeo de coordenadas tras redimensionar la captura debe hacerse con cuidado.
**Tareas:**
- `computer_use.py`: implementar el sub-loop (screenshot → acción → screenshot...) usando el `screenshot` y `click`/`type` ya construidos como ejecutores.
- Exponerlo al orquestador principal como una tool `computer_agent(task)` que se usa **solo como fallback**.
**Criterios de aceptación:**
- "en la ventana actual, hacé clic en el botón Guardar" (con un target visible) → lo encuentra y clickea.
- El orquestador prefiere tools específicas y solo recurre a `computer_agent` cuando hace falta.

### FASE 4 — Modo "LLAMADA" por voz (conversación en tiempo real)
**Objetivo:** hablarle de corrido, como una llamada, y que responda por voz mientras ejecuta.
**Enfoque recomendado (pragmático):** una pequeña **web app local** servida por la PC, accesible desde el celular por **Tailscale**, con un botón **push-to-talk** (o detección de voz/VAD para manos libres). No depende de la telefonía real.
**Tareas:**
- `voice_call.py`: servidor local (Flask/FastAPI) con una página que captura audio del micrófono del celular, lo manda a la PC, transcribe (STT streaming o por segmentos con VAD), pasa al orquestador y devuelve TTS.
- Manejar turno de habla: detectar fin de frase por silencio (VAD con `sounddevice` + umbral de energía).
- Servir solo dentro de la red Tailscale (bind a la IP de Tailscale, nunca `0.0.0.0` público).
**Criterios de aceptación:**
- Desde el celular, hablar y escuchar respuesta hablada con latencia conversacional razonable (objetivo < 3–4 s por turno).
- Se puede pedir una acción ("abrí el correo") y confirma por voz al terminar.
**Stretch opcional (llamada telefónica real):** integrar **Twilio Voice** (número real + webhooks de audio). Mucho más complejo y con costo; dejar como fase opcional documentada, no obligatoria.

### FASE 5 — Hardening, autostart y robustez
**Objetivo:** que funcione sola, arranque con la PC y sea segura.
**Tareas:**
- Arranque automático: Task Scheduler de Windows ejecutando `main.py` al iniciar sesión (o servicio con NSSM).
- Reintentos y manejo de errores (la API o la red pueden fallar): capturar excepciones, responder al usuario en vez de crashear.
- Rotación de logs.
- Documentar todo en `README.md`.
**Criterios de aceptación:**
- Reiniciar la PC → el agente vuelve a estar disponible sin intervención.
- Un error en una tool no tira el bot; responde "no pude hacer X porque...".

---

## 6. Seguridad (OBLIGATORIO — leer antes de codear)

Este sistema le da a un teléfono la capacidad de **ejecutar acciones en tu PC**. Tratar la seguridad como requisito, no como extra.

1. **Allowlist de usuarios.** El bot solo obedece a `chat_id` en `TELEGRAM_ALLOWED_USER_IDS`. Cualquier otro mensaje se ignora y se loguea. Verificarlo en **cada** handler.
2. **Comandos peligrosos con confirmación.** `run_shell` y acciones destructivas (borrar archivos, apagar, `format`, etc.) requieren una confirmación explícita del usuario ("sí, confirmo") antes de ejecutarse cuando `CONFIRM_DANGEROUS=true`. Implementar en `security.py` una lista de patrones peligrosos (`del`, `rm`, `format`, `shutdown`, `reg delete`, etc.).
3. **Nada expuesto a internet público.** Telegram usa polling saliente (no requiere puertos abiertos). El servidor de Fase 4 se sirve **solo** por Tailscale.
4. **Logging total.** Registrar en `logs/actions.log` cada instrucción recibida y cada tool ejecutada con timestamp.
5. **Secretos fuera del repo.** `.env` en `.gitignore`. Nunca hardcodear keys.
6. **Prompt injection (Fase 3).** Al usar computer use, asumir que contenido en pantalla/web puede intentar manipular al agente. No darle acceso a banca/credenciales sin supervisión humana.
7. **Kill switch.** Un comando de Telegram `/stop` que pause la ejecución de tools (modo solo-lectura) hasta `/resume`.

---

## 7. Comportamiento esperado (ejemplos de diálogo)

**Texto (Fase 1):**
> **Usuario:** abrí chrome y buscá vuelos a Madrid
> **Asistente:** *(abre Chrome, va a Google, escribe la búsqueda)* Listo, abrí Chrome y busqué "vuelos a Madrid".

> **Usuario:** subí el volumen tres veces
> **Asistente:** *(volup ×3)* Volumen arriba.

**Voz (Fase 2):**
> **Usuario (nota de voz):** "pausá la música y abrí el bloc de notas"
> **Asistente (texto + voz):** Pausé la música y abrí el Bloc de notas.

**Agéntico (Fase 3):**
> **Usuario:** en esta página hacé clic en "Aceptar cookies"
> **Asistente:** *(toma screenshot, ubica el botón, clickea)* Hice clic en "Aceptar cookies".

**Peligroso (Seguridad):**
> **Usuario:** borrá la carpeta Descargas
> **Asistente:** Eso borra archivos de forma permanente. ¿Confirmás? Respondé "sí, confirmo" para proceder.

---

## 8. Orden de trabajo sugerido para el agente (checklist)

- [ ] Fase 0: entorno, secretos, "ping/pong", allowlist.
- [ ] Fase 1: orquestador + tools básicas + texto por Telegram. **← el 60% del sueño ya funciona acá.**
- [ ] Fase 2: STT (notas de voz) + TTS.
- [ ] Fase 3: computer use como fallback.
- [ ] Fase 4: modo "llamada" push-to-talk sobre Tailscale.
- [ ] Fase 5: autostart, robustez, docs.
- [ ] Escribir/actualizar `README.md` al cerrar cada fase.

---

## 9. Riesgos conocidos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Clicks por coordenadas frágiles (la UI cambia) | Preferir tools específicas y atajos de teclado; usar computer use solo de fallback |
| Latencia de STT local en CPU lenta | Usar modelo `small`/`base`, o STT en la nube (Groq/OpenAI) |
| Tipeo con acentos falla en `pyautogui` | Usar `pynput` para caracteres UTF-8 |
| Acceso no autorizado al bot | Allowlist de `chat_id` + logging + `/stop` |
| Prompt injection en computer use | Entorno controlado, sin credenciales sensibles, confirmaciones |
| API/red caídas | Try/except en el loop; responder el error al usuario sin crashear |

---

## 10. Referencias a verificar al construir
- Tool use (agent loop) y **computer use**: doc oficial de la Claude API (tool reference / computer use tool). Confirmar versión de tool (`computer_20251124`), header beta (`computer-use-2025-11-24`) y modelos soportados vigentes.
- `python-telegram-bot`: usar la API **async** v21+ (handlers `async def`).
- `faster-whisper`: parámetros `device`, `compute_type` según CPU/GPU.
- Tailscale: instalar en PC y celular, misma tailnet.

---

*Fin de la especificación. Construir por fases, respetar los criterios de aceptación y la sección de seguridad.*
