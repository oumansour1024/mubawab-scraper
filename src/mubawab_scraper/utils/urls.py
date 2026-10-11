from urllib.parse import quote, unquote

from mubawab_scraper.config import settings


def build_search_url(city: str, transaction: str) -> str:
    return f"{settings.base_url}/t/{city}"

# Actions valides pour le pattern /ct/
CT_ACTIONS = {
    "a-vendre":   "immobilier-a-vendre-all",
    "a-louer":    "immobilier-a-louer-all",
    "vacational": "immobilier-vacational-all",
}


def build_city_url(city_slug: str, action: str = "a-vendre") -> str:
    """
    Pattern /ct/ : page ville complète (tous types de biens).
    Ex: https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all
    """
    action = {
        "a-vendre-all": "a-vendre",
        "a-louer-all": "a-louer",
        "vacational-all": "vacational",
    }.get(action, action)
    slug = CT_ACTIONS.get(action)
    if not slug:
        raise ValueError(f"Action inconnue: {action}. Valides: {list(CT_ACTIONS)}")
    encoded_city_slug = quote(unquote(city_slug), safe="-")
    return f"{settings.base_url}/ct/{encoded_city_slug}/{slug}"

