# Deployment Guide

ORS Explorer runs as one FastAPI web service. The same server provides the browser UI, API routes, health checks, SQLite session storage, and uploaded JSON files.

## What The Server Needs

- Python 3.11 or Docker
- Internet access for the OpenAI API
- An `OPENAI_API_KEY`
- Writable storage for sessions and uploads
- A browser to use the UI

The app does not require special hardware. A small Linux server is enough if it can run Python or Docker and make outbound HTTPS requests.

## Important Runtime Files

| Setting | Purpose |
| --- | --- |
| `APP_DATA_DIR` | Stores SQLite state and uploaded session files. |
| `ONTOLOGY_FILE` | Server-level ontology loaded at startup. |
| `DEFAULT_QUERY_FILE` | Optional server-level knowledge graph to start from. |

Use persistent storage for these paths on a server. If they point to temporary storage, uploaded ontology/query files and session work may be lost after restart.

## Run Locally From The Terminal

From the repository root, replace `your_openai_api_key_here` and run:

```bash
python3 -m venv .venv && source .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -r requirements.txt && OPENAI_API_KEY="your_openai_api_key_here" python app.py
```

Open:

```text
http://127.0.0.1:8000/
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Docker

Build and run:

```bash
docker build -t ors-explorer .
docker run --rm -p 8000:8000 -e OPENAI_API_KEY="your_openai_api_key_here" ors-explorer
```

For persistent Docker storage:

```bash
mkdir -p ./runtime-data
docker run --rm \
  -p 8000:8000 \
  -e OPENAI_API_KEY="your_openai_api_key_here" \
  -e APP_DATA_DIR=/data \
  -e ONTOLOGY_FILE=/data/ontology.json \
  -e DEFAULT_QUERY_FILE=/data/query.json \
  -v "$(pwd)/runtime-data:/data" \
  ors-explorer
```

If `/data/ontology.json` is missing, the app still starts. Upload an ontology from the Configure page before extracting.

## Manual Linux Server

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Set environment variables:

```bash
export OPENAI_API_KEY="your_openai_api_key_here"
export HOST="0.0.0.0"
export PORT="8000"
export APP_DATA_DIR="/opt/ors-explorer/data"
export ONTOLOGY_FILE="/opt/ors-explorer/data/ontology.json"
export DEFAULT_QUERY_FILE="/opt/ors-explorer/data/query.json"
```

Start the app:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open:

```text
http://SERVER_HOSTNAME_OR_IP:8000/
```

For longer-running use, run the Uvicorn command with a service manager such as systemd, Docker, or the hosting provider's service manager.

## Render

The included `render.yaml` deploys the app as a Docker web service with persistent storage mounted at `/data`.

Steps:

1. Push the repository to GitHub.
2. Create a Render Blueprint from the repository.
3. Set the secret `OPENAI_API_KEY`.
4. Deploy.
5. Open the Render URL.
6. Upload an ontology on the Configure page if `/data/ontology.json` does not exist yet.

## After Deployment

Check:

```text
/health
```

Then test the browser workflow:

1. Open `/`.
2. Confirm that an ontology is loaded, or upload `ontology.json`.
3. Generate a small proposal from the Extract page.
4. Approve it.
5. Confirm that the Export page shows JSON and QuickStatements output.

## Notes And Limitations

- SQLite is intended for one running service instance.
- Sessions expire after `SESSION_TTL_SECONDS`, which defaults to 7 days.
- CORS is currently open in `app.py`.
- The frontend loads Cytoscape from `https://unpkg.com/cytoscape@3.29.2/dist/cytoscape.min.js`.
- Python dependencies are not pinned to exact versions in `requirements.txt`.
