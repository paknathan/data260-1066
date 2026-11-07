"""HW9 Part 2 - Redis semantic response cache for the transit-incident Q&A agent.

Each cache entry is a Redis hash:
    s1066:semcache:entry:<uuid>  {query, embedding (FLOAT32 bytes), answer, data_version, created_at, ...}
indexed by a RediSearch HNSW vector index (COSINE) so a new question is matched by KNN-1 search.
Redis returns cosine *distance*; similarity = 1 - distance.

Data-version marker: the current version lives in s1066:semcache:data_version. Every entry stores the
version it was answered under, and lookups only search entries tagged with the current version, so
bump_data_version() (call it when incident data changes) invalidates every older answer at once.

Needs Redis 8+ (or redis-stack), which ships the query engine:  docker run -d -p 6379:6379 redis:8
"""

import os
import time
import uuid

import numpy as np
import redis
from redis.commands.search.field import NumericField, TagField, TextField, VectorField
from redis.commands.search.query import Query

try:  # redis-py >= 6
    from redis.commands.search.index_definition import IndexDefinition, IndexType
except ImportError:  # redis-py 4/5
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType

from kafka_service.common import get_logger
from kafka_service.config import PREFIX  # s1066

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
EMBED_MODEL = os.getenv("SEMCACHE_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
DEFAULT_THRESHOLD = float(os.getenv("SEMCACHE_THRESHOLD", "0.85"))

INDEX_NAME = f"{PREFIX}:semcache:idx"
KEY_PREFIX = f"{PREFIX}:semcache:entry:"
VERSION_KEY = f"{PREFIX}:semcache:data_version"

log = get_logger("semcache")


class SentenceEmbedder:
    """SentenceTransformers wrapper; loads the model on first use and returns unit-length float32 vectors."""

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            # Only PyTorch is needed; stop `transformers` from importing TensorFlow, whose Anaconda
            # build needs AVX and aborts the whole process on this Mac.
            os.environ.setdefault("USE_TF", "0")
            os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dim(self) -> int:
        return self._load().get_sentence_embedding_dimension()

    def encode(self, text: str) -> np.ndarray:
        return self._load().encode(text, normalize_embeddings=True).astype(np.float32)


class SemanticCache:
    def __init__(self, redis_client=None, embedder=None, threshold: float = DEFAULT_THRESHOLD):
        self.redis_client = redis_client or redis.Redis.from_url(REDIS_URL)
        self.embedder = embedder or SentenceEmbedder()
        self.threshold = threshold
        self.ensure_index()

    # ---- index / version ----------------------------------------------------------------------
    def ensure_index(self) -> None:
        try:
            self.redis_client.ft(INDEX_NAME).info()
            return
        except redis.ResponseError:
            pass
        schema = (
            TextField("query"),
            TagField("data_version"),
            NumericField("created_at"),
            VectorField("embedding", "HNSW",
                        {"TYPE": "FLOAT32", "DIM": self.embedder.dim, "DISTANCE_METRIC": "COSINE"}),
        )
        self.redis_client.ft(INDEX_NAME).create_index(
            schema, definition=IndexDefinition(prefix=[KEY_PREFIX], index_type=IndexType.HASH))
        log.info("created vector index %s (dim=%d, COSINE, HNSW)", INDEX_NAME, self.embedder.dim)

    def data_version(self) -> str:
        self.redis_client.set(VERSION_KEY, 1, nx=True)
        return f"v{int(self.redis_client.get(VERSION_KEY))}"

    def bump_data_version(self, reason: str = "incident data changed") -> str:
        new = f"v{self.redis_client.incr(VERSION_KEY)}"
        log.info("DATA VERSION -> %s (%s); older cache entries will no longer match", new, reason)
        return new

    def clear(self) -> None:
        """Drop the index and every cache entry (used to start an experiment from an empty cache)."""
        try:
            self.redis_client.ft(INDEX_NAME).dropindex(delete_documents=True)
        except redis.ResponseError:
            pass
        self.redis_client.delete(VERSION_KEY)
        self.ensure_index()

    # ---- embed / search / store ---------------------------------------------------------------
    def embed(self, text: str) -> np.ndarray:
        return self.embedder.encode(text)

    def search(self, vec: np.ndarray, version: str) -> tuple[dict | None, float | None]:
        """Nearest cached query under `version`. Returns (entry, cosine similarity) or (None, None) if empty."""
        q = (Query(f"(@data_version:{{{version}}})=>[KNN 1 @embedding $vec AS distance]")
             .sort_by("distance")
             .return_fields("query", "answer", "data_version", "distance", "created_at")
             .dialect(2))
        res = self.redis_client.ft(INDEX_NAME).search(q, query_params={"vec": vec.tobytes()})
        if not res.docs:
            return None, None
        doc = res.docs[0]
        entry = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in doc.__dict__.items()}
        return entry, 1.0 - float(entry["distance"])

    def store(self, query: str, vec: np.ndarray, answer: str, version: str, **meta) -> str:
        key = f"{KEY_PREFIX}{uuid.uuid4().hex}"
        mapping = {"query": query, "embedding": vec.tobytes(), "answer": answer, "data_version": version,
                   "created_at": time.time(), **{k: str(v) for k, v in meta.items()}}
        self.redis_client.hset(key, mapping=mapping)
        return key
