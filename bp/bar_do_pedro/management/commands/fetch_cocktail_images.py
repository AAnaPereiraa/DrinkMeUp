import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from bar_do_pedro.models import Drinks

COCKTAILDB_SEARCH = "https://www.thecocktaildb.com/api/json/v1/1/search.php?s="

# Alternate search terms when the exact cocktail name is not in TheCocktailDB.
SEARCH_ALIASES = {
    "Vesper Martini": ["Vesper"],
    "Dark 'n' Stormy": ["Dark and Stormy"],
    "Planter's Punch": ["Planters Punch", "Mississippi Planters Punch"],
    "Corpse Reviver #2": ["Corpse Reviver"],
    "Hemingway Daiquiri": ["Hemingway Special", "Daiquiri"],
    "Tommy's Margarita": ["Margarita"],
    "Negroni Sbagliato": ["Negroni"],
    "Bee's Knees": ["French 75", "Gin Sour"],
    "Paper Plane": ["Last Word"],
    "Vieux Carré": ["Sazerac"],
    "Fuzzy Navel": ["Screwdriver"],
    "Cable Car": ["Sidecar"],
    "Painkiller": ["Piña Colada"],
    "Suffering Bastard": ["Moscow Mule"],
    "Southside": ["Mojito"],
    "Bronx": ["Martini"],
    "Fitzgerald": ["Gin Rickey"],
    "Brown Derby": ["Whiskey Sour"],
    "Gold Rush": ["Whiskey Sour"],
}


def slugify(name: str) -> str:
    slug = name.lower()
    slug = slug.replace("'", "")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "DrinkMeUp/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def pick_drink(drinks: list, target_name: str):
    if not drinks:
        return None
    target = target_name.lower()
    for drink in drinks:
        if drink.get("strDrink", "").lower() == target:
            return drink
    return drinks[0]


def lookup_image_url(cocktail_name: str) -> tuple[str | None, str | None]:
    queries = [cocktail_name, *SEARCH_ALIASES.get(cocktail_name, [])]
    seen = set()
    for query in queries:
        if query in seen:
            continue
        seen.add(query)
        url = COCKTAILDB_SEARCH + urllib.parse.quote(query)
        try:
            data = fetch_json(url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        drink = pick_drink(data.get("drinks") or [], cocktail_name)
        if drink and drink.get("strDrinkThumb"):
            return drink["strDrinkThumb"], drink.get("strDrink")
        time.sleep(0.08)
    return None, None


def download_image(image_url: str) -> bytes:
    request = urllib.request.Request(image_url, headers={"User-Agent": "DrinkMeUp/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


class Command(BaseCommand):
    help = "Download cocktail images from TheCocktailDB and attach them to Drinks records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace images that are already set.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        updated = 0
        skipped = 0
        failed = []

        for drink in Drinks.objects.all().order_by("id"):
            if drink.image and not force:
                skipped += 1
                continue

            image_url, source_name = lookup_image_url(drink.cocktail)
            if not image_url:
                failed.append(drink.cocktail)
                continue

            try:
                image_bytes = download_image(image_url)
            except (urllib.error.URLError, TimeoutError):
                failed.append(drink.cocktail)
                continue

            extension = "jpg"
            if ".png" in image_url.lower():
                extension = "png"
            filename = f"{slugify(drink.cocktail)}.{extension}"

            if drink.image:
                drink.image.delete(save=False)
            drink.image.save(filename, ContentFile(image_bytes), save=True)
            updated += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"{drink.cocktail} <- {source_name} ({filename})"
                )
            )
            time.sleep(0.08)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated: {updated}, skipped: {skipped}, failed: {len(failed)}"
            )
        )
        if failed:
            self.stdout.write(self.style.WARNING("No image found for:"))
            for name in failed:
                self.stdout.write(f"  - {name}")
