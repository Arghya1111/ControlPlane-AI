from abc import ABC, abstractmethod
import time
from app.models import CheckRequest, RiskSignal


class BaseDetector(ABC):
    """Abstract Base Class for all Responsible AI risk detectors."""

    detector_name: str = "base_detector"

    @abstractmethod
    async def check(self, request: CheckRequest) -> RiskSignal:
        """Evaluate a CheckRequest and return a single RiskSignal with confidence, evidence, and latency."""
        pass

    def calculate_latency_ms(self, start_time: float) -> float:
        """Helper to calculate elapsed execution time in milliseconds."""
        return round((time.perf_counter() - start_time) * 1000, 2)
