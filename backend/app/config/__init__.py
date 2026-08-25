import json
from pathlib import Path
from typing import Dict, List, Optional
from app.models import UseCaseProfile

CONFIG_PATH = Path(__file__).resolve().parent / "policies.json"


def load_use_case_profiles() -> Dict[str, UseCaseProfile]:
    """Load use case profiles from policies.json."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        item["id"]: UseCaseProfile.model_validate(item)
        for item in data.get("use_cases", [])
    }


def get_use_case_profile(use_case_id: str) -> Optional[UseCaseProfile]:
    """Retrieve a specific UseCaseProfile by id."""
    profiles = load_use_case_profiles()
    return profiles.get(use_case_id)
