FROM python:3.11-slim

WORKDIR /app

# Copy package sources (context is repo root).
COPY packages/common/ /app/packages/common/
COPY packages/telegram-bot/ /app/packages/telegram-bot/

# Install common first (for MQTT), then the bot.
RUN pip install --no-cache-dir /app/packages/common/ /app/packages/telegram-bot/

CMD ["python", "-m", "elmer_telegram.main"]
