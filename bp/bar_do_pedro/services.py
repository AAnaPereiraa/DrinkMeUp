import random
from pathlib import Path

from django.core.cache import cache

from .models import Drinks, DrinksMade, UserProfile

BASE_DIR = Path(__file__).resolve().parent
RESPONSE_FILE = BASE_DIR / "templates/tough_responses.txt"
SUGGESTION_CACHE_TTL = 60 * 60 * 24


def get_file_content_as_list(path_file) -> list:
    """Returns content of a file as a list of strings, one string per line."""
    try:
        with open(path_file) as file_handle:
            return file_handle.readlines()
    except FileNotFoundError as err:
        print(err)
        return []


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


def get_matching_drinks(user_profile: UserProfile):
    """Return matching drink queryset and selected spirits list."""
    spirits_list = parse_spirits_list(user_profile.spirits)
    spirits_pattern = "|".join(spirits_list)

    match1 = Drinks.objects.filter(boozy=user_profile.boozy, taste=user_profile.taste)
    if spirits_list:
        match2_qs = match1.filter(spirits__regex=rf"\b({spirits_pattern})\b")
    else:
        match2_qs = match1

    return match1, match2_qs, spirits_list


def is_valid_stored_suggestion(stored, match1, spirits_list) -> bool:
    """Validate a cached suggestion against current user preferences."""
    drink_id = stored.get("id") or stored.get("pk")
    if drink_id:
        valid = match1.filter(pk=drink_id).exists()
        if spirits_list and valid:
            spirits_pattern = "|".join(spirits_list)
            valid = match1.filter(
                pk=drink_id,
                spirits__regex=rf"\b({spirits_pattern})\b",
            ).exists()
        return valid

    cocktail_name = stored.get("cocktail")
    if not cocktail_name:
        return False

    valid_qs = match1.filter(cocktail=cocktail_name)
    if spirits_list:
        spirits_pattern = "|".join(spirits_list)
        valid_qs = valid_qs.filter(spirits__regex=rf"\b({spirits_pattern})\b")
    return valid_qs.exists()


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
    match1, match2_qs, spirits_list = get_matching_drinks(user_profile)
    match2 = list(match2_qs.values())

    if not match2:
        return None, "Unfortunately there is no cocktail match!!! Please try again =)"

    stored = get_stored_suggestion(user_id)
    cocktail_suggestion = None

    if stored and is_valid_stored_suggestion(stored, match1, spirits_list):
        cocktail_suggestion = stored

    if not cocktail_suggestion:
        cocktail_suggestion = random.choice(match2)
        set_stored_suggestion(user_id, cocktail_suggestion)

    return cocktail_suggestion, None


def shuffle_cocktail_suggestion(user_profile: UserProfile, user_id: int):
    """Return a new random cocktail suggestion."""
    _, match2_qs, _ = get_matching_drinks(user_profile)
    match2 = list(match2_qs.values())

    if not match2:
        return None, "Unfortunately there is no cocktail match!!! Please try again =)"

    cocktail_suggestion = random.choice(match2)
    set_stored_suggestion(user_id, cocktail_suggestion)
    return cocktail_suggestion, None


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
