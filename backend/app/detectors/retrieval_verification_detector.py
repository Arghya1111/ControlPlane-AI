import re
import math
import time
from collections import Counter
from typing import List, Optional
from app.models import CheckRequest, RiskSignal
from app.detectors.base import BaseDetector

# 0.55 is a starting heuristic, not a validated value, and should be tuned against real examples before the pitch.
DEFAULT_SIMILARITY_THRESHOLD: float = 0.55

# Optional sentence-transformers support
try:
    from sentence_transformers import SentenceTransformer, util  # type: ignore
    ST_AVAILABLE = True
    _st_model = None
except ImportError:
    ST_AVAILABLE = False
    _st_model = None


def _get_st_model():
    global _st_model
    if _st_model is None and ST_AVAILABLE:
        try:
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            _st_model = None
    return _st_model


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words."""
    return re.findall(r"\b[a-zA-Z0-9_]+\b", text.lower())


def _cosine_similarity_tf(text1: str, text2: str) -> float:
    """Fallback cosine similarity using term frequency vectors."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)
    if not tokens1 or not tokens2:
        return 0.0

    tf1 = Counter(tokens1)
    tf2 = Counter(tokens2)
    all_keys = set(tf1.keys()).union(set(tf2.keys()))

    dot = sum(tf1.get(k, 0) * tf2.get(k, 0) for k in all_keys)
    norm1 = math.sqrt(sum(v ** 2 for v in tf1.values()))
    norm2 = math.sqrt(sum(v ** 2 for v in tf2.values()))

    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _split_into_sentences(text: str) -> List[str]:
    """Split response text into individual claim sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 5]


class RetrievalVerificationDetector(BaseDetector):
    """Detector verifying whether claims in ai_response are grounded in retrieved_context.

    Uses sentence-level embedding similarity (all-MiniLM-L6-v2) or TF-IDF cosine similarity.
    Flags claims with similarity below similarity_threshold as unsupported hallucinations.
    """

    detector_name: str = "retrieval_verification_detector"

    def __init__(self, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        self.similarity_threshold = similarity_threshold

    def _compute_max_similarity(self, sentence: str, context_chunks: List[str]) -> float:
        """Compute the maximum similarity score between a sentence and any context chunk."""
        model = _get_st_model()
        if model is not None:
            try:
                sent_emb = model.encode(sentence, convert_to_tensor=True)
                ctx_embs = model.encode(context_chunks, convert_to_tensor=True)
                scores = util.cos_sim(sent_emb, ctx_embs)[0]
                return float(scores.max().item())
            except Exception:
                pass

        # Fallback to lexical/TF cosine similarity
        similarities = [_cosine_similarity_tf(sentence, chunk) for chunk in context_chunks]
        return max(similarities) if similarities else 0.0

    async def check(self, request: CheckRequest) -> RiskSignal:
        start_time = time.perf_counter()

        # Handle missing or empty retrieved_context
        if not request.retrieved_context or len(request.retrieved_context) == 0:
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["hallucination"],
                confidence=0.0,
                evidence="no ground truth available to verify against",
                latency_ms=self.calculate_latency_ms(start_time),
            )

        sentences = _split_into_sentences(request.ai_response)
        if not sentences:
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["hallucination"],
                confidence=0.0,
                evidence="AI response is empty or contains no verifiable sentences.",
                latency_ms=self.calculate_latency_ms(start_time),
            )

        unsupported_claims: List[str] = []
        similarity_scores: List[float] = []

        for sent in sentences:
            max_sim = self._compute_max_similarity(sent, request.retrieved_context)
            similarity_scores.append(max_sim)
            if max_sim < self.similarity_threshold:
                unsupported_claims.append(sent)

        # Fraction of unsupported claims
        unsupported_ratio = len(unsupported_claims) / len(sentences)

        if unsupported_claims:
            confidence = min(0.95, 0.40 + (0.55 * unsupported_ratio))
            sample_unsupported = ' "..." '.join(unsupported_claims[:2])
            evidence = (
                f"{len(unsupported_claims)}/{len(sentences)} sentence(s) unsupported by context "
                f"(threshold: {self.similarity_threshold:.2f}). Flagged claims: \"{sample_unsupported[:140]}...\""
            )
        else:
            confidence = 0.05
            evidence = (
                f"All {len(sentences)} claim sentence(s) are strongly grounded in retrieved context "
                f"(mean similarity: {sum(similarity_scores)/len(similarity_scores):.2f})."
            )

        return RiskSignal(
            detector_name=self.detector_name,
            risk_dimensions=["hallucination"],
            confidence=round(confidence, 2),
            evidence=evidence,
            latency_ms=self.calculate_latency_ms(start_time),
        )
