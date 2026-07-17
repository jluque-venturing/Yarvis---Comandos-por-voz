import config
from core import claude_code_driver, orchestrator

# Cada engine expone run(user_text, state, chat_id) -> (reply, new_state)
REGISTRY = {
    "pc_tools": orchestrator,
    "claude_code": claude_code_driver,
}

_active = config.ASSISTANT_MODE if config.ASSISTANT_MODE in REGISTRY else "claude_code"


def get_active():
    return _active


def set_active(mode):
    global _active
    if mode in REGISTRY:
        _active = mode
        return True
    return False


def run(user_text, state, chat_id):
    return REGISTRY[_active].run(user_text, state, chat_id)
