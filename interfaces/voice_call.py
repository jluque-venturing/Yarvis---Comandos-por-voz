import threading

from flask import Flask, Response, request, send_file

import config
from core import orchestrator, security, stt, tts

app = Flask(__name__)

# chat_id interno para el modo llamada (comparte capa de seguridad y confirmaciones)
_CALL_CHAT = -999
_history = []

PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jarvis - Llamada</title>
<style>
  body { font-family: system-ui, sans-serif; background:#111; color:#eee; text-align:center; padding:2rem; }
  #btn { font-size:1.5rem; padding:1.5rem 2rem; border:none; border-radius:1rem; background:#2b6; color:#fff; }
  #btn.rec { background:#c33; }
  #log { margin-top:1.5rem; white-space:pre-wrap; text-align:left; max-width:40rem; margin-inline:auto; }
</style>
</head>
<body>
  <h1>Jarvis</h1>
  <button id="btn">Mantener para hablar</button>
  <div id="log"></div>
<script>
let rec, chunks = [];
const btn = document.getElementById('btn'), log = document.getElementById('log');
function say(m){ log.textContent = m + "\\n" + log.textContent; }

async function start(){
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  rec = new MediaRecorder(stream);
  chunks = [];
  rec.ondataavailable = e => chunks.push(e.data);
  rec.onstop = send;
  rec.start();
  btn.classList.add('rec'); btn.textContent = 'Grabando...';
}
function stop(){ if(rec && rec.state === 'recording'){ rec.stop(); } btn.classList.remove('rec'); btn.textContent = 'Mantener para hablar'; }

async function send(){
  const blob = new Blob(chunks, {type:'audio/webm'});
  const fd = new FormData(); fd.append('audio', blob, 'audio.webm');
  say('Procesando...');
  const r = await fetch('/talk', {method:'POST', body:fd});
  if(!r.ok){ say('Error: ' + r.status); return; }
  const buf = await r.arrayBuffer();
  new Audio(URL.createObjectURL(new Blob([buf], {type:'audio/wav'}))).play();
  say('Respuesta reproducida.');
}

btn.addEventListener('mousedown', start);
btn.addEventListener('mouseup', stop);
btn.addEventListener('touchstart', e => { e.preventDefault(); start(); });
btn.addEventListener('touchend', e => { e.preventDefault(); stop(); });
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html")


@app.route("/talk", methods=["POST"])
def talk():
    global _history
    f = request.files.get("audio")
    if not f:
        return {"error": "sin audio"}, 400

    inp = config.RUNTIME_DIR / "call_in.webm"
    f.save(str(inp))
    text = stt.transcribe(str(inp))
    if not text:
        return {"error": "no entendi el audio"}, 422

    if security.is_confirmation_phrase(text):
        security.grant_confirmation(_CALL_CHAT)
    else:
        security.clear_confirmation(_CALL_CHAT)

    reply, _history = orchestrator.run_turn(
        text, _history, config.ORCHESTRATOR_MODEL, _CALL_CHAT
    )
    out = config.RUNTIME_DIR / "call_out.wav"
    tts.synth_to_file(reply or "Listo.", str(out))
    return send_file(str(out), mimetype="audio/wav")


def start_in_background():
    def _serve():
        app.run(
            host=config.VOICE_CALL_HOST,
            port=config.VOICE_CALL_PORT,
            threaded=True,
            use_reloader=False,
        )

    threading.Thread(target=_serve, daemon=True).start()
    security.logger.info(
        f"Modo llamada en http://{config.VOICE_CALL_HOST}:{config.VOICE_CALL_PORT}"
    )
