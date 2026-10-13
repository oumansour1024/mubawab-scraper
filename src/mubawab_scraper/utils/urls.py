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

ACTION_ALIASES = {
    "a-vendre-all": "a-vendre",
    "a-louer-all": "a-louer",
    "vacational-all": "vacational",
}


def normalize_city_action(action: str) -> str:
    action = action.strip().lower()
    action = ACTION_ALIASES.get(action, action)
    if action not in CT_ACTIONS:
        valid_actions = [*CT_ACTIONS, *ACTION_ALIASES, "all"]
        raise ValueError(f"Action inconnue: {action}. Valides: {valid_actions}")
    return action


def build_city_url(city_slug: str, action: str = "a-vendre") -> str:
    """
    Pattern /ct/ : page ville complète (tous types de biens).
    Ex: https://www.mubawab.ma/fr/ct/agadir/immobilier-a-vendre-all
    """
    action = normalize_city_action(action)
    slug = CT_ACTIONS.get(action)
    encoded_city_slug = quote(unquote(city_slug), safe="-")
    return f"{settings.base_url}/ct/{encoded_city_slug}/{slug}"
