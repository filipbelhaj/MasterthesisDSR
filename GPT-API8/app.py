from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from backend.api import api_router, health_router
from backend.core.config import HOST, ONTOLOGY_FILE, PORT
from backend.extractor.ontology import ONTOLOGY, empty_ontology_index
from backend.state import load_json_file

def create_app() -> FastAPI:
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
    def root():
        return RedirectResponse(url="/website/pages/start.html")

    app.include_router(api_router)
    app.include_router(health_router)
    return app

def load_ontology_on_startup() -> None:
    try:
        rows = load_json_file(ONTOLOGY_FILE)
        if not isinstance(rows, list):
            raise RuntimeError(f"{ONTOLOGY_FILE.name} must be a JSON array")
        ONTOLOGY.load(rows)
    except Exception as exc:
        ONTOLOGY.rows = []
        ONTOLOGY.index = empty_ontology_index()
        ONTOLOGY.load_error = str(exc)

load_ontology_on_startup()
app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, reload=False)