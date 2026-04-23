# Deployment Guide

This project is ready to deploy as a single FastAPI web service. The same server handles:

- the UI at `/website/pages/start.html`
- the API at `/api/...`
- a health check at `/health`

## Quick option

If you want the fastest path to a public URL, use Render with the included [render.yaml](./render.yaml).

## Before you deploy

You need:

- a GitHub repo containing this project
- an `OPENAI_API_KEY`

Important app behavior:

- Sessions are stored in server memory, so a restart clears active sessions.
- `ontology.json` and `query.json` are file-based. In hosted environments, keep them on persistent storage.

## Local Docker test

Build the image:

```bash
docker build -t ors-explorer .
```

Run it:

```bash
docker run --rm -p 8000:8000 --env-file .env ors-explorer
```

Then open:

```text
http://127.0.0.1:8000/
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Render deployment

The included `render.yaml` is set up for a Docker-based web service and persistent storage at `/data`.

### What the Render config does

- deploys this repo as a web service
- starts the app with Docker
- exposes `/health` as the health check
- stores `ontology.json` and `query.json` on a persistent disk at `/data`

### Steps

1. Push this repo to GitHub.
2. In Render, create a new Blueprint service from the repo.
3. Render will detect `render.yaml`.
4. Set the secret `OPENAI_API_KEY` when prompted.
5. Deploy.
6. Open the public `onrender.com` URL.

### First deploy note

If `/data/ontology.json` does not exist yet, the app will still boot, but proposal generation will stay blocked until you upload an ontology from the Configure page. This is expected.

### Why `/data`

The app can write uploaded JSON files to the configured paths. Using `/data` avoids mounting a persistent disk over the source tree.

## Manual non-Docker deployment

Any host that can run Python can serve this app. The start command is:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Install dependencies with:

```bash
pip install -r requirements.txt
```

Required environment variable:

```text
OPENAI_API_KEY
```

Recommended environment variables:

```text
HOST=0.0.0.0
PORT=8000
ONTOLOGY_FILE=/absolute/or/persistent/path/ontology.json
DEFAULT_QUERY_FILE=/absolute/or/persistent/path/query.json
```

## Production caveats

- In-memory sessions mean users can lose in-progress work if the service restarts.
- A persistent disk usually means one instance only for this app shape.
- CORS is currently wide open. That is convenient for deployment, but if you later split frontend and backend across domains, you may want to lock it down.

## Useful endpoints

- `/`
- `/health`
- `/website/pages/start.html`
