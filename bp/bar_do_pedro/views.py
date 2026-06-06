import random
from django.contrib import messages
from django.contrib.auth import login, logout 
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LogoutView, LoginView, PasswordResetConfirmView, PasswordResetView, PasswordResetDoneView, PasswordResetCompleteView, PasswordChangeView, PasswordChangeDoneView, TemplateView
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from pathlib import Path
from .forms import BarUserForm
from .models import UserProfile, Drinks, DrinksMade
from .services import (
    find_suggestion_pool,
    get_file_content_as_list,
    get_spirits_columns,
    GuestPreferences,
    is_suggestion_in_pool,
    resolve_drink,
    drink_to_session_data,
    RESPONSE_FILE,
)


def _handle_bar_form_post(request, preferences, bar_url_name, cocktails_url_name):
    """Process order / fallback actions from the bar page. Returns redirect or None."""
    action = request.POST.get("action", "order")

    if action == "accept_fallback":
        match_pool = request.session.pop("fallback_match_pool", None)
        request.session.pop("fallback_message", None)
        request.session.pop("show_fallback_prompt", None)
        if match_pool:
            request.session["selected_cocktail"] = drink_to_session_data(random.choice(match_pool))
            return redirect(cocktails_url_name)
        return redirect(bar_url_name)

    if action == "dismiss_fallback":
        request.session.pop("fallback_match_pool", None)
        request.session.pop("fallback_message", None)
        request.session.pop("show_fallback_prompt", None)
        return redirect(bar_url_name)

    if isinstance(preferences, GuestPreferences):
        preferences.save_from_post(request)
    else:
        preferences.boozy = request.POST.get("strength")
        preferences.taste = request.POST.get("taste")
        preferences.spirits = ", ".join(request.POST.getlist("spirit"))
        preferences.save()

    request.session.pop("selected_cocktail", None)
    request.session.pop("fallback_match_pool", None)
    request.session.pop("fallback_message", None)
    request.session.pop("show_fallback_prompt", None)

    match_pool, recommendation_message, is_exact_match = find_suggestion_pool(preferences)

    if not match_pool:
        request.session["message"] = recommendation_message
        return redirect(bar_url_name)

    if is_exact_match:
        request.session["selected_cocktail"] = drink_to_session_data(random.choice(match_pool))
        return redirect(cocktails_url_name)

    request.session["fallback_match_pool"] = match_pool
    request.session["fallback_message"] = recommendation_message
    request.session["show_fallback_prompt"] = True
    return redirect(bar_url_name)


def _render_cocktail_suggestion(request, preferences, template_name, bar_url_name, is_guest=False):
    """Shared logic for authenticated and guest cocktail suggestion pages."""
    match_pool, computed_message, _ = find_suggestion_pool(preferences)

    if not match_pool:
        request.session["message"] = computed_message
        return redirect(bar_url_name)

    cocktail_suggestion = None
    if "selected_cocktail" in request.session:
        stored = request.session["selected_cocktail"]
        if is_suggestion_in_pool(stored, match_pool):
            cocktail_suggestion = stored

    if not cocktail_suggestion:
        cocktail_suggestion = drink_to_session_data(random.choice(match_pool))
        request.session["selected_cocktail"] = cocktail_suggestion

    cocktail_drink = resolve_drink(cocktail_suggestion)

    context = {
        "cocktails": cocktail_drink,
        "is_guest": is_guest,
    }
    if not is_guest:
        context["member"] = preferences
        context["motivational_msg"] = preferences.latest_post

    request.session.pop("message", None)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "DMU":
            cocktail_suggestion = drink_to_session_data(random.choice(match_pool))
            request.session["selected_cocktail"] = cocktail_suggestion
            context["cocktails"] = resolve_drink(cocktail_suggestion)

        if action == "YES" and not is_guest:
            username = request.user.username
            cocktail = request.session.get("selected_cocktail").get("cocktail")
            drink = Drinks.objects.get(cocktail=cocktail)
            rate = request.POST.get("rate")
            comment = request.POST.get("comment")

            DrinksMade.objects.create(
                user=username, cocktail=cocktail, rate=rate, comment=comment, drink=drink
            )

            preferences.latest_post = random.choice(get_file_content_as_list(RESPONSE_FILE))
            preferences.spirits = ""
            preferences.save()

            del request.session["selected_cocktail"]

            return redirect("profile")

        return render(request, template_name, context)

    return render(request, template_name, context)



# Create utilities here


## Password Reset
class CustomPasswordResetView(PasswordResetView):
    """Allows user to reset password if forgotten"""
    template_name = "registration/custom_password_reset_form.html"
    email_template_name = "registration/custom_password_reset_email.html"
    success_url = reverse_lazy("password_reset_done")


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Informs the user if password reset was successfull"""
    template_name = "registration/custom_password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """This view uses a custom template to display the password reset confirmation form."""
    template_name = "registration/custom_password_reset_confirm.html"


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """This view uses a custom template to display the password reset completion message."""
    template_name = "registration/custom_password_reset_complete.html"


class CustomPasswordChangeView(PasswordChangeView):
    """This view uses a custom template to display the password change form."""
    template_name = "registration/change_password.html"


class CustomPasswordChangeDoneView(PasswordChangeDoneView):
    """This view uses a custom template to display the password change success message."""
    template_name = "registration/change_password_done.html"


class CustomLoginView(LoginView):
    """This view uses a custom template to display the login form."""
    template_name = "registration/login.html"

## Signup
def signup_view(request):
    """View that lets the user signup to the page. Sends a welcome mail upon successfull signup"""
    if request.method == "POST":
        form = BarUserForm(request.POST)
        if form.is_valid():  
            username = form.cleaned_data.get("username")                # create the new user
            password = form.cleaned_data.get("password1")
            email = form.cleaned_data.get("email")
            user = User.objects.create_user(username=username, email=email, password=password)  
            user_profile = UserProfile.objects.create(user=user)               # create userinfo related to new user
            user.backend = "django.contrib.auth.backends.ModelBackend"  # Choose correct backend for user creation -> settings/AUTHENTICATION_BACKENDS
            login(request, user)    
            return redirect("profile")
        else:
            return render(request, "registration/signup.html", {"form":form})
    else: 
        form = BarUserForm()
    return render(request, "registration/signup.html", {"form":form})


#logout functionality
def logout_endpoint(request):
    """Logs out the user"""
    logout(request)
    return redirect('/')


@login_required
def delete_user_func(request):
    """Let the user delete his profile"""
    username = request.user.username
    if request.method == 'POST':
        user_id = request.user.id
        user_to_delete = User.objects.filter(pk=user_id)
        delete_user_drinks = DrinksMade.objects.filter(user=username)
        delete_user_drinks.delete()
        user_to_delete.delete()
        
        return redirect('login')
    return render(request, "bar_pedro/delete.html", {'member': username})


@login_required
def profile_view(request):
    """here the user information is displayed in the profile page and user is able to answer some questions so it can suggest cocktails"""
    
    user = request.user
    user_profile = UserProfile.objects.get(user=user)
    latest_post =  user_profile.latest_post
    user_drinks = DrinksMade.objects.filter(user=user.username).order_by('-id')[:10]
    selected_spirits = []
    spirits_columns = get_spirits_columns()

    context = {
        'member': user_profile,
        'motivational_msg': latest_post,
        'drinks': user_drinks,
        'spirits_columns': spirits_columns,
        'selected_spirits': selected_spirits,
        'show_fallback_prompt': request.session.get('show_fallback_prompt', False),
        'fallback_message': request.session.get('fallback_message', ''),
        'error_message': request.session.pop('message', None),
    }

    if request.method == 'POST':
        redirect_response = _handle_bar_form_post(request, user_profile, "profile", "cocktails")
        if redirect_response:
            return redirect_response

    return render(request, 'bar_pedro/profile.html', context)

@login_required
def cocktails(request):
    """This function is to run the drinks list match the user preferences and randomly suggest a cocktail"""
    user = request.user
    user_profile = UserProfile.objects.get(user=user)
    return _render_cocktail_suggestion(
        request, user_profile, "bar_pedro/cocktails.html", "profile", is_guest=False
    )


def guest_view(request):
    """Bar page for guests — order drinks without an account (no My Cocktails)."""
    if request.user.is_authenticated:
        return redirect("profile")

    request.session["guest_mode"] = True
    preferences = GuestPreferences.from_session(request)
    selected_spirits = []

    context = {
        "spirits_columns": get_spirits_columns(),
        "selected_spirits": selected_spirits,
        "show_fallback_prompt": request.session.get("show_fallback_prompt", False),
        "fallback_message": request.session.get("fallback_message", ""),
        "error_message": request.session.pop("message", None),
    }

    if request.method == "POST":
        redirect_response = _handle_bar_form_post(request, preferences, "guest", "guest_cocktails")
        if redirect_response:
            return redirect_response

    return render(request, "bar_pedro/guest.html", context)


def guest_cocktails(request):
    """Cocktail suggestion page for guests."""
    if request.user.is_authenticated:
        return redirect("cocktails")

    preferences = GuestPreferences.from_session(request)
    return _render_cocktail_suggestion(
        request, preferences, "bar_pedro/cocktails.html", "guest", is_guest=True
    )

@login_required
def menu(request):
    """Display the list of all cocktails"""
    cocktails_list = Drinks.objects.all()
    context = { "menu": cocktails_list,
    }
    return render(request, "bar_pedro/menu.html", context)

@login_required
def cocktail_info(request, id):
    "display all the specific cocktail information, clicked on the cocktails list page or my cocktails list"
    cocktail = Drinks.objects.get(id=id)
    context = {
        'cocktail': cocktail
    }
    
    return render(request, "bar_pedro/cocktail_info.html", context)

class LandingPage(TemplateView):
    template_name = "bar_pedro/landing_page.html"

class ImprintView(TemplateView):
    template_name = "bar_pedro/imprint.html"

class PrivacyPolicyView(TemplateView):
    template_name = "bar_pedro/privacy_policy.html"

