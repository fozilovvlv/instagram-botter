# Telegram Movie Bot

A production-oriented Telegram bot that maps short movie codes to posts in a
private or public Telegram channel. Users send a code; the bot copies the
configured channel message into their chat.

## Configuration

Required environment variables:

- `BOT_TOKEN`: token from BotFather.
- `ADMIN_IDS`: comma-separated Telegram user IDs.
- `MOVIE_CHANNEL_ID`: source channel ID, usually starting with `-100`.
- `DATABASE_URL`: persistent PostgreSQL URL in production. Local development
  defaults to `sqlite:///data/movies.db`.

The bot must be an administrator in the movie channel so it can copy posts.

## Run locally

```bash
python -m venv .venv
pip install -r requirements-dev.txt
cp .env.example .env
python main.py
```

On PowerShell, load the values from `.env` into the current environment before
running the final command. Docker users can run `docker compose up --build`.

## Admin workflow

1. Publish a movie to the configured movie channel.
2. Copy the numeric message ID from the post link.
3. Send `/add <code> <message_id> [title]` to the bot.
4. Users can now send `<code>` to receive that channel post.

Other commands are `/delete <code>`, `/stats`, and `/health`.

## Deployment

The repository includes `Dockerfile`, `docker-compose.yml`, `Procfile`,
`runtime.txt`, `railway.json`, and `render.yaml`.

Railway supports the Dockerfile and restart/health-check settings, but its
current free offer becomes a paid plan after the trial. Render can deploy the
included Blueprint for free, but free web services sleep and free Postgres is
temporary. The bot notifies administrators at startup when configured for
Render. Use a persistent external PostgreSQL service for `DATABASE_URL`.

Never commit `.env` or real tokens. Deployment secrets belong in the hosting
provider's environment-variable settings.
