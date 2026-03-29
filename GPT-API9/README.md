# TriExtract

TriExtract is a human-in-the-loop knowledge graph extraction tool for Wikibase-style data.
It takes legal or structured source text, retrieves relevant context from an existing graph, asks an OpenAI model to propose ontology-valid statement rows, lets a human review and edit those rows, and then exports a delta-oriented JSON result and QuickStatements.

- Inputs: `ontology.json`, optional `query.json`, and free-text source material
- Outputs: reviewed JSON export plus single-step or two-step QuickStatements
- Workflow: `Start` -> `Extract` -> `Finalize`

## Quick Start

`requirements.txt` is included for the backend dependencies.

Before running:

- Use Python 3.10 or newer.
- Make sure the machine has internet access to the OpenAI API.
- The graph view loads Cytoscape from `unpkg.com`, so internet access is also needed for the browser preview.
- Use your own OpenAI API key. Do not put a real key into the repository.

### macOS and Linux

```bash
cd /path/to/GPT-API9
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your-openai-api-key-here"
python3 app.py
```

### Windows PowerShell

```powershell
cd C:\path\to\GPT-API9
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OPENAI_API_KEY="your-openai-api-key-here"
py app.py
```

If PowerShell blocks the activation script, run this once in the same terminal window and then try again:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### Windows Command Prompt

```bat
cd C:\path\to\GPT-API9
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
set OPENAI_API_KEY=your-openai-api-key-here
py app.py
```

Then open: http://127.0.0.1:8000/

To stop the server, press `Ctrl+C` in the terminal.

## Typical Workflow

1. Open the `Start` page.
2. Upload `ontology.json`.
3. Optionally upload `query.json` if you want to continue from an existing graph.
4. Go to `Extract`, paste source text, and generate a proposal.
5. Review the proposed rows and reasoning, edit if needed, and click `Apply`.
6. Repeat extraction and approval until the session graph looks right.
7. Open `Finalize` to export JSON and QuickStatements.
8. If unresolved placeholders remain, run Step 1, paste the created QIDs, and generate Step 2.

## What The App Does

TriExtract is designed for incremental graph building rather than one-shot extraction.
The important design choice is that model output never changes the graph directly. The model creates a proposal, the user reviews it, and only approved rows become part of the working session graph.

Main capabilities:

- loads a Wikibase ontology export and builds lookup indices over it
- optionally loads an existing graph as the session base
- retrieves relevant KB rows using lexical matching, SQLite FTS, and embedding reranking
- builds a constrained prompt payload instead of sending raw text alone
- prefers reusing existing entities instead of creating duplicates
- validates and normalizes model output into a flat statement-row format
- stores session state, revision numbers, warnings, and approval history in memory
- exports JSON plus QuickStatements, with QuickStatements built from the session delta

## How It Works

### 1. Session State

Each session has a starting graph and a working graph:

- `base_kb_json`: the session's starting snapshot
- `current_kb_json`: the mutable working graph after approvals
- `delta_kb_json`: net additions in the session, computed from base vs current

This lets the app extend an existing graph while treating the session's new contribution as the main export object.

### 2. Retrieval And Prompting

Before calling the extractor model, the backend builds a context package from:

- normalized source text
- a compact ontology cache
- preview rows retrieved from the current graph
- an entity catalog for labels already present in the graph
- structured-reference examples to encourage reuse of existing modeling patterns

Retrieval combines:

- lexical label matching
- SQLite full-text search
- embedding reranking

### 3. Proposal Generation

The extractor model returns JSON with:

- `proposed_rows`
- `changes`

The backend then:

- validates the rows against the ontology and statement format
- removes duplicates and bad rows
- resolves safe matches back to existing entity IDs
- merges the rows into a preview graph
- builds a reasoning report for the UI

### 4. Approval

Approving a proposal applies a patch to the session graph.
It does not replace the whole graph.

During approval the backend:

1. checks the proposal belongs to the session
2. rejects stale approvals using `kb_revision`
3. uses the edited patch from the UI if the user changed it
4. removes rows replaced or deleted by the proposal
5. appends the approved rows
6. deduplicates the result
7. increments `kb_revision`

Only approved rows become future retrieval context.

### 5. Export

The `Finalize` page is delta-oriented.
QuickStatements are built from the session delta, while the JSON view prefers delta rows and falls back to `current_kb_json` when there are no delta rows to show.

Export outputs:

- final JSON export
- QuickStatements output

If unresolved placeholders remain, QuickStatements becomes a two-step flow:

- Step 1: create the new items
- Step 2: bind the new QIDs into the remaining statements

## Core Concepts

| Term | Meaning |
| --- | --- |
| `ontology.json` | Ontology export that defines valid items, properties, and labels |
| `query.json` | Optional base graph export used to seed a session |
| `base_kb_json` | Starting graph for the session |
| `current_kb_json` | Current working graph after approvals |
| `delta_kb_json` | Net additions in the current session |
| `removed_kb_json` | Rows removed relative to the base graph |
| `proposal_rows_only` | Validated candidate rows from the extractor |
| `patch_kb_json` | Rows actually applied on approval |
| `proposed_kb_json` | Full merged preview graph shown in the UI |
| `kb_revision` | Session revision counter used to block stale approvals |
| `NEW:entity_n` | Placeholder subject for a new item without a real QID yet |
| Two-step QuickStatements | Export mode used when new items must be created before the final statements can be imported |

## Important Files And Folders

### Backend

- `app.py`
  FastAPI entrypoint, static file mounting, and ontology loading on startup.
- `backend/api.py`
  Main HTTP routes for uploads, proposal generation, approval, state, and QuickStatements.
- `backend/state.py`
  In-memory session store, JSON loading helpers, deduplication, delta calculation, and SQLite FTS indexing.
- `backend/extractor/pipeline.py`
  End-to-end proposal generation orchestration.
- `backend/extractor/context.py`
  Retrieval, label matching, entity reuse, embedding cache, and preview-row selection.
- `backend/extractor/postprocess.py`
  Validation, merge logic, reasoning shaping, and conservative edit/delete matching.
- `backend/extractor/ontology.py`
  Ontology loading, indexing, and statement-row validation helpers.
- `backend/quickstatements.py`
  QuickStatements generation, sanitization, placeholder manifests, and Step 2 binding.
- `backend/core/config.py`
  Environment-backed config and OpenAI client creation.
- `backend/core/prompt.py`
  System prompt that constrains the extractor model.

### Frontend

- `website/pages/start.html`
  Upload ontology and optional base graph.
- `website/pages/extract.html`
  Generate, inspect, edit, and apply proposals.
- `website/pages/finalize.html`
  Export JSON and QuickStatements.
- `website/js/extract.js`
  Main extraction-page workflow.
- `website/js/finalize.js`
  Final export and Step 2 flow.
- `website/js/graph.js`
  Cytoscape graph rendering.

### Data And Docs

- `user_data_editable/ontology.json`
  Default ontology file path.
- `user_data_editable/query.json`
  Default base graph file path.
- `docs/README.md`
  Docs entry point.
- `docs/architecture/thesis_graphs.md`
  Canonical thesis/demo architecture notes.

## API Overview

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Server status, ontology status, and active settings |
| `GET` | `/health` | Same health payload without `/api` |
| `GET` | `/api/state/{session_id}` | Session snapshot including base, current, delta, removed rows, history count, and token usage |
| `GET` | `/api/default-query` | Reads the configured `query.json` file |
| `POST` | `/api/upload-ontology` | Uploads and saves the ontology JSON, then resets in-memory state |
| `POST` | `/api/upload-query` | Uploads and saves the base graph JSON, then resets in-memory state |
| `POST` | `/api/propose` | Generates a proposal from input text |
| `POST` | `/api/approve` | Applies an approved or manually edited patch to the session graph |
| `GET` | `/api/quickstatements/{session_id}` | Builds QuickStatements from the session delta |
| `POST` | `/api/quickstatements/{session_id}/step2` | Binds placeholder QIDs and generates Step 2 QuickStatements |

## Configuration

All runtime configuration lives in `backend/core/config.py`.
Defaults come from `backend/core/tuning.py` unless overridden by environment variables.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | required | API key for embeddings and chat completions |
| `HOST` | `0.0.0.0` | FastAPI bind host |
| `PORT` | `8000` | FastAPI port |
| `ONTOLOGY_FILE` | `user_data_editable/ontology.json` | Path to the ontology file |
| `DEFAULT_QUERY_FILE` | `user_data_editable/query.json` | Path to the default base graph file |
| `ALLOW_DELETE` | `false` | Whether deletion proposals are allowed |
| `TOPK` | `60` | Preview rows sent to the extractor |
| `FTS_CANDIDATES` | `2000` | FTS candidates gathered before reranking |
| `FTS_QUERY_MAX_TOKENS` | `80` | Max unique text tokens used in the FTS query |
| `EMBEDDING_RERANK_CANDIDATES` | `250` | Candidate rows embedded for semantic reranking |
| `ENTITY_CATALOG_LIMIT` | `250` | Label-to-entity mappings exposed to the extractor |
| `ENTITY_NEIGHBORHOOD_SHARE` | `0.35` | Share of `TOPK` reserved for rows around matched entities |
| `ENTITY_NEIGHBORHOOD_PER_ENTITY` | `3` | Max reserved neighborhood rows per matched entity |
| `ROW_EMBEDDING_CACHE_MAX` | `512` | In-memory row embedding cache size |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model used for semantic retrieval |
| `EXTRACTOR_MODEL` | `gpt-5.2` | Model used for structured extraction |
| `EXTRACTOR_TEMPERATURE` | `0.1` | Sampling temperature for the extractor model |

## Operational Notes

- Session state and proposals live only in memory.
- Restarting the server clears all sessions and pending proposals.
- Uploading a new ontology or query file also clears all in-memory sessions and proposals.
- The browser stores `session_id` and last `proposal_id` in `localStorage`, but the server state is still temporary.
- If ontology loading fails at startup, the API still boots, but proposal generation is blocked until the ontology is fixed.
- The UI must be opened through the FastAPI server, not via `file://`.

## Limitations

- There is no database, authentication, or background job system.
- The graph model is intentionally flat and statement-row oriented.
- Deletions are tracked in JSON exports but not emitted in QuickStatements output.
- The Finalize page's JSON view falls back to `current_kb_json` when there are no delta rows, even though QuickStatements still uses the delta path.
- The model is constrained heavily by ontology and retrieval context, but human review is still necessary.
