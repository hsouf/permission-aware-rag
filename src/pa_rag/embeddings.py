"""Embedders.

Where embedding happens: in-process, twice. At ingest each chunk's text becomes a
vector stored next to its ACL payload; at query time the question becomes a vector.
The ACL filter never depends on either vector.

``HashingEmbedder`` is deterministic and offline so the test suite needs no network
or model download. ``FastEmbedEmbedder`` runs a real local ONNX model. Both keep
document text on the machine: sending restricted text to a third-party embedding
API makes that provider a processor of your most sensitive data.
"""

from __future__ import annotations

import hashlib
import math
import re
from itertools import pairwise
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "so",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "us",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        "all",
        "any",
    ]
)


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


def _normalize(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


class HashingEmbedder:
    """Feature-hashed bag of unigrams and bigrams. Good enough to rank a small corpus."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        tokens = [_normalize(t) for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]
        return tokens + [f"{a}_{b}" for a, b in pairwise(tokens)]

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for feature in self._features(text):
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            vec[0] = 1.0  # avoid a zero vector; cosine distance is undefined on it
            return vec
        return [v / norm for v in vec]


class FastEmbedEmbedder:  # pragma: no cover - optional, needs a model download
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name)
        self.dim = len(self.embed("probe"))

    def embed(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._model.embed([text])))]
