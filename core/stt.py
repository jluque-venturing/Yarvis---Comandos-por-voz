import config

_model = None


def _get_model():
    global _model
    if _model is None:
        # import perezoso: la primera vez descarga el modelo de faster-whisper
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
    return _model


def transcribe(path):
    segments, _info = _get_model().transcribe(path, language="es")
    return "".join(s.text for s in segments).strip()
