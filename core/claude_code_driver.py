import json
import os
import shutil
import subprocess

import config
from core import security

# NOTA: los flags de Claude Code (--permission-mode, --output-format json, --resume)
# pueden variar segun la version instalada. Si el modo falla, verificar con:
#   claude -p --output-format json --permission-mode plan   (y escribir el prompt)
# y ajustar aca los nombres de flags.


def _invoke(prompt, session_id, permission_mode):
    if shutil.which(config.CLAUDE_CODE_CMD) is None:
        return {
            "error": (
                f"No encontre Claude Code (comando '{config.CLAUDE_CODE_CMD}') en el PATH. "
                "Instalalo y logueate; verifica con 'claude --version'."
            )
        }

    args = [
        config.CLAUDE_CODE_CMD,
        "-p",
        "--output-format", "json",
        "--permission-mode", permission_mode,
    ]
    if session_id:
        args += ["--resume", session_id]

    try:
        # El prompt va por stdin para evitar problemas de comillas/caracteres especiales.
        r = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            errors="replace",
            cwd=str(config.CLAUDE_CODE_PROJECT_DIR),
            timeout=config.CLAUDE_CODE_TIMEOUT,
            shell=(os.name == "nt"),
        )
    except subprocess.TimeoutExpired:
        return {"error": "Claude Code tardo demasiado (timeout). Proba una tarea mas chica."}

    out = (r.stdout or "").strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        msg = out or (r.stderr or "").strip() or "(sin salida)"
        return {"error": msg[:1500]}

    if data.get("is_error"):
        return {"error": (data.get("result") or "Claude Code reporto un error.")[:1500]}
    return data


def _format(data):
    text = data.get("result") or data.get("text") or "(sin respuesta)"
    cost = data.get("total_cost_usd")
    if cost is not None:
        try:
            text += f"\n\n💰 ~US${float(cost):.4f}"
        except (TypeError, ValueError):
            pass
    return text


def run(user_text, state, chat_id):
    state = state or {"session_id": None, "pending": False}

    # Paso "aplicar": hay un plan pendiente y el usuario confirmo
    if (
        config.CLAUDE_CODE_CONFIRM
        and state.get("pending")
        and security.is_confirmation_phrase(user_text)
    ):
        data = _invoke(
            "Aplica el plan que propusiste.",
            state.get("session_id"),
            "bypassPermissions",
        )
        if "error" in data:
            return f"No pude aplicar: {data['error']}", state
        state["session_id"] = data.get("session_id") or state.get("session_id")
        state["pending"] = False
        return "✅ Aplicado.\n\n" + _format(data), state

    # Turno nuevo
    if config.CLAUDE_CODE_CONFIRM:
        data = _invoke(user_text, state.get("session_id"), "plan")
        if "error" in data:
            return data["error"], state
        state["session_id"] = data.get("session_id") or state.get("session_id")
        state["pending"] = True
        return (
            _format(data)
            + "\n\n(Si querés que ejecute los cambios, respondé «sí, confirmo».)",
            state,
        )

    data = _invoke(user_text, state.get("session_id"), "bypassPermissions")
    if "error" in data:
        return data["error"], state
    state["session_id"] = data.get("session_id") or state.get("session_id")
    state["pending"] = False
    return _format(data), state
