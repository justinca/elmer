# Elmer — System Inventory

> This document tracks all devices, services, and network configuration
> in the Elmer home lab. Update as devices are added or reconfigured.

## Devices

| Device       | Hostname     | IP Address         | OS              | CPU / RAM        | Storage     | Role         |
| ------------ | ------------ | ------------------ | --------------- | ---------------- | ----------- | ------------ |
| NUC          | `elmer-nuc`  | `192.168.x.NUC`   | Ubuntu 22.04    | i5 / 16 GB       | 500 GB SSD  | Hub          |
| Windows PC   | `elmer-win`  | `192.168.x.WIN`   | Windows 11      | i7 / 32 GB + GPU | 1 TB NVMe   | GPU Worker   |
| ShackPi      | `shackpi`    | `192.168.x.SHACK` | Raspberry Pi OS | RPi 4 / 4 GB     | 32 GB SD    | Radio        |
| WeatherPi    | `weatherpi`  | `192.168.x.WX`    | Raspberry Pi OS | RPi 4 / 2 GB     | 32 GB SD    | Weather      |

## Services

| Service           | Device     | Port  | Container    | Status   |
| ----------------- | ---------- | ----- | ------------ | -------- |
| Elmer Core API    | NUC        | 8100  | `elmer-core` | Planned  |
| Streamlit Dashboard| NUC       | 8501  | `elmer-dash` | Planned  |
| Telegram Bot      | NUC        | —     | `elmer-tg`   | Planned  |
| Agents            | NUC        | —     | `elmer-agents`| Planned |
| Knowledge (RAG)   | NUC        | —     | `elmer-knowledge`| Planned|
| PostgreSQL        | NUC        | 5432  | `postgres`   | Running  |
| Mosquitto (MQTT)  | NUC        | 1883  | `mosquitto`  | Running  |
| Ollama            | Windows PC | 11434 | Native       | Running  |
| Worker API        | Windows PC | 8101  | Native       | Planned  |

## Network

- Subnet: `192.168.x.0/24`
- Gateway: `192.168.x.1`
- DNS: Local / Pi-hole (if configured)

## MQTT Topics

| Topic Pattern        | Publisher   | Description                    |
| -------------------- | ----------- | ------------------------------ |
| `elmer/status/#`     | All devices | Service heartbeats             |
| `elmer/radio/#`      | ShackPi     | Band conditions, QSO events    |
| `elmer/weather/#`    | WeatherPi   | Sensor readings                |
| `elmer/home/#`       | Various     | Home automation events         |
| `elmer/llm/#`        | Core/Worker | LLM request/response events    |
