import os
from pathlib import Path
from openai import OpenAI

def env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default

TOPK = env_int("TOPK", 60)
FTS_CANDIDATES = env_int("FTS_CANDIDATES", 800)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "gpt-5.2")
PORT = env_int("PORT", 8000)
HOST = os.getenv("HOST", "0.0.0.0")

ONTOLOGY_FILE = Path(os.getenv("ONTOLOGY_FILE", "Ontology.json"))
DEFAULT_QUERY_FILE = Path(os.getenv("DEFAULT_QUERY_FILE", "query.json"))
ALLOW_DELETE = os.getenv("ALLOW_DELETE", "false").lower() == "true"

def get_client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")
    return OpenAI()
