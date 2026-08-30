from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from bar_do_pedro.models import Drinks, DrinksMade, UserProfile
from bar_do_pedro.services import (
    TASTE_ONLY_MESSAGE,
    drink_has_any_spirit,
    find_suggestion_pool,
    form_selection_from_preferences,
    get_available_spirits,
)


class DrinkFactoryMixin:
    def make_drink(self, **kwargs):
        defaults = {
            "cocktail": "Test Drink",
            "spirits": "Gin",
            "taste": "Fresh",
            "boozy": "Light",
            "ingredients": "Gin, lime",
            "instructions": "Shake.",
        }
        defaults.update(kwargs)
        return Drinks.objects.create(**defaults)

    def make_user(self, username="ana", email="ana@example.com", password="C0cktail-Test-9x"):
        user = User.objects.create_user(username=username, email=email, password=password)
        profile = UserProfile.objects.create(user=user)
        return user, profile


class LegalPagesTests(TestCase):
    def test_imprint_renders(self):
        response = self.client.get(reverse("imprint"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imprint")
        self.assertContains(response, "Pedro Pereira")
        self.assertNotContains(response, "fitness_jerk")
        self.assertNotContains(response, "Hier könnte ihre Werbung stehen")

    def test_privacy_renders(self):
        response = self.client.get(reverse("privacy_policy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Privacy Policy")
        self.assertContains(response, "We do not sell your data")
        self.assertNotContains(response, "fitness_jerk")

    def test_legacy_legal_urls_still_work(self):
        self.assertEqual(self.client.get("/imprint.html").status_code, 200)
        self.assertEqual(self.client.get("/privacy-policy.html").status_code, 200)


class MenuLabelsTests(TestCase):
    def test_menu_uses_boozy_nicknames(self):
        response = self.client.get(reverse("menu"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Starting slow")
        self.assertContains(response, "It's getting hot in here")
        self.assertContains(response, "to infinity and beyond")
        self.assertNotContains(response, ">Light<")
        self.assertNotContains(response, ">Medium<")
        self.assertNotContains(response, ">Strong<")


class ProfileFormRestoreTests(DrinkFactoryMixin, TestCase):
    def setUp(self):
        self.make_drink(cocktail="Mojito", spirits="White Rum", taste="Fresh", boozy="Light")
        self.user, self.profile = self.make_user()
        self.profile.taste = "Fresh"
        self.profile.boozy = "Light"
        self.profile.spirits = "White Rum, Gin"
        self.profile.save()

    def test_profile_form_is_empty_when_back_at_bar(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_taste"], "")
        self.assertEqual(response.context["selected_boozy"], "")
        self.assertEqual(response.context["selected_spirits"], [])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.taste, "")
        self.assertEqual(self.profile.spirits, "")

    def test_guest_form_is_empty_when_back_at_bar(self):
        session = self.client.session
        session["guest_taste"] = "Citrus"
        session["guest_boozy"] = "Medium"
        session["guest_spirits"] = "Gin"
        session["guest_mode"] = True
        session.save()

        response = self.client.get(reverse("guest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_taste"], "")
        self.assertEqual(response.context["selected_boozy"], "")
        self.assertEqual(response.context["selected_spirits"], [])

    def test_no_match_clears_the_order_form(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile"),
            {
                "taste": "Smoky",
                "strength": "Strong",
                "spirit": ["Gin"],
                "action": "order",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no cocktail match")
        self.assertEqual(response.context["selected_taste"], "")
        self.assertEqual(response.context["selected_spirits"], [])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.taste, "")
        self.assertEqual(self.profile.boozy, "")
        self.assertEqual(self.profile.spirits, "")


class MissingRowTests(DrinkFactoryMixin, TestCase):
    def test_unknown_cocktail_returns_404(self):
        response = self.client.get(reverse("details", kwargs={"id": 99999}))
        self.assertEqual(response.status_code, 404)

    def test_profile_creates_missing_userprofile(self):
        user = User.objects.create_user(username="orphan", password="C0cktail-Test-9x")
        self.assertFalse(UserProfile.objects.filter(user=user).exists())
        self.client.force_login(user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=user).exists())


class AdminRegistrationTests(TestCase):
    def test_models_are_registered(self):
        self.assertTrue(admin.site.is_registered(UserProfile))
        self.assertTrue(admin.site.is_registered(Drinks))
        self.assertTrue(admin.site.is_registered(DrinksMade))


class AuthHardeningTests(DrinkFactoryMixin, TestCase):
    def test_logout_rejects_get(self):
        user, _ = self.make_user()
        self.client.force_login(user)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_logout_post_signs_out(self):
        user, _ = self.make_user()
        self.client.force_login(user)
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_signup_creates_profile(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newguest",
                "email": "newguest@example.com",
                "password1": "C0cktail-Test-9x",
                "password2": "C0cktail-Test-9x",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newguest")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_access_token_lifetime_is_30_minutes(self):
        from django.conf import settings

        self.assertEqual(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], timedelta(minutes=30))


class SuggestionServiceTests(DrinkFactoryMixin, TestCase):
    def test_exact_match_and_fallback(self):
        exact = self.make_drink(cocktail="Mojito", spirits="White Rum", taste="Fresh", boozy="Light")
        stronger = self.make_drink(
            cocktail="Daiquiri", spirits="White Rum", taste="Fresh", boozy="Medium"
        )
        profile = UserProfile(taste="Fresh", boozy="Light", spirits="White Rum")

        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertTrue(is_exact)
        self.assertIsNone(message)
        self.assertEqual({drink["id"] for drink in pool}, {exact.id})

        profile.boozy = "Strong"
        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertFalse(is_exact)
        self.assertIsNotNone(message)
        self.assertEqual({drink["id"] for drink in pool}, {stronger.id})

    def test_spirit_tokens_are_not_treated_as_regex(self):
        gin = self.make_drink(cocktail="Gin Fizz", spirits="Gin", taste="Sour", boozy="Light")
        vodka = self.make_drink(cocktail="Vodka Sour", spirits="Vodka", taste="Sour", boozy="Light")
        self.assertFalse(drink_has_any_spirit("Gin", [".*"]))
        self.assertFalse(drink_has_any_spirit("Vodka", [".*"]))

        profile = UserProfile(taste="Sour", boozy="Light", spirits=".*")
        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertFalse(is_exact)
        self.assertEqual(message, TASTE_ONLY_MESSAGE)
        self.assertEqual({drink["id"] for drink in pool}, {gin.id, vodka.id})

    def test_rum_matches_the_full_rum_family(self):
        mojito = self.make_drink(
            cocktail="Mojito", spirits="White Rum", taste="Fresh", boozy="Light"
        )
        cable_car = self.make_drink(
            cocktail="Cable Car", spirits="Spiced Rum", taste="Fresh", boozy="Light"
        )
        dark_n_stormy = self.make_drink(
            cocktail="Dark n Stormy", spirits="Dark Rum", taste="Fresh", boozy="Light"
        )
        profile = UserProfile(taste="Fresh", boozy="Light", spirits="Rum")
        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertTrue(is_exact)
        self.assertIsNone(message)
        self.assertEqual(
            {drink["id"] for drink in pool},
            {mojito.id, cable_car.id, dark_n_stormy.id},
        )

    def test_form_shows_only_rum_for_the_rum_family(self):
        self.make_drink(cocktail="Mojito", spirits="White Rum", taste="Fresh", boozy="Light")
        self.make_drink(cocktail="Cable Car", spirits="Spiced Rum", taste="Fresh", boozy="Medium")
        self.make_drink(cocktail="Dark n Stormy", spirits="Dark Rum", taste="Fresh", boozy="Medium")
        spirits = get_available_spirits()
        self.assertIn("Rum", spirits)
        self.assertNotIn("White Rum", spirits)
        self.assertNotIn("Spiced Rum", spirits)
        self.assertNotIn("Spicy Rum", spirits)
        self.assertNotIn("Dark Rum", spirits)

    def test_scotch_matches_blended_and_islay(self):
        rusty_nail = self.make_drink(
            cocktail="Rusty Nail", spirits="Scotch", taste="Smoky", boozy="Strong"
        )
        penicillin = self.make_drink(
            cocktail="Penicillin",
            spirits="Blended Scotch, Islay Scotch",
            taste="Smoky",
            boozy="Strong",
        )
        profile = UserProfile(taste="Smoky", boozy="Strong", spirits="Scotch")
        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertTrue(is_exact)
        self.assertIsNone(message)
        self.assertEqual({drink["id"] for drink in pool}, {rusty_nail.id, penicillin.id})

    def test_form_shows_only_scotch_for_the_scotch_family(self):
        self.make_drink(cocktail="Rusty Nail", spirits="Scotch", taste="Smoky", boozy="Strong")
        self.make_drink(
            cocktail="Penicillin",
            spirits="Blended Scotch, Islay Scotch",
            taste="Smoky",
            boozy="Strong",
        )
        spirits = get_available_spirits()
        self.assertIn("Scotch", spirits)
        self.assertNotIn("Blended Scotch", spirits)
        self.assertNotIn("Islay Scotch", spirits)

    def test_whiskey_matches_irish_and_rye(self):
        old_fashioned = self.make_drink(
            cocktail="Old Fashioned", spirits="Whiskey", taste="Bitter", boozy="Strong"
        )
        manhattan = self.make_drink(
            cocktail="Manhattan", spirits="Rye Whiskey", taste="Bitter", boozy="Strong"
        )
        tipperary = self.make_drink(
            cocktail="Tipperary", spirits="Irish Whiskey", taste="Bitter", boozy="Strong"
        )
        profile = UserProfile(taste="Bitter", boozy="Strong", spirits="Whiskey")
        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertTrue(is_exact)
        self.assertIsNone(message)
        self.assertEqual(
            {drink["id"] for drink in pool},
            {old_fashioned.id, manhattan.id, tipperary.id},
        )

    def test_form_shows_only_whiskey_for_irish_and_rye(self):
        self.make_drink(cocktail="Old Fashioned", spirits="Whiskey", taste="Bitter", boozy="Strong")
        self.make_drink(cocktail="Manhattan", spirits="Rye Whiskey", taste="Bitter", boozy="Strong")
        self.make_drink(cocktail="Tipperary", spirits="Irish Whiskey", taste="Bitter", boozy="Strong")
        self.make_drink(cocktail="Mint Julep", spirits="Bourbon", taste="Sweet", boozy="Strong")
        spirits = get_available_spirits()
        self.assertIn("Whiskey", spirits)
        self.assertIn("Bourbon", spirits)
        self.assertNotIn("Irish Whiskey", spirits)
        self.assertNotIn("Rye Whiskey", spirits)

    def test_taste_fallback_when_spirit_is_missing(self):
        penicillin = self.make_drink(
            cocktail="Penicillin", spirits="Scotch", taste="Smoky", boozy="Strong"
        )
        profile = UserProfile(taste="Smoky", boozy="Strong", spirits="Gin")
        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertFalse(is_exact)
        self.assertEqual(message, TASTE_ONLY_MESSAGE)
        self.assertEqual({drink["id"] for drink in pool}, {penicillin.id})

    def test_form_selection_ignores_placeholders(self):
        profile = UserProfile(taste="Taste", boozy="Boozy", spirits="Spirits")
        selection = form_selection_from_preferences(profile)
        self.assertEqual(selection["selected_taste"], "")
        self.assertEqual(selection["selected_boozy"], "")
        self.assertEqual(selection["selected_spirits"], [])


class CatalogCoverageTests(TestCase):
    fixtures = ["drinks.json"]

    def test_each_taste_has_a_core_spirit_drink(self):
        from bar_do_pedro.services import BOOZY_LEVELS, queryset_for_preferences

        tastes = [
            "Sweet",
            "Citrus",
            "Bitter",
            "Fruity",
            "Fresh",
            "Sour",
            "Smoky",
            "Savory",
        ]
        core_spirits = [
            "Gin",
            "Vodka",
            "Tequila",
            "Rum",
            "Whiskey",
            "Wine",
            "Brandy",
            "Prosecco",
        ]
        missing = []
        for taste in tastes:
            for spirit in core_spirits:
                has_match = any(
                    queryset_for_preferences(taste, boozy, [spirit]).exists()
                    for boozy in BOOZY_LEVELS
                )
                if not has_match:
                    missing.append(f"{taste} + {spirit}")
        self.assertEqual(missing, [])


class ApiTests(DrinkFactoryMixin, TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_register_and_jwt_profile(self):
        response = self.api.post(
            "/api/auth/register/",
            {
                "username": "apiuser",
                "email": "apiuser@example.com",
                "password": "C0cktail-Test-9x",
                "password_confirm": "C0cktail-Test-9x",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        token = response.data["tokens"]["access"]
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        profile = self.api.get("/api/profile/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["user"]["username"], "apiuser")

    def test_profile_get_creates_missing_row(self):
        user = User.objects.create_user(
            username="apitoken", email="apitoken@example.com", password="C0cktail-Test-9x"
        )
        self.api.force_authenticate(user=user)
        response = self.api.get("/api/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_menu_detail_missing_drink_is_404(self):
        user, _ = self.make_user(username="menuuser", email="menu@example.com")
        self.api.force_authenticate(user=user)
        response = self.api.get("/api/menu/99999/")
        self.assertEqual(response.status_code, 404)
