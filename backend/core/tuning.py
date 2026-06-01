"""Default retrieval, model, and generation settings for the extraction pipeline."""

TOPK: int = 60  # KB rows included in the extractor prompt after retrieval/reranking.
FTS_CANDIDATES: int = 2000  # Rows pulled from SQLite FTS before embedding similarity rerank.
FTS_QUERY_MAX_TOKENS: int = 80  # Unique source-text tokens used to build the FTS query.
EMBEDDING_RERANK_CANDIDATES: int = 250  # Max FTS candidates embedded for semantic rerank on each request.
ENTITY_CATALOG_LIMIT: int = 250  # Label->entity mappings included to help entity linking.
ENTITY_NEIGHBORHOOD_SHARE: float = 0.35  # Share of TOPK reserved for rows around matched existing entities.
ENTITY_NEIGHBORHOOD_PER_ENTITY: int = 3  # Max reserved neighborhood rows per matched entity.
ROW_EMBEDDING_CACHE_MAX: int = 512  # Max row embeddings kept in memory across requests.

# Model selection
EMBEDDING_MODEL: str = "text-embedding-3-small"  # Used for semantic retrieval.
EXTRACTOR_MODEL: str = "gpt-5.4"  # Main extraction model.

# Generation behavior
EXTRACTOR_TEMPERATURE: float = 0.1  # Lower is more deterministic; higher is more exploratory.
EXTRACTOR_ROW_BUDGET_PREFERRED_MIN: int = 4  # Preferred lower bound for extractor proposal rows.
EXTRACTOR_ROW_BUDGET_PREFERRED_MAX: int = 50  # Preferred upper bound for extractor proposal rows.
