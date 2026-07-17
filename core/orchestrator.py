import anthropic

import config
from core import security, tools

client = anthropic.Anthropic()

SYSTEM_PROMPT = """Sos Jarvis, un asistente que controla la PC Windows del usuario en tiempo real mediante herramientas.
Reglas:
- Prefiere herramientas especificas (open_app, open_url, press_hotkey, media_key) antes que clicks por coordenadas.
- Si necesitas ubicar algo en pantalla, usa screenshot primero y razona sobre la imagen antes de hacer click.
- Usa computer_agent SOLO como ultimo recurso, cuando ninguna tool especifica resuelve la tarea.
- Antes de acciones destructivas o irreversibles (borrar, cerrar sin guardar, comandos de sistema), explica que vas a hacer y espera confirmacion (la capa de seguridad la gestiona por vos; si una tool responde que quedo bloqueada, pedile al usuario que responda 'si, confirmo').
- Se conciso: confirma que hiciste en una o dos frases.
- Si una instruccion es ambigua o peligrosa, pedi aclaracion en vez de adivinar.
- Respondes siempre en espanol rioplatense, natural y directo."""

MAX_LOOPS = 15


def run_turn(user_text, history, model=None, chat_id=0):
    model = model or config.ORCHESTRATOR_MODEL
    history.append({"role": "user", "content": user_text})

    for _ in range(MAX_LOOPS):
        resp = client.messages.create(
            model=model,
            max_tokens=config.ORCHESTRATOR_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools.TOOLS,
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "refusal":
            return "No puedo hacer eso por razones de seguridad.", history

        if resp.stop_reason != "tool_use":
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", None) == "text"
            )
            return text.strip() or "Listo.", history

        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                result = security.guarded_dispatch(chat_id, block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
        history.append({"role": "user", "content": tool_results})

    return "Alcance el limite de pasos sin terminar la tarea.", history
