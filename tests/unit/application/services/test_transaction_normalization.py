import pytest

from mubawab_scraper.application.services.transaction_normalization import (
    normalize_detail_transaction,
    normalize_scrape_action,
)


def test_normalize_scrape_action_preserves_aliases() -> None:
    assert normalize_scrape_action("vente") == "a-vendre"
    assert normalize_scrape_action("vacances") == "vacational"


def test_normalize_detail_transaction_handles_all_and_invalid_values() -> None:
    assert normalize_detail_transaction("all") is None
    with pytest.raises(ValueError):
        normalize_detail_transaction("unknown")
