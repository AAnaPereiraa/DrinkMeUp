from django.contrib import admin

from .models import Drinks, DrinksMade, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "taste", "boozy", "spirits", "latest_post")
    search_fields = ("user__username", "user__email")
    list_filter = ("taste", "boozy")
    raw_id_fields = ("user",)


@admin.register(Drinks)
class DrinksAdmin(admin.ModelAdmin):
    list_display = ("cocktail", "taste", "boozy", "spirits")
    search_fields = ("cocktail", "spirits")
    list_filter = ("taste", "boozy")


@admin.register(DrinksMade)
class DrinksMadeAdmin(admin.ModelAdmin):
    list_display = ("user", "cocktail", "rate", "drink")
    search_fields = ("user", "cocktail")
    list_filter = ("rate",)
    raw_id_fields = ("drink",)
