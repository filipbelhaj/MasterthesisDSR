# ORS Explorer

ORS Explorer is a human-in-the-loop web application for building a Wikibase-style knowledge graph from source text. It was developed as part of a thesis project around Organisational Rule Systems.

The application helps a user:

1. Load an ontology that defines the available Wikibase items and properties.
2. Optionally load an existing knowledge graph export.
3. Paste source text and ask an OpenAI model to propose ontology-compliant statement rows.
4. Review and edit the proposed JSON before accepting it.
5. Export the approved session changes as JSON or QuickStatements.

The model never writes directly to the knowledge graph. Each extraction is a proposal that must be reviewed and approved in the browser.

## Repository Structure

| Path | Purpose |
| --- | --- |
| `app.py` | FastAPI entrypoint. Mounts the static UI, API routes, health routes, and startup storage. |
| `backend/api.py` | Upload, session, proposal, approval, health, and export endpoints. |
| `backend/session_store.py` | SQLite-backed storage for sessions, proposals, and uploaded session files. |
| `backend/state.py` | Knowledge graph row loading, deduplication, session helpers, and delta computation. |
| `backend/extractor/` | Prompt context retrieval, ontology loading, model call pipeline, validation, and post-processing. |
| `backend/core/` | Environment config, model defaults, ontology profile, prompt, and ontology-specific policy. |
| `backend/quickstatements.py` | Conversion from approved rows to QuickStatements output. |
| `website/pages/` | Browser pages for Configure, Extract, and Export. |
| `website/js/` | Frontend workflow, API calls, session state, graph rendering, and UI helpers. |
| `website/css/` | Application styling. |
| `user_data_editable/ontology.json` | Default ontology loaded at startup unless `ONTOLOGY_FILE` points elsewhere. |
| `data/` | Runtime SQLite database and uploaded files. This is generated local state and is ignored by Git. |
| `Dockerfile` | Container image definition for deployment. |
| `render.yaml` | Render Blueprint configuration with a persistent disk. |
| `.env.example` | Example environment configuration. |

## How The Application Works

The service is a single FastAPI application. It serves the UI and API from the same process:

- `/` redirects to `/website/pages/start.html`
- `/website/...` serves the browser UI
- `/api/...` serves JSON API routes
- `/health` and `/api/health` report configuration and ontology status

The normal workflow is:

1. Configure the session on the start page.
2. Upload `ontology.json` if the server does not already have one.
3. Optionally upload `query.json` to start from an existing knowledge graph.
4. Go to Extract, paste source text, and generate a proposal.
5. Review the proposed rows and reasoning report.
6. Approve the proposal to append it to the session knowledge graph.
7. Repeat extraction as needed.
8. Go to Export and copy or save the JSON/QuickStatements output.

## Required Inputs

### Ontology JSON

`ontology.json` must be a JSON array. The included Configure page contains a SPARQL query template for exporting ontology items and properties from a Wikibase instance.

The backend validates the uploaded ontology against the ontology profile in `backend/core/ontology_profile.py`. If the profile and ontology do not match, proposal generation is blocked until the mismatch is fixed.

### Knowledge Graph JSON

`query.json` is optional. It must also be a JSON array. If present, the session starts from those existing rows and exports only the net changes approved during the session.

If no knowledge graph is uploaded and no `DEFAULT_QUERY_FILE` exists, ORS Explorer starts from an empty graph.

## Install Locally

Use one terminal command from the repository root. Replace `your_openai_api_key_here` with a valid OpenAI API key.

The `.venv/` folder is local only and is not uploaded to Git. This command recreates it on the machine where the project is being run.

```bash
python3 -m venv .venv && source .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -r requirements.txt && OPENAI_API_KEY="your_openai_api_key_here" python app.py
```

This creates `.venv/`, installs dependencies, sets the API key for the current server process, and starts ORS Explorer on port `8000`.

## Run Locally From The Terminal

After the command is running, open the UI:

```text
http://127.0.0.1:8000/
```

Check the backend status:

```text
http://127.0.0.1:8000/health
```

Do not open the HTML files directly with `file://`. Uploads, extraction, session loading, and export require the FastAPI server.

## Configuration

The main environment variables are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Required for proposal generation and embeddings. |
| `HOST` | `0.0.0.0` | Host address used by `python app.py`. |
| `PORT` | `8000` | Port used by `python app.py` and most manual deployments. |
| `APP_DATA_DIR` | `data` | Directory for SQLite state and uploaded session files. |
| `SESSION_TTL_SECONDS` | `604800` | Session lifetime. Default is 7 days. |
| `ONTOLOGY_FILE` | `user_data_editable/ontology.json` | Server-level ontology loaded at startup. |
| `DEFAULT_QUERY_FILE` | `user_data_editable/query.json` | Optional server-level base graph. |
| `ALLOW_DELETE` | `false` | Enables delete behavior where supported by the backend. |
| `EXTRACTOR_MODEL` | value in `backend/core/tuning.py` | OpenAI model used for proposal generation. |
| `EMBEDDING_MODEL` | value in `backend/core/tuning.py` | OpenAI model used for semantic retrieval. |

Additional retrieval and row-budget settings are documented in `backend/core/tuning.py`.


## Deployment Overview

The app can be deployed in three practical ways:

- Local terminal run with Python and Uvicorn.
- Docker container using the included `Dockerfile`.
- Render Blueprint using the included `render.yaml`.

For server deployment, configure persistent storage for:

- `APP_DATA_DIR`
- `ONTOLOGY_FILE`
- `DEFAULT_QUERY_FILE`, if a server-level base graph is required

See [DEPLOYMENT.md](./DEPLOYMENT.md) for local Docker, Render, and manual Linux server instructions.

## Known Assumptions And Limitations

- The server needs outbound internet access to call the OpenAI API.
- The browser currently loads Cytoscape from `https://unpkg.com`. If the deployment must work fully offline or behind a strict firewall, vendor that JavaScript file locally and update the HTML script tags.
- Dependencies in `requirements.txt` are not pinned to exact versions. For strict reproducibility, freeze known-good versions after testing on the target server.
- SQLite storage is intended for a single service instance. Do not run multiple replicas against the same SQLite files.
- Sessions expire after `SESSION_TTL_SECONDS`. Increase this value or export work promptly for long reviews.
- Deletions appear in the JSON export as `deleted_rows`; QuickStatements output is focused on additions and modifications.
- New entities use placeholders such as `NEW:entity_1`. The Export page may require a two-step QuickStatements process: create new items first, enter the assigned Q-IDs, then generate the mapped statements.
- The ontology profile is tailored to the current Organisational Rule Systems ontology. A different ontology may require changes in `backend/core/ontology_profile.py`.

## Related Documentation

- [DEPLOYMENT.md](./DEPLOYMENT.md): server, Docker, Render, and local deployment instructions.
- [MAINTAIN.md](./MAINTAIN.md): architecture, request flow, state model, and maintenance checklist.
