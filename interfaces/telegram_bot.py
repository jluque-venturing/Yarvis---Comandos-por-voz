import asyncio

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from core import engines, security, stt, tts

# Estado de conversacion por (chat_id, modo). Cada modo mantiene su propio estado.
STATES = {}


def _apply_confirmation(chat_id, text):
    if security.is_confirmation_phrase(text):
        security.grant_confirmation(chat_id)
    else:
        security.clear_confirmation(chat_id)


async def _process(update, text):
    chat_id = update.effective_chat.id
    _apply_confirmation(chat_id, text)
    security.log_incoming(chat_id, text)
    key = (chat_id, engines.get_active())
    state = STATES.get(key)
    reply, state = await asyncio.to_thread(engines.run, text, state, chat_id)
    STATES[key] = state
    return reply


async def on_text(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not security.is_allowed(user.id):
        security.log_ignored(user.id, update.message.text)
        return

    text = update.message.text
    if text.strip().lower() == "ping":
        await update.message.reply_text("pong")
        return

    try:
        reply = await _process(update, text)
    except Exception as e:
        security.logger.exception("error en on_text")
        reply = f"Ocurrio un error: {e}"
    await update.message.reply_text(reply or "Listo.")


async def on_voice(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not security.is_allowed(user.id):
        security.log_ignored(user.id, "[voz]")
        return

    ogg = config.RUNTIME_DIR / f"in_{update.message.message_id}.ogg"
    reply = "Listo."
    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        await tg_file.download_to_drive(str(ogg))
        text = await asyncio.to_thread(stt.transcribe, str(ogg))
        if not text:
            await update.message.reply_text("No entendi el audio, probá de nuevo.")
            return
        await update.message.reply_text(f"🗣️ Entendi: {text}")
        reply = await _process(update, text)
    except Exception as e:
        security.logger.exception("error en on_voice")
        reply = f"Ocurrio un error: {e}"
    finally:
        try:
            ogg.unlink()
        except OSError:
            pass

    await update.message.reply_text(reply or "Listo.")
    await _reply_voice(update, reply or "Listo.")


async def _reply_voice(update, text):
    wav = config.RUNTIME_DIR / f"out_{update.message.message_id}.wav"
    try:
        await asyncio.to_thread(tts.synth_to_file, text, str(wav))
        with open(wav, "rb") as f:
            data = f.read()
        try:
            await update.message.reply_voice(data)
        except Exception:
            # Telegram exige OGG/Opus para notas de voz; sin ffmpeg cae a audio comun
            await update.message.reply_audio(data)
    except Exception:
        security.logger.exception("error en TTS")
    finally:
        try:
            wav.unlink()
        except OSError:
            pass


async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE):
    if not security.is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "Jarvis activo. Escribime o mandame una nota de voz. /help para comandos."
    )


async def cmd_help(update, context: ContextTypes.DEFAULT_TYPE):
    if not security.is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "/mode muestra o cambia el modo (claude_code | pc_tools)\n"
        "/ping prueba de vida\n"
        "/stop pausa la ejecucion de acciones (solo-lectura, modo pc_tools)\n"
        "/resume reanuda\n"
        "/reset borra el estado de la conversacion del modo actual"
    )


async def cmd_mode(update, context: ContextTypes.DEFAULT_TYPE):
    if not security.is_allowed(update.effective_user.id):
        return
    arg = context.args[0].strip() if context.args else ""
    if arg and engines.set_active(arg):
        await update.message.reply_text(f"Modo activo: {arg}")
    else:
        await update.message.reply_text(
            f"Modo actual: {engines.get_active()}\n"
            "Opciones:\n"
            "/mode claude_code  (Jarvis maneja tu Claude Code)\n"
            "/mode pc_tools     (Jarvis controla la PC via API)"
        )


async def cmd_ping(update, context: ContextTypes.DEFAULT_TYPE):
    if not security.is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("pong")


async def cmd_stop(update, context: ContextTypes.DEFAULT_TYPE):
    if not security.is_allowed(update.effective_user.id):
        return
    security.pause()
    await update.message.reply_text("⏸️ Modo solo-lectura. /resume para reanudar.")


async def cmd_resume(update, context: ContextTypes.DEFAULT_TYPE):
    if not security.is_allowed(update.effective_user.id):
        return
    security.resume()
    await update.message.reply_text("▶️ Acciones reanudadas.")


async def cmd_reset(update, context: ContextTypes.DEFAULT_TYPE):
    if not security.is_allowed(update.effective_user.id):
        return
    STATES.pop((update.effective_chat.id, engines.get_active()), None)
    await update.message.reply_text("🧹 Estado borrado (modo actual).")


def run():
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    security.logger.info("Bot de Telegram iniciado (polling).")
    app.run_polling()
