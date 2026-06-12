import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from movie_bot.config import Settings
from movie_bot.database import MovieRepository


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
LOGGER = logging.getLogger("movie_bot")


class HealthHandler(BaseHTTPRequestHandler):
    ready = False

    def do_GET(self) -> None:
        status = 200 if self.ready else 503
        body = b'{"status":"ok"}' if self.ready else b'{"status":"starting"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def start_health_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def is_admin(update: Update, settings: Settings) -> bool:
    return bool(update.effective_user and update.effective_user.id in settings.admin_ids)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    text = (
        "Welcome. Send me a movie code and I will return the matching movie.\n\n"
        "Example: 1024"
    )
    if is_admin(update, settings):
        text += (
            "\n\nAdmin commands:\n"
            "/add <code> <channel_message_id> [title]\n"
            "/delete <code>\n"
            "/stats\n"
            "/health"
        )
    await update.effective_message.reply_text(text)


async def health_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Bot and database are running.")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    repository: MovieRepository = context.application.bot_data["repository"]
    if not is_admin(update, settings):
        await update.effective_message.reply_text("This command is for administrators.")
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /add <code> <channel_message_id> [title]"
        )
        return
    code = context.args[0].strip().lower()
    try:
        message_id = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("channel_message_id must be a number.")
        return
    title = " ".join(context.args[2:]).strip() or None
    repository.upsert(code, message_id, title)
    await update.effective_message.reply_text(f"Saved movie code: {code}")


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    repository: MovieRepository = context.application.bot_data["repository"]
    if not is_admin(update, settings):
        await update.effective_message.reply_text("This command is for administrators.")
        return
    if len(context.args) != 1:
        await update.effective_message.reply_text("Usage: /delete <code>")
        return
    deleted = repository.delete(context.args[0].strip().lower())
    await update.effective_message.reply_text(
        "Movie deleted." if deleted else "Movie code not found."
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    repository: MovieRepository = context.application.bot_data["repository"]
    if not is_admin(update, settings):
        await update.effective_message.reply_text("This command is for administrators.")
        return
    await update.effective_message.reply_text(
        f"Movies: {repository.count()}\nRequests served: {repository.total_requests()}"
    )


async def movie_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    repository: MovieRepository = context.application.bot_data["repository"]
    code = (update.effective_message.text or "").strip().lower()
    movie = repository.get(code)
    if movie is None:
        await update.effective_message.reply_text(
            "Movie code not found. Check the code and try again."
        )
        return
    try:
        await context.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=settings.movie_channel_id,
            message_id=movie.message_id,
        )
        repository.record_request(code)
    except TelegramError:
        LOGGER.exception("Could not copy channel message %s", movie.message_id)
        await update.effective_message.reply_text(
            "The movie is temporarily unavailable. An administrator has been notified."
        )
        await notify_admins(
            context.application,
            f"Failed to deliver code {code} from channel message {movie.message_id}.",
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, RetryAfter):
        LOGGER.warning("Telegram rate limit; retry after %s seconds", error.retry_after)
    elif isinstance(error, (TimedOut, NetworkError)):
        LOGGER.warning("Temporary Telegram API error: %s", error)
    else:
        LOGGER.error(
            "Unhandled update error",
            exc_info=(type(error), error, error.__traceback__),
        )


async def notify_admins(application: Application, text: str) -> None:
    settings: Settings = application.bot_data["settings"]
    for admin_id in settings.admin_ids:
        try:
            await application.bot.send_message(admin_id, text)
        except TelegramError:
            LOGGER.warning("Could not notify administrator %s", admin_id)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            ("start", "Start the bot"),
            ("health", "Check bot status"),
            ("add", "Add or update a movie (admin)"),
            ("delete", "Delete a movie (admin)"),
            ("stats", "Show statistics (admin)"),
        ]
    )
    HealthHandler.ready = True
    settings: Settings = application.bot_data["settings"]
    if settings.sleep_warning:
        await notify_admins(application, settings.sleep_warning)
    LOGGER.info("Bot initialized as @%s", (await application.bot.get_me()).username)


async def post_shutdown(_application: Application) -> None:
    HealthHandler.ready = False


def build_application(settings: Settings, repository: MovieRepository) -> Application:
    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .connect_timeout(20)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(20)
        .get_updates_connect_timeout(20)
        .get_updates_read_timeout(30)
        .get_updates_pool_timeout(20)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data.update(settings=settings, repository=repository)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, movie_lookup)
    )
    application.add_error_handler(error_handler)
    return application


def run_bot(settings: Settings, repository: MovieRepository) -> None:
    application = build_application(settings, repository)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
        drop_pending_updates=False,
        poll_interval=1.0,
        timeout=30,
        stop_signals=None if os.name == "nt" else (signal.SIGINT, signal.SIGTERM),
    )


def main() -> None:
    settings = Settings.from_environment()
    repository = MovieRepository(settings.database_url)
    repository.initialize()
    health_server = start_health_server(settings.port)
    retry_delay = 5
    try:
        while True:
            try:
                run_bot(settings, repository)
                break
            except KeyboardInterrupt:
                break
            except Exception:
                HealthHandler.ready = False
                LOGGER.exception("Bot crashed; restarting in %s seconds", retry_delay)
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 300)
    finally:
        health_server.shutdown()
        repository.close()


if __name__ == "__main__":
    main()
