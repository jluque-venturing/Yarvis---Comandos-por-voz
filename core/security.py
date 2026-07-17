import logging
import re
from logging.handlers import RotatingFileHandler

import config
from core import tools

# --- Logging con rotacion (Fase 5) ---
logger = logging.getLogger("jarvis")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fh = RotatingFileHandler(
        config.LOGS_DIR / "actions.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_fh)
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(_ch)

# Tools que se permiten incluso en modo solo-lectura (/stop)
READ_ONLY = {"screenshot", "list_windows"}

_DANGEROUS_PATTERNS = [
    r"\bdel\b", r"\berase\b", r"\brmdir\b", r"\brd\b", r"\brm\b",
    r"\bformat\b", r"\bdiskpart\b", r"\bshutdown\b", r"\brestart\b",
    r"reg\s+delete", r"remove-item", r"rm\s+-rf", r"\bmkfs\b",
    r"\bfdisk\b", r"cipher\s+/w", r"\bschtasks\b", r"\btaskkill\b",
]
_dangerous_re = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)

_CONFIRM_PHRASES = ("si, confirmo", "sí, confirmo", "si confirmo", "sí confirmo", "confirmo")

_paused = False
_confirmations = set()  # chat_ids con confirmacion pendiente de consumir


def is_allowed(user_id):
    return user_id in config.TELEGRAM_ALLOWED_USER_IDS


def log_ignored(user_id, text):
    logger.warning(f"IGNORADO usuario no autorizado id={user_id} texto={text!r}")


def log_incoming(chat_id, text):
    logger.info(f"IN chat={chat_id} {text!r}")


def pause():
    global _paused
    _paused = True
    logger.info("KILL SWITCH: pausado (modo solo-lectura)")


def resume():
    global _paused
    _paused = False
    logger.info("KILL SWITCH: reanudado")


def is_paused():
    return _paused


def is_confirmation_phrase(text):
    t = (text or "").strip().lower()
    return any(t == p or t.startswith(p) for p in _CONFIRM_PHRASES)


def grant_confirmation(chat_id):
    _confirmations.add(chat_id)
    logger.info(f"confirmacion otorgada chat={chat_id}")


def clear_confirmation(chat_id):
    _confirmations.discard(chat_id)


def _consume_confirmation(chat_id):
    if chat_id in _confirmations:
        _confirmations.discard(chat_id)
        return True
    return False


def _is_dangerous(name, tool_input):
    if name == "run_shell":
        return bool(_dangerous_re.search(tool_input.get("command", "")))
    return False


def guarded_dispatch(chat_id, name, tool_input):
    logger.info(f"TOOL chat={chat_id} {name} {tool_input!r}")

    if name not in tools.DISPATCH:
        return f"Herramienta desconocida: {name}"

    if is_paused() and name not in READ_ONLY:
        return "Modo solo-lectura activo (/stop). Envia /resume para reanudar la ejecucion."

    if _is_dangerous(name, tool_input) and config.CONFIRM_DANGEROUS:
        if not _consume_confirmation(chat_id):
            return (
                "ACCION PELIGROSA BLOQUEADA: "
                + tool_input.get("command", "")
                + ". Explicale al usuario que hace y pedile que responda exactamente "
                "'si, confirmo' para ejecutarla."
            )

    try:
        result = tools.DISPATCH[name](tool_input)
        logger.info(f"TOOL OK {name}")
        return result
    except Exception as e:  # una tool que falla no debe tirar el bot
        logger.exception(f"TOOL ERROR {name}")
        return f"No pude ejecutar {name}: {e}"
