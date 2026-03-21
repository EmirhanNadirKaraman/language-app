# YouGlish App

## Running locally

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — install and make sure it's running

### Steps

1. Clone this repo

2. Copy the example env file:
   ```
   cp .env.example .env
   ```

3. Open `.env` and set your `ANTHROPIC_API_KEY`
   (get one at https://console.anthropic.com — free tier works)

4. Start the app:
   ```
   cd youglish-app
   docker compose up
   ```

5. Open http://localhost:8000 in your browser

The first run takes a few minutes to download and build everything. Subsequent runs start in seconds.

### Stopping

- `Ctrl+C` to stop
- `docker compose down` to clean up containers

To wipe all saved data: `docker compose down -v`
