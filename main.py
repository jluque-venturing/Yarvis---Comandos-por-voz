import config


def main():
    config.validate()

    from interfaces import telegram_bot

    if config.ENABLE_VOICE_CALL:
        from interfaces import voice_call

        voice_call.start_in_background()

    telegram_bot.run()


if __name__ == "__main__":
    main()
