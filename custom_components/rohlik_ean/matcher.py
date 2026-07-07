"""Scoring of Rohlík search candidates against EAN metadata.

Pure functions, no Home Assistant dependencies — unit-testable standalone.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# "500 g", "0,5 l", "6× 330 ml", "cca 150 g", "1kg"
_AMOUNT_RE = re.compile(
    r"(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|dl|l)\b", re.IGNORECASE
)

_UNIT_FACTORS = {"g": 1.0, "kg": 1000.0, "ml": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0}
_MASS_UNITS = {"g", "kg"}

# Score weights; renormalized over the components actually available.
_W_BRAND = 0.4
_W_SIZE = 0.4
_W_NAME = 0.2

# Without a verified package size we never auto-add (200 g vs 500 g variants
# of the same product are the typical failure mode).
_NO_SIZE_CAP = 0.7


@dataclass(slots=True)
class Amount:
    """Normalized package amount."""

    value: float  # grams or millilitres
    dimension: str  # "mass" | "volume"


def parse_amount(text: str | None) -> Amount | None:
    """Parse a textual amount like '500 g' or '6× 330 ml' into base units."""
    if not text:
        return None
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    count = int(match.group(1)) if match.group(1) else 1
    value = float(match.group(2).replace(",", "."))
    unit = match.group(3).lower()
    dimension = "mass" if unit in _MASS_UNITS else "volume"
    return Amount(value=count * value * _UNIT_FACTORS[unit], dimension=dimension)


def _fold(text: str) -> str:
    """Lowercase and strip diacritics."""
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-z0-9%]+", _fold(text)) if len(tok) > 1}


def _size_score(meta_quantity: str | None, candidate_amount: str | None) -> float | None:
    """Compare package sizes; None when either side is unparseable."""
    meta_amount = parse_amount(meta_quantity)
    cand_amount = parse_amount(candidate_amount)
    if meta_amount is None or cand_amount is None:
        return None
    if meta_amount.dimension != cand_amount.dimension:
        return 0.0
    ratio = min(meta_amount.value, cand_amount.value) / max(
        meta_amount.value, cand_amount.value
    )
    if ratio >= 0.98:
        return 1.0
    if ratio >= 0.85:
        return 0.5
    return 0.0


def score_candidate(
    meta_name: str | None,
    meta_brand: str | None,
    meta_quantity: str | None,
    candidate_name: str | None,
    candidate_brand: str | None,
    candidate_amount: str | None,
) -> float:
    """Score a Rohlík candidate against OpenFoodFacts metadata, 0.0–1.0."""
    parts: list[tuple[float, float]] = []

    if meta_brand:
        # OFF brands are often comma-separated; the first one is primary.
        brand = _fold(meta_brand.split(",")[0].strip())
        haystack = _fold(f"{candidate_brand or ''} {candidate_name or ''}")
        parts.append((_W_BRAND, 1.0 if brand and brand in haystack else 0.0))

    size = _size_score(meta_quantity, candidate_amount)
    if size is not None:
        parts.append((_W_SIZE, size))

    if meta_name and candidate_name:
        meta_tokens = _tokens(meta_name)
        if meta_tokens:
            overlap = len(meta_tokens & _tokens(candidate_name)) / len(meta_tokens)
            parts.append((_W_NAME, overlap))

    if not parts:
        return 0.0

    score = sum(weight * value for weight, value in parts) / sum(
        weight for weight, _ in parts
    )
    if size is None:
        score = min(score, _NO_SIZE_CAP)
    return round(score, 3)


def size_conflict(meta_quantity: str | None, candidate_amount: str | None) -> bool:
    """True when both sides parse and clearly disagree (guards EAN-index hits)."""
    score = _size_score(meta_quantity, candidate_amount)
    return score == 0.0
