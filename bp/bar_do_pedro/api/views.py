from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from bar_do_pedro.models import Drinks, DrinksMade
from bar_do_pedro.services import (
    clear_stored_suggestion,
    get_available_spirits,
    get_cocktail_suggestion,
    get_or_create_user_profile,
    record_drink_made,
    shuffle_cocktail_suggestion,
)

from .serializers import (
    DrinkMadeSerializer,
    DrinkSerializer,
    MarkDrinkMadeSerializer,
    PreferencesSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserSerializer,
)


def build_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": build_tokens_for_user(user),
            },
            status=status.HTTP_201_CREATED,
        )


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_profile = get_or_create_user_profile(request.user)
        serializer = UserProfileSerializer(user_profile)
        return Response(serializer.data)

    def delete(self, request):
        username = request.user.username
        DrinksMade.objects.filter(user=username).delete()
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvailableSpiritsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"spirits": get_available_spirits()})


class PreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = PreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_profile = get_or_create_user_profile(request.user)
        user_profile.taste = serializer.validated_data["taste"]
        user_profile.boozy = serializer.validated_data["boozy"]
        user_profile.spirits = ", ".join(serializer.validated_data["spirits"])
        user_profile.save()
        clear_stored_suggestion(request.user.id)

        return Response(UserProfileSerializer(user_profile).data)


class DrinkHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        drinks = DrinksMade.objects.filter(user=request.user.username).order_by("-id")[:10]
        serializer = DrinkMadeSerializer(drinks, many=True, context={"request": request})
        return Response(serializer.data)


class CocktailSuggestionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_profile = get_or_create_user_profile(request.user)

        if not user_profile.taste or user_profile.taste == "Taste":
            return Response(
                {"detail": "Set your taste preference before requesting a cocktail."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user_profile.boozy or user_profile.boozy == "Boozy":
            return Response(
                {"detail": "Set your boozy preference before requesting a cocktail."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestion, info_message = get_cocktail_suggestion(user_profile, request.user.id)
        if not suggestion:
            return Response({"detail": info_message}, status=status.HTTP_404_NOT_FOUND)

        drink = get_object_or_404(Drinks, pk=suggestion["id"])
        response_data = DrinkSerializer(drink, context={"request": request}).data
        if info_message:
            response_data["recommendation_message"] = info_message
        return Response(response_data)


class CocktailShuffleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_profile = get_or_create_user_profile(request.user)
        suggestion, info_message = shuffle_cocktail_suggestion(user_profile, request.user.id)
        if not suggestion:
            return Response({"detail": info_message}, status=status.HTTP_404_NOT_FOUND)

        drink = get_object_or_404(Drinks, pk=suggestion["id"])
        response_data = DrinkSerializer(drink, context={"request": request}).data
        if info_message:
            response_data["recommendation_message"] = info_message
        return Response(response_data)


class CocktailMadeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MarkDrinkMadeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            drinks_made = record_drink_made(
                request.user,
                serializer.validated_data["rate"],
                serializer.validated_data.get("comment", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Drinks.DoesNotExist:
            return Response(
                {"detail": "The suggested cocktail could not be found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user_profile = get_or_create_user_profile(request.user)
        return Response(
            {
                "drink_made": DrinkMadeSerializer(
                    drinks_made,
                    context={"request": request},
                ).data,
                "profile": UserProfileSerializer(user_profile).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MenuListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DrinkSerializer
    queryset = Drinks.objects.all().order_by("cocktail")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context


class MenuDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DrinkSerializer
    queryset = Drinks.objects.all()
    lookup_url_kwarg = "drink_id"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

