"""
StudyRewind Local Embedding Service (Phase 7)

Provides local-first, CPU-based embedding generation using
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2.
Supports English, Hindi, and Hinglish/mixed-language texts.
Outputs 384-dimensional normalized vectors compatible with pgvector vector(384).
Requires zero paid APIs, zero cloud credentials, and zero external services.
"""

import math
import logging
from typing import List, Optional

logger = logging.getLogger("studyrewinds.services.embedding")

# Exact required model name
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Output vector dimensionality matching pgvector vector(384)
EMBEDDING_DIMENSION = 384

# Default batch size chosen for laptop-friendly CPU execution without excessive memory consumption
DEFAULT_BATCH_SIZE = 32

# Module-level singleton cache to avoid repeatedly reloading model weights on CPU
_embedding_model = None
_embedding_service = None


class EmbeddingServiceError(Exception):
    """Base exception for all embedding service failures."""
    pass


class ModelLoadError(EmbeddingServiceError):
    """Raised when the SentenceTransformer model fails to load."""
    pass


class InvalidInputError(EmbeddingServiceError):
    """Raised when input text is None, empty, whitespace-only, or not a string."""
    pass


class EmbeddingDimensionError(EmbeddingServiceError):
    """Raised when the embedding output dimension does not match the expected 384 dimensions."""
    pass


def get_embedding_model(model_name: str = MODEL_NAME, device: str = "cpu"):
    """
    Lazy loader and singleton cache for the SentenceTransformer model.
    Loads onto CPU to ensure compatibility with standard laptops.
    First call loads the weights; subsequent calls reuse the cached instance.
    """
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Initializing local SentenceTransformer model='%s' on device='%s'...", model_name, device)
            _embedding_model = SentenceTransformer(model_name, device=device)
            logger.info("SentenceTransformer model successfully initialized.")
        except Exception as err:
            logger.error("Failed to load SentenceTransformer model '%s': %s", model_name, str(err), exc_info=True)
            raise ModelLoadError(f"Failed to load local embedding model '{model_name}': {str(err)}") from err
    return _embedding_model


def reset_embedding_model():
    """
    Resets the singleton model cache. Used primarily for deterministic unit testing.
    """
    global _embedding_model, _embedding_service
    _embedding_model = None
    _embedding_service = None


def _validate_single_text(text: str, context: str = "Input text") -> str:
    """Validates that a single input is a non-empty, non-whitespace string."""
    if text is None or not isinstance(text, str):
        raise InvalidInputError(f"{context} must be a string, got {type(text).__name__}.")
    stripped = text.strip()
    if not stripped:
        raise InvalidInputError(f"{context} cannot be empty or whitespace-only.")
    return text


def _validate_embedding_vector(vector: List[float], index: Optional[int] = None) -> List[float]:
    """Validates that an embedding vector has exactly 384 dimensions and all values are finite."""
    ctx = f" at index {index}" if index is not None else ""
    if len(vector) != EMBEDDING_DIMENSION:
        raise EmbeddingDimensionError(
            f"Embedding vector{ctx} has dimension {len(vector)}, expected {EMBEDDING_DIMENSION}."
        )
    for i, val in enumerate(vector):
        if not math.isfinite(val):
            raise EmbeddingServiceError(f"Embedding vector{ctx} contains non-finite value at position {i}: {val}")
    return vector


class EmbeddingService:
    """
    Reusable local embedding service.
    Designed for laptop CPU execution with batching, input validation,
    normalized embeddings (for cosine similarity), and strict dimension enforcement.
    """

    def __init__(self, model_name: str = MODEL_NAME, device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.dimension = EMBEDDING_DIMENSION

    def get_model(self):
        """Returns the cached model instance."""
        return get_embedding_model(self.model_name, self.device)

    def embed_text(self, text: str) -> List[float]:
        """
        Generates a 384-dimensional normalized embedding for a single text.

        Args:
            text: Non-empty string to embed (English, Hindi, or Hinglish).

        Returns:
            List[float] of exactly 384 normalized numeric values.

        Raises:
            InvalidInputError: If text is None, empty, or whitespace-only.
            ModelLoadError: If the model fails to load.
            EmbeddingDimensionError: If the output vector is not 384-dimensional.
            EmbeddingServiceError: For inference or finite-value failures.
        """
        _validate_single_text(text)
        model = self.get_model()

        try:
            # normalize_embeddings=True ensures unit vectors for subsequent cosine similarity
            embedding = model.encode(
                text,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as err:
            logger.error("Embedding generation failed: %s", str(err), exc_info=True)
            raise EmbeddingServiceError(f"Failed to generate embedding: {str(err)}") from err

        vector = [float(v) for v in embedding]
        return _validate_embedding_vector(vector)

    def embed_texts(self, texts: List[str], batch_size: int = DEFAULT_BATCH_SIZE) -> List[List[float]]:
        """
        Generates 384-dimensional normalized embeddings for a batch of texts.

        Args:
            texts: List of non-empty strings to embed.
            batch_size: Batch size for model inference (default: 32).

        Returns:
            List[List[float]] containing 384-d normalized vectors for each input text.

        Raises:
            InvalidInputError: If texts is not a list, contains invalid items, or batch_size <= 0.
            ModelLoadError: If the model fails to load.
            EmbeddingDimensionError: If any output vector is not 384-dimensional.
            EmbeddingServiceError: For inference or finite-value failures.
        """
        if texts is None or not isinstance(texts, list):
            raise InvalidInputError("Input texts must be a list of strings.")

        if batch_size <= 0:
            raise InvalidInputError(f"batch_size must be a positive integer, got {batch_size}.")

        if len(texts) == 0:
            return []

        for i, t in enumerate(texts):
            _validate_single_text(t, context=f"Input text at index {i}")

        model = self.get_model()

        try:
            embeddings = model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as err:
            logger.error("Batch embedding generation failed: %s", str(err), exc_info=True)
            raise EmbeddingServiceError(f"Failed to generate batch embeddings: {str(err)}") from err

        if len(embeddings) != len(texts):
            raise EmbeddingServiceError(
                f"Model returned {len(embeddings)} embeddings for {len(texts)} input texts."
            )

        results: List[List[float]] = []
        for idx, emb in enumerate(embeddings):
            vector = [float(v) for v in emb]
            _validate_embedding_vector(vector, index=idx)
            results.append(vector)

        return results


def get_embedding_service() -> EmbeddingService:
    """
    Returns the singleton EmbeddingService instance.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def embed_text(text: str) -> List[float]:
    """Convenience module function to embed a single text."""
    return get_embedding_service().embed_text(text)


def embed_texts(texts: List[str], batch_size: int = DEFAULT_BATCH_SIZE) -> List[List[float]]:
    """Convenience module function to embed a batch of texts."""
    return get_embedding_service().embed_texts(texts, batch_size=batch_size)
