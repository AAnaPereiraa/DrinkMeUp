from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from bar_do_pedro.models import Drinks, DrinksMade, UserProfile


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate_username(self, value):
        forbidden_chars = [
            "[", "!", "@", "#", "$", "%", "^", "&", "*",
            "(", ")", ",", ".", "?", "\\", ":", "{", "}", "|",
            "<", ">", "/", "'", "\"",
        ]
        for forbidden_char in forbidden_chars:
            if forbidden_char in value:
                raise serializers.ValidationError("Username can't contain special characters.")
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        UserProfile.objects.create(user=user)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    selected_spirits = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            "user",
            "latest_post",
            "spirits",
            "selected_spirits",
            "taste",
            "boozy",
        ]

    def get_selected_spirits(self, obj):
        return [spirit.strip() for spirit in obj.spirits.split(",") if spirit.strip()]


class PreferencesSerializer(serializers.Serializer):
    taste = serializers.ChoiceField(
        choices=["Sweet", "Citrus", "Bitter", "Fruity", "Fresh", "Sour", "Smoky", "Savory"]
    )
    boozy = serializers.ChoiceField(choices=["Strong", "Medium", "Light"])
    spirits = serializers.ListField(
        child=serializers.CharField(max_length=100),
        allow_empty=True,
    )


class DrinkSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Drinks
        fields = [
            "id",
            "cocktail",
            "spirits",
            "taste",
            "boozy",
            "ingredients",
            "instructions",
            "image_url",
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        if request is None:
            return obj.image.url
        return request.build_absolute_uri(obj.image.url)


class DrinkMadeSerializer(serializers.ModelSerializer):
    drink = DrinkSerializer(read_only=True)

    class Meta:
        model = DrinksMade
        fields = ["id", "cocktail", "rate", "comment", "drink"]


class MarkDrinkMadeSerializer(serializers.Serializer):
    rate = serializers.ChoiceField(
        choices=["Hate it!", "Not bad!", "Well, nice!", "That's the one, loved!"]
    )
    comment = serializers.CharField(required=False, allow_blank=True, default="")
