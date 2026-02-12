import os
from pathlib import Path
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parents[1]
KB_PATH = BASE_DIR / "query.json"
INDEX_HTML_PATH = BASE_DIR / "index.html"

def env_int(name, default):
    return int(os.getenv(name, str(default)))

TOPK = env_int("TOPK", 20)

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "gpt-5.2")

PORT = env_int("PORT", 8000)
HOST = os.getenv("HOST", "0.0.0.0")

def get_client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")
    return OpenAI()


