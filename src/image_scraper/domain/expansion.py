"""Query expansion: derive variant queries to multiply result coverage."""

from __future__ import annotations


def expand_query(query: str) -> list[str]:
    """Return the query plus deterministic variants, deduplicated in order."""
    base = " ".join(query.split())
    if not base:
        return []

    variants = [base]
    lowered = base.lower()
    if not lowered.endswith("s"):
        variants.append(f"{base}s")
    for modifier in ("photo", "wallpaper", "picture"):
        variants.append(f"{base} {modifier}")

    seen: set[str] = set()
    unique: list[str] = []
    for variant in variants:
        key = variant.lower()
        if key not in seen:
            seen.add(key)
            unique.append(variant)
    return unique
