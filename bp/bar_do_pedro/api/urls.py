from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AvailableSpiritsView,
    CocktailMadeView,
    CocktailShuffleView,
    CocktailSuggestionView,
    DrinkHistoryView,
    MenuDetailView,
    MenuListView,
    PreferencesView,
    ProfileView,
    RegisterView,
)


urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="api_register"),
    path("auth/login/", TokenObtainPairView.as_view(), name="api_login"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="api_token_refresh"),
    path("profile/", ProfileView.as_view(), name="api_profile"),
    path("profile/spirits/", AvailableSpiritsView.as_view(), name="api_available_spirits"),
    path("profile/preferences/", PreferencesView.as_view(), name="api_preferences"),
    path("profile/history/", DrinkHistoryView.as_view(), name="api_drink_history"),
    path("cocktails/suggestion/", CocktailSuggestionView.as_view(), name="api_cocktail_suggestion"),
    path("cocktails/suggestion/shuffle/", CocktailShuffleView.as_view(), name="api_cocktail_shuffle"),
    path("cocktails/suggestion/made/", CocktailMadeView.as_view(), name="api_cocktail_made"),
    path("menu/", MenuListView.as_view(), name="api_menu"),
    path("menu/<int:drink_id>/", MenuDetailView.as_view(), name="api_menu_detail"),
]
