import random
from pathlib import Path

from django.core.cache import cache

from .models import Drinks, DrinksMade, UserProfile

PLACEHOLDER_TASTE = "Taste"
PLACEHOLDER_BOOZY = "Boozy"
PLACEHOLDER_SPIRITS = "Spirits"

BASE_DIR = Path(__file__).resolve().parent
RESPONSE_FILE = BASE_DIR / "templates/tough_responses.txt"
BOOZY_LEVELS = ["Light", "Medium", "Strong"]
BOOZY_LABELS = {
    "Light": "starting slow",
    "Medium": "it's getting hot in here",
    "Strong": "to infinity and beyond",
}
SUGGESTION_CACHE_TTL = 60 * 60 * 24
NO_MATCH_MESSAGE = "Unfortunately there is no cocktail match!!! Please try again =)"


def shift_boozy(boozy: str, direction: int) -> str | None:
    """Move boozy one level up (+1) or down (-1)."""
    try:
        index = BOOZY_LEVELS.index(boozy)
    except ValueError:
        return None
    new_index = index + direction
    if 0 <= new_index < len(BOOZY_LEVELS):
        return BOOZY_LEVELS[new_index]
    return None


RUM_FAMILY = frozenset({
    "rum",
    "white rum",
    "dark rum",
    "spiced rum",
    "spicy rum",
    "gold rum",
    "light rum",
})

SCOTCH_FAMILY = frozenset({
    "scotch",
    "blended scotch",
    "islay scotch",
    "single malt scotch",
})

WHISKEY_FAMILY = frozenset({
    "whiskey",
    "bourbon",
    "rye whiskey",
    "irish whiskey",
})

# Shown as the family label on the form; catalog names still match that checkbox.
SPIRIT_DISPLAY_ALIASES = {
    **{name: "Rum" for name in RUM_FAMILY if name != "rum"},
    **{name: "Scotch" for name in SCOTCH_FAMILY if name != "scotch"},
    **{name: "Whiskey" for name in ("rye whiskey", "irish whiskey")},
}

SPIRIT_FAMILIES = (
    RUM_FAMILY,
    SCOTCH_FAMILY,
    WHISKEY_FAMILY,
    frozenset({"brandy", "cognac"}),
    frozenset({"prosecco", "champagne"}),
    frozenset({"triple sec", "cointreau", "orange liqueur"}),
    frozenset({"kahlua", "coffee liqueur"}),
)

TASTE_ONLY_MESSAGE = (
    "We don't have that spirit with this taste, but here is another drink "
    "in that taste."
)


def expand_spirit_names(spirits_list: list[str]) -> set[str]:
    """Include related bottles (Rum ↔ White Rum, Whiskey ↔ Bourbon, etc.)."""
    names = {spirit.casefold() for spirit in spirits_list if spirit}
    expanded = set(names)
    for family in SPIRIT_FAMILIES:
        if names & family:
            expanded |= family
    return expanded


def drink_has_any_spirit(drink_spirits: str, selected_spirits: list[str]) -> bool:
    """True if the drink's comma-separated spirits overlap the user's selection."""
    selected = expand_spirit_names(selected_spirits)
    if not selected:
        return True
    drink_set = expand_spirit_names(parse_spirits_list(drink_spirits))
    return bool(selected & drink_set)


def queryset_for_preferences(taste: str, boozy: str, spirits_list: list[str]):
    """Return drinks matching taste, boozy, and optional spirits."""
    queryset = Drinks.objects.filter(boozy=boozy, taste=taste)
    if not spirits_list:
        return queryset
    matching_ids = [
        drink.pk
        for drink in queryset
        if drink_has_any_spirit(drink.spirits, spirits_list)
    ]
    return Drinks.objects.filter(pk__in=matching_ids)


def get_or_create_user_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def clear_order_preferences(preferences, request=None) -> None:
    """Reset taste / spirits / boozy so the bar form starts empty."""
    preferences.taste = ""
    preferences.boozy = ""
    preferences.spirits = ""
    if isinstance(preferences, GuestPreferences):
        if request is not None:
            request.session["guest_taste"] = ""
            request.session["guest_boozy"] = ""
            request.session["guest_spirits"] = ""
        return
    preferences.save(update_fields=["taste", "boozy", "spirits"])


def empty_form_selection() -> dict:
    return {
        "selected_taste": "",
        "selected_boozy": "",
        "selected_spirits": [],
    }


def form_selection_from_preferences(preferences) -> dict:
    """Values the order form needs to restore the last taste / spirits / boozy."""
    taste = getattr(preferences, "taste", "") or ""
    boozy = getattr(preferences, "boozy", "") or ""
    spirits = getattr(preferences, "spirits", "") or ""
    if taste == PLACEHOLDER_TASTE:
        taste = ""
    if boozy == PLACEHOLDER_BOOZY:
        boozy = ""
    selected_spirits = parse_spirits_list(spirits)
    if selected_spirits == [PLACEHOLDER_SPIRITS]:
        selected_spirits = []
    selected_spirits = _spirits_for_display(selected_spirits)
    return {
        "selected_taste": taste,
        "selected_boozy": boozy,
        "selected_spirits": selected_spirits,
    }


def get_spirits_columns() -> list[list[str]]:
    """Split available spirits into columns of at most 10 for the profile form."""
    spirits = get_available_spirits()
    return [spirits[i : i + 10] for i in range(0, len(spirits), 10)]


class GuestPreferences:
    """Session-backed preferences for guest users (no account)."""

    def __init__(self, taste: str = "", boozy: str = "", spirits: str = ""):
        self.taste = taste
        self.boozy = boozy
        self.spirits = spirits

    @classmethod
    def from_session(cls, request):
        return cls(
            taste=request.session.get("guest_taste", ""),
            boozy=request.session.get("guest_boozy", ""),
            spirits=request.session.get("guest_spirits", ""),
        )

    def save_from_post(self, request):
        self.taste = request.POST.get("taste", "")
        self.boozy = request.POST.get("strength", "")
        self.spirits = ", ".join(request.POST.getlist("spirit"))
        request.session["guest_taste"] = self.taste
        request.session["guest_boozy"] = self.boozy
        request.session["guest_spirits"] = self.spirits
        request.session["guest_mode"] = True


def find_suggestion_pool(preferences):
    """
    Find drinks for the user's taste and spirits.

    Tries the requested boozy level, then nearby levels, then any boozy
    level. If that spirit is not in the catalog for this taste, offer
    another drink with the same taste.
    Returns (match_list, info_message, is_exact_boozy_match).
    """
    taste = preferences.taste
    boozy = preferences.boozy
    spirits_list = parse_spirits_list(preferences.spirits)

    exact_qs = queryset_for_preferences(taste, boozy, spirits_list)
    if exact_qs.exists():
        return list(exact_qs.values()), None, True

    tried_boozy = {boozy}
    for direction in (1, -1):
        adjusted_boozy = shift_boozy(boozy, direction)
        if not adjusted_boozy or adjusted_boozy in tried_boozy:
            continue
        tried_boozy.add(adjusted_boozy)
        fallback_qs = queryset_for_preferences(taste, adjusted_boozy, spirits_list)
        if fallback_qs.exists():
            boozy_label = BOOZY_LABELS.get(adjusted_boozy, adjusted_boozy)
            message = (
                "Unfortunately there is no match, but with this taste and spirits "
                f"we can recommend a {boozy_label} boozy level option."
            )
            return list(fallback_qs.values()), message, False

    for other_boozy in BOOZY_LEVELS:
        if other_boozy in tried_boozy:
            continue
        leftover_qs = queryset_for_preferences(taste, other_boozy, spirits_list)
        if leftover_qs.exists():
            boozy_label = BOOZY_LABELS.get(other_boozy, other_boozy)
            message = (
                "Unfortunately there is no match, but with this taste and spirits "
                f"we can recommend a {boozy_label} boozy level option."
            )
            return list(leftover_qs.values()), message, False

    taste_qs = Drinks.objects.filter(taste=taste)
    if taste_qs.exists():
        return list(taste_qs.values()), TASTE_ONLY_MESSAGE, False

    return [], NO_MATCH_MESSAGE, False


def is_suggestion_in_pool(stored, match_pool: list) -> bool:
    """Check whether a stored suggestion is still valid for the current match pool."""
    if not stored or not match_pool:
        return False
    pool_ids = {drink.get("id") for drink in match_pool}
    stored_id = stored.get("id") or stored.get("pk")
    return stored_id in pool_ids


def resolve_drink(stored) -> Drinks:
    """Return a Drinks model instance from a dict, session data, or model."""
    if isinstance(stored, Drinks):
        return stored
    drink_id = stored.get("id") or stored.get("pk")
    return Drinks.objects.get(pk=drink_id)


def drink_to_session_data(drink) -> dict:
    """Store only the fields needed to restore a suggestion from session."""
    if isinstance(drink, dict):
        return {"id": drink["id"], "cocktail": drink["cocktail"]}
    return {"id": drink.id, "cocktail": drink.cocktail}


def get_matching_drinks(user_profile: UserProfile):
    """Return matching drink queryset and selected spirits list."""
    spirits_list = parse_spirits_list(user_profile.spirits)
    match1 = Drinks.objects.filter(boozy=user_profile.boozy, taste=user_profile.taste)
    match2_qs = queryset_for_preferences(
        user_profile.taste, user_profile.boozy, spirits_list
    )
    return match1, match2_qs, spirits_list


def get_file_content_as_list(path_file) -> list:
    """Returns content of a file as a list of strings, one string per line."""
    try:
        with open(path_file) as file_handle:
            return file_handle.readlines()
    except FileNotFoundError as err:
        print(err)
        return []


def get_random_motivational_message(default="Welcome! Let's drink!") -> str:
    messages = get_file_content_as_list(RESPONSE_FILE)
    if messages:
        return random.choice(messages).strip()
    return default


def get_guest_motivational_message(request) -> str:
    if not request.session.get("guest_motivational_msg"):
        request.session["guest_motivational_msg"] = get_random_motivational_message()
    return request.session["guest_motivational_msg"]


def _display_spirit_name(spirit: str) -> str:
    return SPIRIT_DISPLAY_ALIASES.get(spirit.casefold(), spirit)


def _spirits_for_display(spirits_list: list[str]) -> list[str]:
    """Map hidden rum-family names to the checkbox label (Rum)."""
    seen: set[str] = set()
    display: list[str] = []
    for spirit in spirits_list:
        label = _display_spirit_name(spirit)
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        display.append(label)
    return display


def get_available_spirits() -> list[str]:
    """Build a sorted list of spirits for the order form.

    Family bottles (White Rum, Dark Rum, Blended Scotch, Islay Scotch,
    Irish Whiskey, Rye Whiskey, …) are not shown as their own
    checkboxes; those drinks match the family label.
    """
    all_spirits = set()
    for spirits_value in Drinks.objects.values_list("spirits", flat=True):
        if spirits_value:
            for part in spirits_value.split(","):
                spirit = part.strip()
                if spirit:
                    all_spirits.add(_display_spirit_name(spirit))
    return sorted(all_spirits)


def parse_spirits_list(spirits: str) -> list[str]:
    return [spirit.strip() for spirit in spirits.split(",") if spirit.strip()]


def get_suggestion_cache_key(user_id: int) -> str:
    return f"cocktail_suggestion:{user_id}"


def get_stored_suggestion(user_id: int):
    return cache.get(get_suggestion_cache_key(user_id))


def set_stored_suggestion(user_id: int, suggestion) -> None:
    cache.set(get_suggestion_cache_key(user_id), suggestion, SUGGESTION_CACHE_TTL)


def clear_stored_suggestion(user_id: int) -> None:
    cache.delete(get_suggestion_cache_key(user_id))


def get_cocktail_suggestion(user_profile: UserProfile, user_id: int):
    """Pick or reuse a cocktail suggestion for the user."""
    match_pool, info_message, _ = find_suggestion_pool(user_profile)

    if not match_pool:
        return None, info_message

    stored = get_stored_suggestion(user_id)
    cocktail_suggestion = None

    if stored and is_suggestion_in_pool(stored, match_pool):
        cocktail_suggestion = stored

    if not cocktail_suggestion:
        cocktail_suggestion = random.choice(match_pool)
        set_stored_suggestion(user_id, cocktail_suggestion)

    return cocktail_suggestion, info_message


def shuffle_cocktail_suggestion(user_profile: UserProfile, user_id: int):
    """Return a new random cocktail suggestion."""
    match_pool, info_message, _ = find_suggestion_pool(user_profile)

    if not match_pool:
        return None, info_message

    cocktail_suggestion = random.choice(match_pool)
    set_stored_suggestion(user_id, cocktail_suggestion)
    return cocktail_suggestion, info_message


def record_drink_made(user, rate: str, comment: str) -> DrinksMade:
    """Save a made drink from the active suggestion and clear cached suggestion."""
    stored = get_stored_suggestion(user.id)
    if not stored:
        raise ValueError("No active cocktail suggestion.")

    cocktail_name = stored.get("cocktail")
    if not cocktail_name:
        raise ValueError("No active cocktail suggestion.")

    drink = Drinks.objects.get(cocktail=cocktail_name)
    drinks_made = DrinksMade.objects.create(
        user=user.username,
        cocktail=cocktail_name,
        rate=rate,
        comment=comment,
        drink=drink,
    )

    user_profile = get_or_create_user_profile(user)
    messages = get_file_content_as_list(RESPONSE_FILE)
    if messages:
        user_profile.latest_post = random.choice(messages)
    user_profile.taste = ""
    user_profile.boozy = ""
    user_profile.spirits = ""
    user_profile.save()
    clear_stored_suggestion(user.id)
    return drinks_made
