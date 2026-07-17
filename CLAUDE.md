# Reglas del proyecto Jarvis PC (para el agente y para humanos)

Asistente residente en Windows que recibe ordenes desde Telegram (texto y voz),
las interpreta con la Claude API (tool use) y ejecuta acciones reales sobre la PC.

## Idioma
- Codigo, comentarios y archivos de plan: **espanol** (este proyecto esta fuera de C:\Venturing).
- Comentarios: casi ninguno. Solo cuando el POR QUE no es obvio.

## Arquitectura (resumen)
```
Celular (Telegram)  ->  interfaces/telegram_bot.py
                            -> core/stt.py         (voz -> texto)
                            -> core/orchestrator.py (loop Claude + tool use)
                                 -> core/security.py (allowlist, confirmaciones, log)
                                      -> core/tools.py (acciones reales sobre Windows)
                            -> core/tts.py         (texto -> voz)
```

## Fases (no avanzar sin cumplir criterios de aceptacion)
- Fase 0: setup, secretos, ping/pong, allowlist.
- Fase 1: orquestador + tools + control por texto. (el 60% del sueno)
- Fase 2: STT (notas de voz) + TTS.
- Fase 3: computer use como fallback (core/computer_use.py).
- Fase 4: modo llamada push-to-talk (interfaces/voice_call.py) sobre Tailscale.
- Fase 5: autostart, robustez, docs.

## Seguridad (obligatorio)
1. Allowlist de chat_id en TELEGRAM_ALLOWED_USER_IDS. Se verifica en CADA handler.
2. Comandos peligrosos (run_shell con del/format/shutdown/etc.) requieren "si, confirmo".
3. Nada expuesto a internet publico. Telegram usa polling saliente. Fase 4 solo por Tailscale.
4. Logging total en logs/actions.log (con rotacion).
5. Secretos en .env (nunca commitear; esta en .gitignore).
6. Kill switch: /stop (solo-lectura) y /resume.
7. Fase 3 (computer use): asumir prompt injection; sin credenciales sensibles sin supervision.

## Modelo
- Orquestador por defecto: claude-sonnet-5 (configurable en .env).
- Escalable a claude-opus-4-8 cambiando ORCHESTRATOR_MODEL.
