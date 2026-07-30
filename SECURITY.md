# Security Policy

## Secrets

Never commit Discord tokens, `.env`, `config/bot.yaml`, SQLite databases or local logs.

If a token is exposed:

1. Reset it in Discord Developer Portal.
2. Update the running deployment through the web panel or environment variables.
3. Restart the bot process.

## Admin Panel

The management panel can edit sources and bot settings. If you expose the API publicly, protect `/yonetim/*` endpoints with a reverse proxy, private network, SSO or another authentication layer.

## Reporting

Open a private security advisory on GitHub if available. If not, open an issue without including active secrets or exploit details.
