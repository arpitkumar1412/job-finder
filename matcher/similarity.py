"""
Compute cosine-similarity between a resume and a list of job descriptions
using sentence-transformers embeddings.

The resume is embedded **once** and reused across all comparisons.
Job descriptions are embedded in batches for efficiency.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

import config

logger = logging.getLogger(__name__)

# Module-level cache so the model is loaded only once per process.
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazy-load and cache the sentence-transformer model."""
    global _model
    if _model is None:
        logger.info("Loading embedding model '%s' …", config.EMBEDDING_MODEL)
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Model loaded.")
    return _model


def embed_texts(texts: list[str]) -> NDArray[np.float32]:
    """
    Encode a list of texts into dense vectors.

    Parameters
    ----------
    texts : list[str]
        Raw texts (resume or job descriptions).

    Returns
    -------
    np.ndarray
        Array of shape ``(len(texts), embedding_dim)``.
    """
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=config.EMBEDDING_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return np.asarray(embeddings, dtype=np.float32)


def compute_similarities(
    resume_embedding: NDArray[np.float32],
    job_embeddings: NDArray[np.float32],
) -> NDArray[np.float64]:
    """
    Compute cosine similarities between the resume and each job.

    Parameters
    ----------
    resume_embedding : np.ndarray
        Shape ``(1, dim)`` — the single resume vector.
    job_embeddings : np.ndarray
        Shape ``(n_jobs, dim)`` — job description vectors.

    Returns
    -------
    np.ndarray
        1-D array of similarity scores scaled to **0 – 100**.
    """
    # cosine_similarity returns shape (1, n_jobs)
    raw_scores: NDArray = cosine_similarity(resume_embedding, job_embeddings)[0]
    # Scale from [-1, 1] → [0, 100] (values are almost always ≥ 0 for text)
    scores = np.clip(raw_scores * 100, 0, 100)
    return scores


def rank_jobs(
    resume_text: str,
    jobs: list[dict[str, Any]],
    threshold: float = config.SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    End-to-end ranking: embed resume + jobs, score, filter, sort.

    Parameters
    ----------
    resume_text : str
        Plain text of the candidate's resume.
    jobs : list[dict]
        Each dict must contain a ``"description"`` key.
    threshold : float
        Minimum similarity score (0-100) to keep a job.

    Returns
    -------
    list[dict]
        Filtered & sorted (highest first) jobs, each enriched with a
        ``"similarity_score"`` key (rounded to 2 decimals).
    """
    if not jobs:
        logger.warning("No jobs to rank.")
        return []

    logger.info("Embedding resume …")
    resume_emb = embed_texts([resume_text])  # shape (1, dim)

    descriptions = [j["description"] for j in jobs]
    logger.info("Embedding %d job descriptions (batch_size=%d) …", len(descriptions), config.EMBEDDING_BATCH_SIZE)
    job_embs = embed_texts(descriptions)  # shape (n, dim)

    logger.info("Computing cosine similarities …")
    scores = compute_similarities(resume_emb, job_embs)

    # Attach scores and filter
    matched: list[dict[str, Any]] = []
    for job, score in zip(jobs, scores):
        rounded = round(float(score), 2)
        if rounded >= threshold:
            job_copy = dict(job)
            job_copy["similarity_score"] = rounded
            matched.append(job_copy)

    # Sort descending by score
    matched.sort(key=lambda j: j["similarity_score"], reverse=True)

    logger.info(
        "Matching complete: %d / %d jobs meet the %.0f%% threshold.",
        len(matched),
        len(jobs),
        threshold,
    )
    return matched
