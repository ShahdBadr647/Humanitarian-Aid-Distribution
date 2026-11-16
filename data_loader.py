"""Load and validate the fictional sample datasets in the data/ folder."""

from pathlib import Path

import pandas as pd

from agents.config import RESOURCES

DATA_DIR = Path(__file__).parent / "data"

AREA_COLUMNS = [
    "area_id", "area_name", "region", "population",
    "food_need", "water_need", "medicine_need",
    "urgency", "vulnerable_pct", "access_difficulty",
]
NUMBER_COLUMNS = [
    "population", "food_need", "water_need", "medicine_need",
    "urgency", "vulnerable_pct", "access_difficulty",
]


def clean_areas(areas: pd.DataFrame) -> pd.DataFrame:
    """Check the area table and fix simple problems (missing or negative numbers)."""
    missing = [c for c in AREA_COLUMNS if c not in areas.columns]
    if missing:
        raise ValueError(f"Area data is missing columns: {missing}")
    areas = areas[AREA_COLUMNS].copy()
    areas = areas.dropna(subset=["area_id", "area_name"])
    areas["area_id"] = areas["area_id"].astype(str)
    if areas["area_id"].duplicated().any():
        raise ValueError("Area IDs must be unique")
    for col in NUMBER_COLUMNS:
        areas[col] = pd.to_numeric(areas[col], errors="coerce").fillna(0).clip(lower=0).astype(int)
    areas["urgency"] = areas["urgency"].clip(1, 5)
    areas["access_difficulty"] = areas["access_difficulty"].clip(1, 5)
    areas["vulnerable_pct"] = areas["vulnerable_pct"].clip(0, 100)
    return areas.reset_index(drop=True)


def load_areas(path: Path = DATA_DIR / "areas.csv") -> pd.DataFrame:
    return clean_areas(pd.read_csv(path))


def load_resources(path: Path = DATA_DIR / "resources.csv") -> pd.DataFrame:
    resources = pd.read_csv(path)
    missing = [r for r in RESOURCES if r not in set(resources["resource"])]
    if missing:
        raise ValueError(f"Resource data is missing: {missing}")
    resources["available"] = pd.to_numeric(resources["available"], errors="coerce").fillna(0).clip(lower=0).astype(int)
    return resources.set_index("resource").loc[RESOURCES].reset_index()
