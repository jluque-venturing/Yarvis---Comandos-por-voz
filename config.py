import os
import pathlib

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = pathlib.Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
RUNTIME_DIR = BASE_DIR / "runtime"
LOGS_DIR.mkdir(exist_ok=True)
RUNTIME_DIR.mkdir(exist_ok=True)


def _parse_ids(raw):
    ids = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            pass
    return ids


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ALLOWED_USER_IDS = _parse_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))

ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "claude-sonnet-5").strip()
ORCHESTRATOR_MAX_TOKENS = int(os.getenv("ORCHESTRATOR_MAX_TOKENS", "2048"))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small").strip()
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip()
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip()

TTS_ENGINE = os.getenv("TTS_ENGINE", "local").strip()

CONFIRM_DANGEROUS = os.getenv("CONFIRM_DANGEROUS", "true").strip().lower() == "true"

ENABLE_VOICE_CALL = os.getenv("ENABLE_VOICE_CALL", "false").strip().lower() == "true"
VOICE_CALL_HOST = os.getenv("VOICE_CALL_HOST", "127.0.0.1").strip()
VOICE_CALL_PORT = int(os.getenv("VOICE_CALL_PORT", "8760"))


def validate():
    faltantes = []
    if not ANTHROPIC_API_KEY:
        faltantes.append("ANTHROPIC_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        faltantes.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_ALLOWED_USER_IDS:
        faltantes.append("TELEGRAM_ALLOWED_USER_IDS")
    if faltantes:
        raise SystemExit(
            "Faltan variables en .env: "
            + ", ".join(faltantes)
            + ".\nCopia .env.example a .env y completalas antes de arrancar."
        )
