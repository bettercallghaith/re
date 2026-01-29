# Sales Analytics Dashboard - Setup Guide

Deploy to `report.bettercallghaith.com` with Docker Compose.

---

## Quick Deploy

```bash
cd "/path/to/OCR TO CHART "

# Build and start
docker compose build
docker compose up -d

# Pull LLM model (optional, for AI insights)
docker compose exec ollama ollama pull mistral
```

**Done!** Dashboard live at `http://report.bettercallghaith.com`

---

## Use Different Port

If port 80 is already in use:

```bash
# Use port 8080 instead
PORT=8080 docker compose up -d

# Or set in .env
echo "PORT=8080" >> .env
docker compose up -d
```

---

## Cloudflare Setup

1. Add DNS record pointing `report.bettercallghaith.com` → your server IP
2. Set SSL mode to **Flexible** or **Full** in Cloudflare
3. Cloudflare handles SSL - no certbot needed

---

## Configuration

Edit `.env` to configure:

```env
# Backend
OLLAMA_HOST=http://ollama:11434

# Notifications
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## Commands

| Command | Description |
|---------|-------------|
| `docker compose build` | Build containers |
| `docker compose up -d` | Start (detached) |
| `docker compose down` | Stop |
| `docker compose logs -f` | View logs |
| `docker compose restart` | Restart |

---

## Architecture

```
Cloudflare (SSL) → Nginx (:80) → Frontend (:3000)
                              → Backend (:8000) → Ollama
```

---

## Troubleshooting

```bash
# Check logs
docker compose logs backend
docker compose logs frontend

# Check if port is free
lsof -i :80

# Use different port
PORT=8080 docker compose up -d
```
