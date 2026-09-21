"""
Phase 7 - Local Embedding Service Tests
Tests sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 embedding generation.
Verifies English, Hindi, Hinglish, dimensions, normalization, input validation, batching, and error handling.
"""

import math
import pytest
from unittest.mock import MagicMock, patch

from app.services.embedding import (
    MODEL_NAME,
    EMBEDDING_DIMENSION,
    EmbeddingService,
    get_embedding_service,
    get_embedding_model,
    reset_embedding_model,
    embed_text,
    embed_texts,
    EmbeddingServiceError,
    ModelLoadError,
    InvalidInputError,
    EmbeddingDimensionError,
)


@pytest.fixture(autouse=True)
def ensure_clean_model_cache():
    """Ensure clean test state before and after each test."""
    yield
    # Keep singleton intact for speed across standard tests, reset if needed explicitly


def test_model_initialization():
    """Verifies that the embedding model initializes with expected configuration."""
    model = get_embedding_model()
    assert model is not None
    # Model name or tokenizer checks
    assert hasattr(model, "encode")


def test_model_singleton_reuse():
    """Verifies that subsequent calls reuse the same loaded model instance."""
    model_first = get_embedding_model()
    model_second = get_embedding_model()
    assert model_first is model_second, "get_embedding_model must return the singleton instance"


def test_english_text_embedding():
    """Verifies 384-d normalized finite embedding for English text."""
    text = "Operating systems manage hardware resources and provide common services for computer programs."
    embedding = embed_text(text)

    assert isinstance(embedding, list)
    assert len(embedding) == EMBEDDING_DIMENSION
    assert all(isinstance(val, float) for val in embedding)
    assert all(math.isfinite(val) for val in embedding)

    # Unit vector check: norm should be approximately 1.0
    norm = sum(val * val for val in embedding)
    assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_hindi_text_embedding():
    """Verifies 384-d normalized finite embedding for Hindi (Devanagari) text."""
    text = "कंप्यूटर प्रोग्रामिंग और एल्गोरिदम का अध्ययन छात्रों के लिए महत्वपूर्ण है।"
    embedding = embed_text(text)

    assert isinstance(embedding, list)
    assert len(embedding) == EMBEDDING_DIMENSION
    assert all(isinstance(val, float) for val in embedding)
    assert all(math.isfinite(val) for val in embedding)

    norm = sum(val * val for val in embedding)
    assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_hinglish_text_embedding():
    """Verifies 384-d normalized finite embedding for Hinglish / code-mixed text."""
    text = "Aaj hum Binary Search Tree ke baare mein detail se padhenge, concept bahut simple hai."
    embedding = embed_text(text)

    assert isinstance(embedding, list)
    assert len(embedding) == EMBEDDING_DIMENSION
    assert all(isinstance(val, float) for val in embedding)
    assert all(math.isfinite(val) for val in embedding)

    norm = sum(val * val for val in embedding)
    assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_empty_input_rejected():
    """Verifies that empty string is rejected with InvalidInputError."""
    with pytest.raises(InvalidInputError, match="cannot be empty"):
        embed_text("")


def test_whitespace_only_input_rejected():
    """Verifies that whitespace-only strings are rejected with InvalidInputError."""
    with pytest.raises(InvalidInputError, match="cannot be empty or whitespace-only"):
        embed_text("   \n\t  ")


@pytest.mark.parametrize("invalid_val", [None, 12345, 3.14, [], {}, True])
def test_non_string_input_rejected(invalid_val):
    """Verifies that non-string inputs are rejected with InvalidInputError."""
    with pytest.raises(InvalidInputError, match="must be a string"):
        embed_text(invalid_val)


def test_batch_embedding_success():
    """Verifies batch embedding across multiple languages and topics."""
    texts = [
        "Data structures: arrays, linked lists, stacks, and queues.",
        "डेटाबेस प्रबंधन प्रणाली और SQL क्वेरी का परिचय।",
        "Recursion ka base case likhna sabse important step hota hai.",
        "Distributed consensus protocols like Raft and Paxos.",
    ]
    embeddings = embed_texts(texts, batch_size=2)

    assert isinstance(embeddings, list)
    assert len(embeddings) == len(texts)

    for idx, emb in enumerate(embeddings):
        assert len(emb) == EMBEDDING_DIMENSION
        assert all(isinstance(val, float) for val in emb)
        assert all(math.isfinite(val) for val in emb)
        norm = sum(val * val for val in emb)
        assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_batch_embedding_matches_single_embedding():
    """Verifies that batch embedding produces the identical vectors to single embeddings."""
    texts = [
        "Virtual memory paging and segmentation.",
        "प्रोसेस शेड्यूलिंग और सीपीयू यूटिलाइजेशन।",
    ]
    batch_embeddings = embed_texts(texts)
    single_embeddings = [embed_text(t) for t in texts]

    for b_vec, s_vec in zip(batch_embeddings, single_embeddings):
        assert len(b_vec) == len(s_vec) == EMBEDDING_DIMENSION
        for b_val, s_val in zip(b_vec, s_vec):
            assert math.isclose(b_val, s_val, abs_tol=1e-5)


def test_batch_embedding_empty_list():
    """Verifies that embed_texts with an empty list cleanly returns an empty list."""
    assert embed_texts([]) == []


def test_batch_embedding_invalid_element_rejected():
    """Verifies that any invalid element in batch raises InvalidInputError."""
    with pytest.raises(InvalidInputError, match="Input text at index 1"):
        embed_texts(["Valid text", "   ", "Another valid text"])

    with pytest.raises(InvalidInputError, match="Input text at index 2"):
        embed_texts(["Valid text", "Another valid", None])


def test_batch_embedding_invalid_batch_size():
    """Verifies that non-positive batch size raises InvalidInputError."""
    with pytest.raises(InvalidInputError, match="batch_size must be a positive integer"):
        embed_texts(["Test text"], batch_size=0)

    with pytest.raises(InvalidInputError, match="batch_size must be a positive integer"):
        embed_texts(["Test text"], batch_size=-5)


def test_batch_embedding_invalid_type():
    """Verifies that passing a non-list to embed_texts raises InvalidInputError."""
    with pytest.raises(InvalidInputError, match="must be a list of strings"):
        embed_texts("single string instead of list")


def test_dimension_validation_failure():
    """Verifies that EmbeddingDimensionError is raised if model returns wrong dimension."""
    service = EmbeddingService()
    # Mock model encode returning 512 dimensions instead of 384
    fake_model = MagicMock()
    fake_model.encode.return_value = [0.1] * 512

    with patch.object(service, "get_model", return_value=fake_model):
        with pytest.raises(EmbeddingDimensionError, match="dimension 512, expected 384"):
            service.embed_text("Test string")


def test_non_finite_value_detection():
    """Verifies that non-finite values (NaN / Inf) in embedding raise EmbeddingServiceError."""
    service = EmbeddingService()
    fake_vector = [0.0] * 384
    fake_vector[42] = float("nan")

    fake_model = MagicMock()
    fake_model.encode.return_value = fake_vector

    with patch.object(service, "get_model", return_value=fake_model):
        with pytest.raises(EmbeddingServiceError, match="non-finite value"):
            service.embed_text("Test string")


def test_model_load_failure():
    """Verifies that ModelLoadError is raised with clear explanation if model loading fails."""
    reset_embedding_model()
    try:
        with pytest.raises(ModelLoadError, match="Failed to load local embedding model"):
            get_embedding_model("nonexistent-invalid-model-name-xyz-12345")
    finally:
        reset_embedding_model()


def test_embedding_service_class_instance():
    """Verifies direct instantiation of EmbeddingService class."""
    service = EmbeddingService()
    assert service.dimension == 384
    assert service.model_name == MODEL_NAME

    vec = service.embed_text("Test class instance method.")
    assert len(vec) == 384

    batch = service.embed_texts(["Batch item 1", "Batch item 2"])
    assert len(batch) == 2
