import logging

from dotenv import load_dotenv

load_dotenv()  # esporta .env in os.environ per le librerie (Tavily, DeepSeek)

from telegram.ext import Application, MessageHandler, filters

from bot.config import get_settings
from bot.handlers import handle_message

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)


def main() -> None:
    settings = get_settings()
    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN.get_secret_value())
        .build()
    )
    app.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO | filters.CAPTION, handle_message)
    )
    logging.getLogger(__name__).info("FactChecking bot avviato (polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
