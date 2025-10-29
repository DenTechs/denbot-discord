# DenBot Discord Bot - Docker Setup

This directory contains the Docker configuration for running the DenBot Discord bot in a containerized environment.

## 📁 Files Overview

- `Dockerfile` - Container build configuration
- `docker-compose.yml` - Service orchestration and configuration
- `.dockerignore` - Files to exclude from Docker build context
- `example.env` - Template for environment variables
- `README.md` - This setup guide

## 🚀 Quick Start

### Prerequisites

- Docker Engine 20.10 or later
- Docker Compose 2.0 or later

### Setup Steps

1. **Navigate to the docker directory:**
   ```bash
   cd docker/
   ```

2. **Configure environment variables:**
   ```bash
   cp example.env .env
   ```
   
   Edit `.env` file with your actual API keys and configuration:
   ```bash
   BOT_API_KEY="your_discord_bot_token"
   ANTHROPIC_API_KEY="your_anthropic_api_key"
   ALLOWED_CHANNELS="[123456789, 987654321]"
   OVERRIDE_USERS="[111111111, 222222222]"
   WOLFRAM_APPID="your_wolfram_alpha_api_key"
   MOONDREAM_API_KEY="your_moondream_api_key"
   ```

3. **Start the bot:**
   ```bash
   docker-compose up -d
   ```
   
   That's it! The setup automatically handles:
   - Building the Docker image
   - Creating the logs directory with proper permissions
   - Starting the bot with all dependencies

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `BOT_API_KEY` | Discord bot token | ✅ | - |
| `ANTHROPIC_API_KEY` | Claude API key | ✅ | - |
| `ALLOWED_CHANNELS` | JSON array of allowed Discord channel IDs | ✅ | `[]` |
| `OVERRIDE_USERS` | JSON array of user IDs that can bypass channel restrictions | ✅ | `[]` |
| `WOLFRAM_APPID` | Wolfram Alpha API key | ❌ | - |
| `MOONDREAM_API_KEY` | Moondream image recognition API key | ❌ | - |

### Resource Limits

The default configuration sets:
- Memory limit: 512MB
- Memory reservation: 256MB

Adjust these in `docker-compose.yml` based on your server capacity.

## 📊 Management Commands

### Start the bot:
```bash
docker-compose up -d
```

### Stop the bot:
```bash
docker-compose down
```

### View logs:
```bash
docker-compose logs -f denbot
```

### Restart the bot:
```bash
docker-compose restart denbot
```

### Update the bot:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Check bot status:
```bash
docker-compose ps
```

## 🏥 Health Monitoring

The container includes health checks that verify the bot's status every 30 seconds. You can check the health status with:

```bash
docker inspect denbot-discord --format='{{.State.Health.Status}}'
```

## 📝 Logs

Logs are stored in the `./logs` directory and are automatically rotated:
- Maximum log file size: 10MB
- Maximum number of log files: 3
- Bot logs are also written to `bot.log` inside the container

## 🔒 Security Features

- Runs as non-root user (`botuser`)
- Environment variables are properly isolated
- No unnecessary ports exposed
- Minimal base image (Python slim)

## 🛠️ Troubleshooting

### Bot won't start:
1. Check environment variables in `.env` file
2. Verify Docker and Docker Compose versions
3. Check logs: `docker-compose logs denbot`

### Permission issues:
```bash
# Fix log directory permissions
sudo chown -R 1000:1000 ./logs
```

### Memory issues:
Increase memory limits in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 1G
    reservations:
      memory: 512M
```

### Update dependencies:
```bash
# Rebuild with latest packages
docker-compose build --no-cache --pull
```

## 🔄 Development Mode

For development, you can mount the source code as a volume:

```yaml
volumes:
  - .:/app
  - ./logs:/app/logs
```

This allows live code changes without rebuilding the container.

## 📞 Support

If you encounter issues:
1. Check the logs first: `docker-compose logs denbot`
2. Verify all required environment variables are set
3. Ensure your API keys are valid
4. Check Docker system resources: `docker system df`

## 🏗️ Architecture

The Docker setup includes:
- **Base Image**: Python 3.11 slim for optimal size and performance
- **Dependencies**: All required packages for Discord, AI, and image processing
- **Security**: Non-root user execution
- **Monitoring**: Health checks and log rotation
- **Persistence**: Log directory mounting for data retention
