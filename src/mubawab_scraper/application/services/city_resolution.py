"""Resolve user city selections against the registered city catalogue."""

from typing import TypeAlias

RegisteredCity: TypeAlias = dict[str, str | None]
CityTarget: TypeAlias = tuple[str, str]


def resolve_cities(
    city: str,
    registered_cities: list[RegisteredCity],
) -> list[CityTarget]:
    """Resolve one city or all registered cities to display name and slug."""
    if city.strip().lower() == "all":
        city_targets = [
            (
                item.get("name") or item.get("attrNameurl") or "",
                item.get("attrNameurl") or item.get("name") or "",
            )
            for item in registered_cities
        ]
        city_targets = [(name, slug) for name, slug in city_targets if slug]
        if not city_targets:
            raise ValueError(
                "Aucune ville enregistrée. Exécutez d'abord le scraper des villes."
            )
        return city_targets

    matching_city = next(
        (
            item
            for item in registered_cities
            if (item.get("attrNameurl") or "").casefold() == city.casefold()
            or (item.get("name") or "").casefold() == city.casefold()
        ),
        None,
    )
    if matching_city:
        return [
            (
                matching_city.get("name") or city,
                matching_city.get("attrNameurl") or city,
            )
        ]
    return [(city, city)]


def resolve_city_range(
    city_range: str,
    registered_cities: list[RegisteredCity],
) -> list[CityTarget]:
    """Resolve an inclusive ``start;end`` range of registered cities."""
    parts = city_range.split(";")
    if len(parts) != 2 or not parts[0].strip():
        raise ValueError("city_range doit suivre le format 'VilleDépart;VilleFin'")

    city_targets = resolve_cities("all", registered_cities)

    def find_city_index(name: str) -> int:
        for index, (city_name, city_slug) in enumerate(city_targets):
            if name.casefold() in {city_name.casefold(), city_slug.casefold()}:
                return index
        raise ValueError(f"Ville non enregistrée dans la plage: {name}")

    start_index = find_city_index(parts[0].strip())
    end_index = (
        find_city_index(parts[1].strip())
        if parts[1].strip()
        else len(city_targets) - 1
    )
    if end_index < start_index:
        raise ValueError("La ville de fin doit suivre la ville de départ")
    return city_targets[start_index : end_index + 1]
