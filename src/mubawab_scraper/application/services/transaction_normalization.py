"""Normalize transaction aliases while preserving existing API semantics."""

from mubawab_scraper.utils.urls import ACTION_ALIASES, normalize_city_action

RAW_ACTION_ALIASES = {
    **ACTION_ALIASES,
    "vente": "a-vendre",
    "location": "a-louer",
    "vacances": "vacational",
}

DETAIL_ACTION_ALIASES = RAW_ACTION_ALIASES
DETAIL_ACTIONS = {"a-vendre", "a-louer", "vacational"}


def normalize_scrape_action(action: str) -> str:
    """Normalize a raw-scraper transaction alias to a supported action."""
    normalized = action.strip().lower()
    normalized = RAW_ACTION_ALIASES.get(normalized, normalized)
    return normalize_city_action(normalized)


def normalize_detail_transaction(transaction_type: str | None) -> str | None:
    """Normalize a detail transaction, returning ``None`` for ``all``."""
    if not transaction_type or transaction_type.strip().lower() == "all":
        return None
    normalized = transaction_type.strip().lower()
    normalized = DETAIL_ACTION_ALIASES.get(normalized, normalized)
    if normalized not in DETAIL_ACTIONS:
        raise ValueError(
            "transaction_type must be a-vendre, a-louer, vacational, or all"
        )
    return normalized
