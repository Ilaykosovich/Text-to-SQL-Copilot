# app/rag/chroma_store.py

from typing import Dict, List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from DB.init_db import build_chroma_from_pg_url
from API.config import settings

DEFAULT_PERSIST_DIR = "./chroma_db"
DEFAULT_COLLECTION = "pg_schema"
DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class ChromaStore:
    def __init__(
        self,
        persist_dir: str = DEFAULT_PERSIST_DIR,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_model: str = DEFAULT_EMBED_MODEL,
        connection_string: str = settings.DATABASE_URL
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_model = embedding_model


        self._collection = build_chroma_from_pg_url(
        connection_string,
        persist_dir=DEFAULT_PERSIST_DIR,
        collection_name=DEFAULT_COLLECTION,
        reset_collection=True,  # recommended if you rerun often
    )
        self._embedder = SentenceTransformer(self.embedding_model)

    def count(self) -> int:
        return self._collection.count()

    def query(
        self,
        queries: List[str],
        n_results: int = 10,
        where: Optional[Dict] = None,
    ) -> Dict:
        """
        Semantic search by precomputed embeddings.
        """
        embeddings = self._embedder.encode(
            queries,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        return self._collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    @staticmethod
    def _normalize_where(where: dict) -> dict:
        if any(k.startswith("$") for k in where.keys()):
            return where
        return {"$and": [{k: {"$eq": v}} for k, v in where.items()]}

    def get_by_metadata(self, where: dict, limit: int = 2000) -> dict:
        where = self._normalize_where(where)
        return self._collection.get(
            where=where,
            limit=limit,
            include=["documents", "metadatas"],
        )




