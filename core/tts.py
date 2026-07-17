_SPANISH_HINTS = ("spanish", "español", "espanol", "helena", "sabina", "laura", "pablo")


def synth_to_file(text, out_path):
    import pyttsx3

    engine = pyttsx3.init()
    try:
        for v in engine.getProperty("voices"):
            name = (v.name or "").lower()
            if any(h in name for h in _SPANISH_HINTS):
                engine.setProperty("voice", v.id)
                break
        engine.save_to_file(text, out_path)
        engine.runAndWait()
    finally:
        engine.stop()
    return out_path
