from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.config import HOST, ONTOLOGY_FILE, PORT
from backend.api import router as api_router
from backend.extractor import ONTOLOGY, empty_ontology_index
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
        index_path = Path("website/Startpage.html")
        return FileResponse(index_path) if index_path.exists() else {"ok": True, "message": "API is running.", "docs": "/docs"}
    app.include_router(api_router)
    return app

def load_ontology_on_startup():
    try:
        rows = load_json_file(ONTOLOGY_FILE)
        if not isinstance(rows, list):
            raise RuntimeError("Ontology.json must be a JSON array")
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