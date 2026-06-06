import random
from pathlib import Path

from django.core.cache import cache

from .models import Drinks, DrinksMade, UserProfile

BASE_DIR = Path(__file__).resolve().parent
RESPONSE_FILE = BASE_DIR / "templates/tough_responses.txt"
BOOZY_LEVELS = ["Light", "Medium", "Strong"]
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


def queryset_for_preferences(taste: str, boozy: str, spirits_list: list[str]):
    """Return drinks matching taste, boozy, and optional spirits."""
    queryset = Drinks.objects.filter(boozy=boozy, taste=taste)
    if spirits_list:
        spirits_pattern = "|".join(spirits_list)
        queryset = queryset.filter(spirits__regex=rf"\b({spirits_pattern})\b")
    return queryset


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
    Find drinks for the user's taste and spirits, trying boozy level up then down.
    Returns (match_list, info_message, is_exact_boozy_match).
    """
    taste = preferences.taste
    boozy = preferences.boozy
    spirits_list = parse_spirits_list(preferences.spirits)

    exact_qs = queryset_for_preferences(taste, boozy, spirits_list)
    if exact_qs.exists():
        return list(exact_qs.values()), None, True

    for direction in (1, -1):
        adjusted_boozy = shift_boozy(boozy, direction)
        if not adjusted_boozy:
            continue
        fallback_qs = queryset_for_preferences(taste, adjusted_boozy, spirits_list)
        if fallback_qs.exists():
            message = (
                "Unfortunately there is no match, but with this taste and spirits "
                f"we can recommend a {adjusted_boozy} option."
            )
            return list(fallback_qs.values()), message, False

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
    if spirits_list:
        spirits_pattern = "|".join(spirits_list)
        match2_qs = match1.filter(spirits__regex=rf"\b({spirits_pattern})\b")
    else:
        match2_qs = match1

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


def get_available_spirits() -> list[str]:
    """Build a sorted list of all spirits present in the Drinks table."""
    all_spirits = set()
    for spirits_value in Drinks.objects.values_list("spirits", flat=True):
        if spirits_value:
            for part in spirits_value.split(","):
                spirit = part.strip()
                if spirit:
                    all_spirits.add(spirit)
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

    user_profile = UserProfile.objects.get(user=user)
    messages = get_file_content_as_list(RESPONSE_FILE)
    if messages:
        user_profile.latest_post = random.choice(messages)
    user_profile.spirits = ""
    user_profile.save()
    clear_stored_suggestion(user.id)
    return drinks_made
