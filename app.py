"""Application entrypoint that wires FastAPI, static pages, and ontology startup loading."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from backend.api import api_router, health_router
from backend.core.config import HOST, ONTOLOGY_FILE, PORT
from backend.core.ontology_config import validate_ontology_config
from backend.extractor.ontology import ONTOLOGY, empty_ontology_index
from backend.session_store import init_storage
from backend.state import load_json_file

def create_app() -> FastAPI:
    """Build the FastAPI application and mount its routes.

    Returns:
        The configured FastAPI app instance.
    """
    app = FastAPI(title="Ontology Wikibase Extractor API", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/website", StaticFiles(directory="website"), name="website")

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/website/pages/start.html")

    app.include_router(api_router)
    app.include_router(health_router)
    return app

def load_ontology_on_startup() -> None:
    """Load the ontology file while keeping the API bootable on failure.

    Returns:
        None.
    """
    try:
        rows = load_json_file(ONTOLOGY_FILE)
        if not isinstance(rows, list):
            raise RuntimeError(f"{ONTOLOGY_FILE.name} must be a JSON array")
        ONTOLOGY.load(rows)
        config_errors = validate_ontology_config(ONTOLOGY.index)
        if config_errors:
            raise RuntimeError("Ontology configuration does not match ontology.json: " + " ".join(config_errors))
    except Exception as exc:
        # Keep the API bootable even if ontology loading fails; /health exposes the
        # error and proposal generation stays blocked until the ontology is fixed.
        ONTOLOGY.rows = []
        ONTOLOGY.index = empty_ontology_index()
        ONTOLOGY.load_error = str(exc)

load_ontology_on_startup()
init_storage()
app: FastAPI = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
