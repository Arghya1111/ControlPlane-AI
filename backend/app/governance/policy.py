import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field

try:
    import yaml  # type: ignore
    PYYAML_AVAILABLE = True
except ImportError:
    PYYAML_AVAILABLE = False

from app.models import ChannelType, RiskTolerance, FailMode, DecisionTier, UseCaseProfile

CONFIG_DIR = Path(__file__).parent.parent / "config"


class PolicyConfig(BaseModel):
    id: str = Field(..., description="Primary identifier for the use case")
    aliases: List[str] = Field(default_factory=list, description="Alternative lookup IDs")
    name: str = Field(..., description="Human-readable policy name")
    channel_type: ChannelType = Field(..., description="customer_facing, internal, or decision_support")
    latency_budget_ms: int = Field(default=500, ge=10, description="Overall pipeline latency budget in ms")
    risk_tolerance: RiskTolerance = Field(default=RiskTolerance.MEDIUM)
    fail_mode: FailMode = Field(default=FailMode.FAIL_CLOSED)
    requires_human_review_above: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Confidence threshold forcing mandatory human review",
    )
    enabled_detectors: List[str] = Field(
        default_factory=lambda: [
            "pii_entity_detector",
            "retrieval_verification_detector",
            "bias_heuristic_detector",
            "statistical_anomaly_detector",
        ]
    )
    detector_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "pii_entity_detector": 0.30,
            "retrieval_verification_detector": 0.30,
            "bias_heuristic_detector": 0.25,
            "statistical_anomaly_detector": 0.15,
        }
    )
    threshold_bands: Dict[str, List[float]] = Field(
        default_factory=lambda: {
            "allow": [0.0, 0.30],
            "edit": [0.30, 0.55],
            "flag_for_review": [0.55, 0.75],
            "block": [0.75, 1.0],
        }
    )

    def to_use_case_profile(self) -> UseCaseProfile:
        """Convert PolicyConfig to API-compatible UseCaseProfile model."""
        return UseCaseProfile(
            id=self.id,
            name=self.name,
            channel_type=self.channel_type,
            latency_budget_ms=self.latency_budget_ms,
            risk_tolerance=self.risk_tolerance,
            fail_mode=self.fail_mode,
            requires_human_review_above=self.requires_human_review_above,
        )


def _simple_yaml_parse(text: str) -> Dict[str, Any]:
    """Pure-Python basic YAML parser fallback for key-value and list structures."""
    import json
    data: Dict[str, Any] = {}
    current_key = None
    list_items = []
    sub_dict = {}
    in_sub = False

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("- ") and current_key:
            item = line[2:].strip().strip('"').strip("'")
            list_items.append(item)
            data[current_key] = list_items
            continue

        if ":" in line:
            parts = line.split(":", 1)
            k = parts[0].strip()
            v = parts[1].strip()

            if not v:
                current_key = k
                list_items = []
                sub_dict = {}
                continue

            # Strip quotes
            v_clean = v.strip('"').strip("'")
            # Parse numbers/booleans/json arrays
            if v.startswith("[") and v.endswith("]"):
                try:
                    data[k] = json.loads(v)
                except Exception:
                    data[k] = v_clean
            elif v_clean.isdigit():
                data[k] = int(v_clean)
            else:
                try:
                    data[k] = float(v_clean)
                except ValueError:
                    data[k] = v_clean
    return data


class PolicyManager:
    """Governance loader and manager for per-use-case YAML policies."""

    _policies: Dict[str, PolicyConfig] = {}
    _alias_map: Dict[str, str] = {}

    @classmethod
    def load_policies(cls, config_dir: Optional[Path] = None) -> Dict[str, PolicyConfig]:
        """Load all YAML policy definitions from the config directory."""
        target_dir = config_dir or CONFIG_DIR
        policies: Dict[str, PolicyConfig] = {}
        alias_map: Dict[str, str] = {}

        if not target_dir.exists():
            return {}

        yaml_files = list(target_dir.glob("*.yaml")) + list(target_dir.glob("*.yml"))
        for yf in yaml_files:
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    content = f.read()
                if PYYAML_AVAILABLE:
                    raw_data = yaml.safe_load(content)
                else:
                    raw_data = _simple_yaml_parse(content)

                if raw_data and isinstance(raw_data, dict):
                    policy = PolicyConfig.model_validate(raw_data)
                    policies[policy.id] = policy
                    alias_map[policy.id] = policy.id
                    for alias in policy.aliases:
                        alias_map[alias] = policy.id
            except Exception as e:
                # Log or ignore corrupted configs
                continue

        cls._policies = policies
        cls._alias_map = alias_map
        return policies

    @classmethod
    def get_policy(cls, use_case_id: str) -> Optional[PolicyConfig]:
        """Lookup policy by primary ID or alias."""
        if not cls._policies:
            cls.load_policies()

        canonical_id = cls._alias_map.get(use_case_id, use_case_id)
        return cls._policies.get(canonical_id)

    @classmethod
    def list_policies(cls) -> List[PolicyConfig]:
        """List all active policies."""
        if not cls._policies:
            cls.load_policies()
        return list(cls._policies.values())


# Module-level convenience functions
def get_use_case_policy(use_case_id: str) -> Optional[PolicyConfig]:
    return PolicyManager.get_policy(use_case_id)


def load_all_use_case_policies() -> Dict[str, PolicyConfig]:
    return PolicyManager.load_policies()
