from mubawab_scraper.application.services.city_resolution import (
    resolve_cities,
    resolve_city_range,
)


REGISTERED_CITIES = [
    {"name": "Casablanca", "attrNameurl": "casablanca"},
    {"name": "Fès", "attrNameurl": "fes"},
    {"name": "Marrakech", "attrNameurl": "marrakech"},
]


def test_resolve_cities_matches_name_and_slug() -> None:
    assert resolve_cities("Fès", REGISTERED_CITIES) == [("Fès", "fes")]
    assert resolve_cities("marrakech", REGISTERED_CITIES) == [("Marrakech", "marrakech")]


def test_resolve_city_range_supports_open_end() -> None:
    assert resolve_city_range("Fès;", REGISTERED_CITIES) == [
        ("Fès", "fes"),
        ("Marrakech", "marrakech"),
    ]
