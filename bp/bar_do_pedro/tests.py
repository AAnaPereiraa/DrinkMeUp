from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from bar_do_pedro.models import Drinks, DrinksMade, UserProfile
from bar_do_pedro.services import (
    find_suggestion_pool,
    form_selection_from_preferences,
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


class ProfileFormRestoreTests(DrinkFactoryMixin, TestCase):
    def setUp(self):
        self.make_drink(cocktail="Mojito", spirits="White Rum", taste="Fresh", boozy="Light")
        self.user, self.profile = self.make_user()
        self.profile.taste = "Fresh"
        self.profile.boozy = "Light"
        self.profile.spirits = "White Rum, Gin"
        self.profile.save()

    def test_profile_form_restores_last_order(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Fresh" selected')
        self.assertContains(response, 'value="Light" selected')
        self.assertContains(response, 'value="White Rum"')
        self.assertContains(response, "checked")
        self.assertEqual(response.context["selected_spirits"], ["White Rum", "Gin"])

    def test_guest_form_restores_session_order(self):
        session = self.client.session
        session["guest_taste"] = "Citrus"
        session["guest_boozy"] = "Medium"
        session["guest_spirits"] = "Gin"
        session["guest_mode"] = True
        session.save()

        response = self.client.get(reverse("guest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_taste"], "Citrus")
        self.assertEqual(response.context["selected_boozy"], "Medium")
        self.assertEqual(response.context["selected_spirits"], ["Gin"])


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

    def test_regex_metacharacters_in_spirits_do_not_match_everything(self):
        gin = self.make_drink(cocktail="Gin Fizz", spirits="Gin", taste="Sour", boozy="Light")
        self.make_drink(cocktail="Vodka Sour", spirits="Vodka", taste="Sour", boozy="Light")
        profile = UserProfile(taste="Sour", boozy="Light", spirits=".*")

        pool, message, is_exact = find_suggestion_pool(profile)
        self.assertEqual(pool, [])
        self.assertFalse(is_exact)
        self.assertIsNotNone(message)
        self.assertNotIn(gin.id, {drink.get("id") for drink in pool})

    def test_form_selection_ignores_placeholders(self):
        profile = UserProfile(taste="Taste", boozy="Boozy", spirits="Spirits")
        selection = form_selection_from_preferences(profile)
        self.assertEqual(selection["selected_taste"], "")
        self.assertEqual(selection["selected_boozy"], "")
        self.assertEqual(selection["selected_spirits"], [])


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
