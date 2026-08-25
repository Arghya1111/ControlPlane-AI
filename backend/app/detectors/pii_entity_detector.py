import re
import time
from typing import List, Set, Tuple, Optional
from app.models import CheckRequest, RiskSignal, RiskDimension
from app.detectors.base import BaseDetector

# Lazy initialization cache for Presidio AnalyzerEngine
_analyzer = None
_presidio_attempted = False


def _get_analyzer():
    """Lazily initialize Presidio AnalyzerEngine with lightweight en_core_web_sm model (~12MB)."""
    global _analyzer, _presidio_attempted
    if not _presidio_attempted:
        _presidio_attempted = True
        try:
            from presidio_analyzer import AnalyzerEngine  # type: ignore
            from presidio_analyzer.nlp_engine import NlpEngineProvider  # type: ignore

            nlp_config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
            nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
            _analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        except Exception:
            _analyzer = None
    return _analyzer


# Comprehensive Regex patterns for fallback and standalone PII scanning
REGEX_PATTERNS = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
    "PHONE_NUMBER": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "US_SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "BANK_ACCOUNT": re.compile(r"\b(?:account|acct|iban)[\s#:]*([A-Z0-9]{8,24})\b", re.IGNORECASE),
    "STREET_ADDRESS": re.compile(
        r"\b\d{1,5}\s+(?:[A-Za-z0-9#.]+\s+){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct)\b",
        re.IGNORECASE,
    ),
    "NAMED_PERSON_PATTERN": re.compile(
        r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
    ),
}


class PIIEntityDetector(BaseDetector):
    """Detector for identifying Personally Identifiable Information (PII) in model responses.

    Supports Presidio Analyzer with built-in regex fallbacks covering emails,
    phone numbers, social security numbers, credit card numbers, bank accounts,
    addresses, and named personal titles.
    """

    detector_name: str = "pii_entity_detector"

    def _extract_pii_with_regex(self, text: str) -> List[Tuple[str, str]]:
        """Fallback scanner using pre-compiled regular expressions."""
        findings: List[Tuple[str, str]] = []
        for entity_type, pattern in REGEX_PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append((entity_type, match.group(0)))
        return findings

    def _extract_pii(self, text: str) -> List[Tuple[str, str]]:
        """Extract PII entity types and matching snippets."""
        analyzer = _get_analyzer()
        if analyzer is not None:
            try:
                results = analyzer.analyze(text=text, language="en")
                if results:
                    findings: List[Tuple[str, str]] = []
                    for res in results:
                        snippet = text[res.start:res.end]
                        findings.append((res.entity_type, snippet))
                    return findings
            except Exception:
                # Fallback to regex on Presidio runtime failure
                pass

        return self._extract_pii_with_regex(text)

    def _is_mentioned_in_inputs(self, entity_value: str, request: CheckRequest) -> bool:
        """Check if the detected PII token was already provided in prompt, context, or history."""
        clean_val = entity_value.strip().lower()
        if not clean_val:
            return True

        corpus = [request.prompt.lower()]
        if request.retrieved_context:
            corpus.extend(c.lower() for c in request.retrieved_context)
        if request.conversation_history:
            corpus.extend(h.lower() for h in request.conversation_history)

        return any(clean_val in text for text in corpus)

    async def check(self, request: CheckRequest) -> RiskSignal:
        start_time = time.perf_counter()

        pii_findings = self._extract_pii(request.ai_response)

        if not pii_findings:
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["privacy"],
                confidence=0.0,
                evidence="No Personally Identifiable Information (PII) detected in AI response.",
                latency_ms=self.calculate_latency_ms(start_time),
            )

        # Separate ungrounded/fabricated PII vs mentioned PII
        unprompted_findings: List[Tuple[str, str]] = []
        prompted_findings: List[Tuple[str, str]] = []

        for entity_type, snippet in pii_findings:
            if self._is_mentioned_in_inputs(snippet, request):
                prompted_findings.append((entity_type, snippet))
            else:
                unprompted_findings.append((entity_type, snippet))

        # =========================================================================
        # DUAL-TAGGING LOGIC:
        # A privacy leak is always tagged as 'privacy'.
        # If the detected PII entity was NOT provided in the input prompt or
        # retrieved context, the AI has generated/fabricated a personal identity,
        # account number, or contact detail out of thin air. In enterprise deployments,
        # a hallucinated identity detail (e.g. inventing an SSN or fabricated email)
        # poses both a severe privacy concern AND an ungrounded hallucination risk.
        # Therefore, we dual-tag with ["privacy", "hallucination"].
        # =========================================================================
        risk_dimensions: List[RiskDimension] = ["privacy"]
        if unprompted_findings:
            risk_dimensions.append("hallucination")

        # Confidence calculation based on number and severity of PII occurrences
        base_confidence = 0.70
        if unprompted_findings:
            # Fabricated/Unprompted PII has higher confidence risk
            confidence = min(1.0, base_confidence + 0.10 * len(unprompted_findings))
            sample_entities = ", ".join(f"{t}: '{s}'" for t, s in unprompted_findings[:3])
            evidence = (
                f"Detected {len(unprompted_findings)} unprompted/fabricated PII entity(ies) "
                f"not found in input context [{sample_entities}]. "
                f"Tagged as both privacy leak and hallucination."
            )
        else:
            confidence = min(0.85, 0.50 + 0.10 * len(prompted_findings))
            sample_entities = ", ".join(f"{t}: '{s}'" for t, s in prompted_findings[:3])
            evidence = (
                f"Detected {len(prompted_findings)} PII entity(ies) echoing user input "
                f"[{sample_entities}]."
            )

        return RiskSignal(
            detector_name=self.detector_name,
            risk_dimensions=risk_dimensions,
            confidence=round(confidence, 2),
            evidence=evidence,
            latency_ms=self.calculate_latency_ms(start_time),
        )
