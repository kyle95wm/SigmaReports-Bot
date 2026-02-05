# Discord Reports Bot

A Discord bot for handling TV and VOD issue reports using slash commands, modals, and staff workflows.

## Features
- `/report-tv` and `/report-vod` slash commands
- Modal-based report submission
- Staff review buttons (Fixed, Can't replicate, More info required, Follow-up)
- Public + DM updates to reporters
- Configurable staff pings
- Dockerized deployment
- SQLite persistence

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/yourname/discord-reports-bot.git
cd discord-reports-bot```

### 2. Create environment file
```bash
cp .env.example .env```

Fill in your values.

### 3. Run with Docker

```bash
docker compose up -d --build```


