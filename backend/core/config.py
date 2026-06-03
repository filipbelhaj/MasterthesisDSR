"""Environment-backed configuration and client setup used across the backend."""

import os
from pathlib import Path
from openai import OpenAI
from . import tuning

def env_int(name: str, default: int) -> int:
    """Read an integer environment variable with a fallback.

    Args:
        name: Environment variable name.
        default: Value to use when the variable is unset.

    Returns:
        The parsed integer value.
    """
    value = os.getenv(name, "").strip()
    return int(value) if value else default

def env_float(name: str, default: float) -> float:
    """Read a float environment variable with a fallback.

    Args:
        name: Environment variable name.
        default: Value to use when the variable is unset.

    Returns:
        The parsed float value.
    """
    value = os.getenv(name, "").strip()
    return float(value) if value else default

TOPK = env_int("TOPK", tuning.TOPK)
FTS_CANDIDATES = env_int("FTS_CANDIDATES", tuning.FTS_CANDIDATES)
FTS_QUERY_MAX_TOKENS = env_int("FTS_QUERY_MAX_TOKENS", tuning.FTS_QUERY_MAX_TOKENS)
EMBEDDING_RERANK_CANDIDATES = env_int("EMBEDDING_RERANK_CANDIDATES", tuning.EMBEDDING_RERANK_CANDIDATES)
ENTITY_CATALOG_LIMIT = env_int("ENTITY_CATALOG_LIMIT", tuning.ENTITY_CATALOG_LIMIT)
ENTITY_NEIGHBORHOOD_SHARE = env_float("ENTITY_NEIGHBORHOOD_SHARE", tuning.ENTITY_NEIGHBORHOOD_SHARE)
ENTITY_NEIGHBORHOOD_PER_ENTITY = env_int("ENTITY_NEIGHBORHOOD_PER_ENTITY", tuning.ENTITY_NEIGHBORHOOD_PER_ENTITY)
ROW_EMBEDDING_CACHE_MAX = env_int("ROW_EMBEDDING_CACHE_MAX", tuning.ROW_EMBEDDING_CACHE_MAX)
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", tuning.EMBEDDING_MODEL)
EXTRACTOR_MODEL: str = os.getenv("EXTRACTOR_MODEL", tuning.EXTRACTOR_MODEL)
EXTRACTOR_TEMPERATURE = env_float("EXTRACTOR_TEMPERATURE", tuning.EXTRACTOR_TEMPERATURE)
EXTRACTOR_ROW_BUDGET_PREFERRED_MIN = env_int(
    "EXTRACTOR_ROW_BUDGET_PREFERRED_MIN",
    tuning.EXTRACTOR_ROW_BUDGET_PREFERRED_MIN,
)
EXTRACTOR_ROW_BUDGET_PREFERRED_MAX = env_int(
    "EXTRACTOR_ROW_BUDGET_PREFERRED_MAX",
    tuning.EXTRACTOR_ROW_BUDGET_PREFERRED_MAX,
)
PORT = env_int("PORT", 8000)
HOST: str = os.getenv("HOST", "0.0.0.0")

DATA_DIR: Path = Path(os.getenv("APP_DATA_DIR", "data"))
SESSION_TTL_SECONDS = env_int("SESSION_TTL_SECONDS", 7 * 24 * 60 * 60)
ONTOLOGY_FILE: Path = Path(os.getenv("ONTOLOGY_FILE", "user_data_editable/ontology.json"))
DEFAULT_QUERY_FILE: Path = Path(os.getenv("DEFAULT_QUERY_FILE", "user_data_editable/query.json"))
ALLOW_DELETE: bool = os.getenv("ALLOW_DELETE", "false").lower() == "true"

def get_client() -> OpenAI:
    """Create an OpenAI client when credentials are configured.

    Returns:
        An initialized OpenAI client.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")
    return OpenAI()
