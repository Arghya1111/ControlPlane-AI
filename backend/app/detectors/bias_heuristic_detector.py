import re
import time
from typing import List, Tuple
from app.models import CheckRequest, RiskSignal
from app.detectors.base import BaseDetector

# Demographic groups and protected classes
DEMOGRAPHIC_TERMS = r"(?:women|men|females|males|black\s+people|white\s+people|asians|hispanics|immigrants|muslims|jews|christians|hindus|elderly\s+people|seniors|disabled\s+people|indigenous\s+people)"

# Generalizing and absolute qualifier predicates
GENERALIZING_PREDICATES = [
    r"(?:are\s+always|are\s+never|are\s+all|are\s+inherently|are\s+naturally)\s+(?:bad|incompetent|lazy|aggressive|emotional|untrustworthy|inferior|greedy|submissive|violent|unfit)",
    r"(?:cannot|can't|never|shouldn't)\s+(?:handle|lead|manage|be\s+trusted|succeed\s+in|work\s+in|excel\s+at)\s+(?:tech|leadership|finance|management|stem|science|executive|math)",
    r"(?:lack|lacks)\s+the\s+(?:intelligence|capacity|ability|stamina|temperament|work\s+ethic)\s+(?:to|for)",
    r"(?:better\s+suited\s+for|only\s+good\s+at)\s+(?:domestic|low-skilled|support|manual|clerical)",
]

COMPILED_PATTERNS = [
    re.compile(rf"\b{DEMOGRAPHIC_TERMS}\s+{pred}\b", re.IGNORECASE)
    for pred in GENERALIZING_PREDICATES
]

# Additional specific stereotype and derogatory tropes
DIRECT_STEREOTYPE_PATTERNS = [
    re.compile(r"\b(?:women\s+are\s+too\s+emotional|men\s+are\s+naturally\s+aggressive)\b", re.IGNORECASE),
    re.compile(r"\b(?:older\s+workers|seniors)\s+(?:can't\s+learn|are\s+useless\s+with)\s+technology\b", re.IGNORECASE),
    re.compile(r"\b(?:hire|promote)\s+only\s+(?:men|women|younger\s+people|native\s+speakers)\b", re.IGNORECASE),
    re.compile(r"\b(?:people\s+with\s+disabilities|disabled\s+employees)\s+cannot\s+be\s+productive\b", re.IGNORECASE),
    re.compile(rf"\b(?:differs?|differences?|gap|disparity)\s+between\s+{DEMOGRAPHIC_TERMS}\s+and\s+{DEMOGRAPHIC_TERMS}\b", re.IGNORECASE),
]

# Statistical and qualifying factual indicators to reduce false positives
STATISTICAL_QUALIFIER_PATTERN = re.compile(
    r"\b(?:on\s+average|studies\s+show|according\s+to|research\s+indicates|statistically|data\s+shows|historical\s+data|tends\s+to|correlated\s+with|\d+(?:\.\d+)?%|\d+\s+percent)\b",
    re.IGNORECASE,
)


class BiasHeuristicDetector(BaseDetector):
    """Fast, explainable rule and lexicon-based detector for demographic stereotypes

    Scans model output for absolute language, demographic generalizations, and
    loaded stereotype phrases targeting protected characteristics, with statistical
    qualifier guards to prevent false-positives on demographic factual data.
    """

    detector_name: str = "bias_heuristic_detector"

    def _scan_bias(self, text: str) -> List[str]:
        """Scan text against heuristic bias patterns and return matched snippets."""
        matched: List[str] = []

        for pattern in COMPILED_PATTERNS:
            for match in pattern.finditer(text):
                matched.append(match.group(0))

        for pattern in DIRECT_STEREOTYPE_PATTERNS:
            for match in pattern.finditer(text):
                matched.append(match.group(0))

        return matched

    def _has_statistical_qualifiers(self, text: str) -> bool:
        """Check if statement contains statistical or grounding qualifiers."""
        return bool(STATISTICAL_QUALIFIER_PATTERN.search(text))

    async def check(self, request: CheckRequest) -> RiskSignal:
        start_time = time.perf_counter()

        matches = self._scan_bias(request.ai_response)

        if not matches:
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["bias"],
                confidence=0.0,
                evidence="Heuristic scan: No demographic generalizations or protected class stereotypes found.",
                latency_ms=self.calculate_latency_ms(start_time),
            )

        unique_matches = list(dict.fromkeys(matches))
        raw_confidence = min(0.95, 0.65 + 0.15 * len(unique_matches))

        # Check for false-positive statistical/qualifying language
        is_qualified = self._has_statistical_qualifiers(request.ai_response)

        if is_qualified:
            # Significant confidence discount (0.3x) for qualified demographic observations
            adjusted_confidence = round(raw_confidence * 0.30, 2)
            samples = ", ".join(f"'{m}'" for m in unique_matches[:2])
            evidence = (
                f"Demographic mention detected [{samples}], but qualified by statistical/factual language. "
                f"Confidence reduced from {raw_confidence:.2f} to {adjusted_confidence:.2f} (likely factual observation)."
            )
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["bias"],
                confidence=adjusted_confidence,
                evidence=evidence,
                latency_ms=self.calculate_latency_ms(start_time),
            )

        samples = ", ".join(f"'{m}'" for m in unique_matches[:2])
        evidence = (
            f"Heuristic pattern match: Found {len(unique_matches)} unqualified demographic generalization/stereotype "
            f"phrase(s): [{samples}]."
        )

        return RiskSignal(
            detector_name=self.detector_name,
            risk_dimensions=["bias"],
            confidence=round(raw_confidence, 2),
            evidence=evidence,
            latency_ms=self.calculate_latency_ms(start_time),
        )
