# Elmer Project Context

## Architecture
- NUC (Ubuntu 22.04, Python 3.10): Elmer Core, Dashboard, Docker services
- Windows Desktop (RTX 3060): Elmer Worker, Ollama, Whisper, Obsidian
- ShackPi (RPi): AllStar node
- WeatherPi (RPi): weewx, meshtastic

## Key Details
- Python venv: ~/elmer/.venv (always activate before running)
- Common package: packages/common/elmer_common/ (installed editable)
- PostgreSQL: native on NUC, localhost:5432, database "elmer", user "postgres"
- MQTT: Mosquitto in Docker, requires auth (user: w0abe, password: meshtastic)
- Ollama: Windows machine at 192.168.1.226:11434
- Worker: Windows machine at 192.168.1.226:8101
- .env must be in each package directory (Pydantic Settings uses relative paths)
- Embedding model: nomic-embed-text (768 dimensions)
- Chat model: llama3.1:8b

## Known Issues
- OLLAMA_HOST env var is set system-wide on Windows to 0.0.0.0:11434
  so worker config uses ELMER_OLLAMA_HOST to avoid collision
- Windows worker uses threaded paho-mqtt (not aiomqtt) due to asyncio issues
- Docker services need host network access to reach native Postgres and MQTT

## Conventions
- Commit after each prompt card: git commit -m "P2-XX: description"
- Test endpoints with curl after each change
- Use make commands where available
