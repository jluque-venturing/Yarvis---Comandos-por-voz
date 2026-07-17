# Jarvis PC — asistente de voz/texto para controlar tu PC

Controlá tu PC Windows desde el celular por **Telegram** (texto y notas de voz).
Claude interpreta la orden y ejecuta acciones reales: abrir apps, escribir, atajos,
volumen/multimedia, comandos, capturas y hasta clicks "mirando" la pantalla.

```
   CELULAR (Telegram)                    PC WINDOWS (agente residente)
 ┌────────────────┐   internet   ┌──────────────────────────────────────┐
 │ texto / voz    │ ───────────▶ │ telegram_bot ─▶ stt ─▶ orchestrator   │
 │ (y "llamada")  │ ◀─────────── │                        │  (Claude)    │
 └────────────────┘   respuesta  │                        ▼             │
                                  │            security ─▶ tools ─▶ Windows│
                                  │                        │             │
                                  │                        ▼             │
                                  │              tts ─▶ 📱 (voz de vuelta) │
                                  └──────────────────────────────────────┘
```

---

## 1. Requisitos previos (credenciales)

Necesitás 3 cosas. Cargalas en un archivo `.env` (copiá `.env.example`).

| Variable | Cómo obtenerla |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → API Keys → Create Key |
| `TELEGRAM_BOT_TOKEN` | En Telegram hablá con **@BotFather** → `/newbot` → te da el token |
| `TELEGRAM_ALLOWED_USER_IDS` | Tu **chat_id**: escribile a **@userinfobot** en Telegram y te lo dice |

> ⚠️ El `.env` NO se sube a git (está en `.gitignore`). Nunca compartas tus keys.

---

## 2. Instalación

```powershell
# 1) Crear y activar entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) Instalar dependencias
pip install -r requirements.txt

# 3) Configurar secretos
copy .env.example .env
notepad .env      # completá las 3 variables obligatorias
```

> La primera nota de voz descarga el modelo de `faster-whisper` (`small`).
> Si tu PC es lenta, bajá a `WHISPER_MODEL=base` en `.env`.

---

## 3. Ejecutar

```powershell
python main.py
```

Deberías ver `Bot de Telegram iniciado (polling).` en la consola.
En Telegram, escribile al bot:

- `ping` → responde `pong` (prueba de vida)
- `abrí el bloc de notas y escribí Hola mundo`
- `subí el volumen` / `pausá la música`
- `abrí youtube`
- `qué ventanas tengo abiertas`

Un usuario **no autorizado** que le escriba al bot es ignorado (queda en `logs/actions.log`).

---

## 4. Comandos del bot

| Comando | Qué hace |
|---|---|
| `/ping` | Prueba de vida |
| `/stop` | **Kill switch**: modo solo-lectura (no ejecuta acciones) |
| `/resume` | Reanuda la ejecución |
| `/reset` | Borra el historial de la conversación |
| `/help` | Ayuda |

---

## 5. Fases implementadas

| Fase | Qué incluye | Archivo(s) |
|---|---|---|
| 0 | Setup, secretos, ping/pong, allowlist | `config.py`, `main.py` |
| 1 | Orquestador + tools + control por texto | `core/orchestrator.py`, `core/tools.py` |
| 2 | Notas de voz (STT) + respuestas habladas (TTS) | `core/stt.py`, `core/tts.py` |
| 3 | Computer use (fallback agéntico) | `core/computer_use.py` |
| 4 | Modo llamada push-to-talk (web local) | `interfaces/voice_call.py` |
| 5 | Autostart, robustez, logging con rotación | ver abajo |

### Notas por fase
- **Fase 2 (voz de vuelta):** Telegram exige OGG/Opus para "notas de voz". Sin `ffmpeg`
  instalado, la respuesta llega como **audio común** (igual se escucha). Para notas de voz
  reales, instalá `ffmpeg` y quedará automático.
- **Fase 3 (computer use):** es un *fallback*. Confirmá en la doc oficial de Anthropic la
  versión de tool (`computer_20251124`) y el header beta (`computer-use-2025-11-24`) al usarlo,
  porque pueden cambiar. Cuidado con *prompt injection*: no lo uses sin supervisión en sitios
  con datos sensibles.
- **Fase 4 (modo llamada):** poné `ENABLE_VOICE_CALL=true` en `.env`. Serví **solo** por Tailscale
  (nunca `0.0.0.0` público). Con Tailscale instalado en PC y celular (misma tailnet), poné
  `VOICE_CALL_HOST` = tu IP de Tailscale y abrí `http://<IP-tailscale>:8760` desde el celu.

---

## 6. Autostart (Fase 5)

Que arranque solo al iniciar sesión en Windows, con el **Programador de tareas**:

1. Abrí *Programador de tareas* → *Crear tarea básica*.
2. Desencadenador: *Al iniciar sesión*.
3. Acción: *Iniciar un programa*.
   - Programa: `C:\Proyectos\Yarvis - Comandos por voz\.venv\Scripts\pythonw.exe`
   - Argumentos: `main.py`
   - Iniciar en: `C:\Proyectos\Yarvis - Comandos por voz`
4. Reiniciá la PC y probá que el bot responda sin abrir nada a mano.

> `pythonw.exe` corre sin ventana de consola. Los errores igual quedan en `logs/actions.log`.

---

## 7. Seguridad

- **Allowlist** de `chat_id`: solo los IDs de `TELEGRAM_ALLOWED_USER_IDS` mandan órdenes.
- **Confirmación** para comandos peligrosos (`del`, `format`, `shutdown`, `rm`, etc.):
  el bot bloquea y pide que respondas exactamente `si, confirmo`.
- **Kill switch**: `/stop` deja el bot en solo-lectura hasta `/resume`.
- **Logging** de toda orden y acción en `logs/actions.log` (rota a 1 MB × 5 archivos).
- **Sin puertos abiertos**: Telegram usa polling saliente; la Fase 4 va por Tailscale.

---

## 8. Estructura

```
.
├── main.py                  # punto de entrada
├── config.py                # carga y valida .env
├── core/
│   ├── orchestrator.py      # loop de Claude + tool use
│   ├── tools.py             # esquema + implementación de acciones
│   ├── security.py          # allowlist, confirmaciones, kill switch, logging
│   ├── stt.py               # voz -> texto (faster-whisper)
│   ├── tts.py               # texto -> voz (pyttsx3)
│   └── computer_use.py      # fallback agéntico (Fase 3)
├── interfaces/
│   ├── telegram_bot.py      # handlers de texto y voz
│   └── voice_call.py        # modo llamada push-to-talk (Fase 4)
├── logs/actions.log         # registro (se crea al correr)
└── runtime/                 # audios temporales (se crea al correr)
```

---

## 9. Tips (VS Code y Git)

**Atajos de VS Code útiles para este proyecto:**
- `Ctrl + Ñ` : abrir/cerrar la terminal integrada
- `Ctrl + P` : saltar rápido a un archivo (ej. `orchestrator.py`)
- `Ctrl + Shift + F` : buscar en TODO el proyecto (ej. dónde se usa `guarded_dispatch`)
- `F5` : correr/depurar; `Shift + F5` : detener
- `Ctrl + /` : comentar/descomentar la línea

**Git básico:**
- `git status` → ver qué cambió
- `git add .` → preparar cambios; `git commit -m "mensaje"` → guardar snapshot
- Tip: el `.env` está en `.gitignore`, así que tus keys **nunca** se suben.
  Verificá con `git status` que `.env` no aparezca antes de un commit.
