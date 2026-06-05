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
    is_suggestion_in_pool,
    resolve_drink,
    drink_to_session_data,
    RESPONSE_FILE,
)



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

    # Build a dynamic list of all spirits present in the Drinks table
    all_spirits = set()
    for s in Drinks.objects.values_list('spirits', flat=True):
        if s:
            for part in s.split(','):
                sp = part.strip()
                if sp:
                    all_spirits.add(sp)
    available_spirits = sorted(all_spirits)

    # Always show unchecked spirit boxes on the bar page.
    selected_spirits = []

    # Split the available spirits into columns of at most 10 items each
    spirits_columns = [available_spirits[i:i + 10] for i in range(0, len(available_spirits), 10)]

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
        action = request.POST.get('action', 'order')

        if action == 'accept_fallback':
            match_pool = request.session.pop('fallback_match_pool', None)
            request.session.pop('fallback_message', None)
            request.session.pop('show_fallback_prompt', None)
            if match_pool:
                request.session['selected_cocktail'] = drink_to_session_data(random.choice(match_pool))
                return redirect('cocktails')
            return redirect('profile')

        if action == 'dismiss_fallback':
            request.session.pop('fallback_match_pool', None)
            request.session.pop('fallback_message', None)
            request.session.pop('show_fallback_prompt', None)
            return redirect('profile')

        user_profile.boozy = request.POST.get('strength')
        user_profile.taste = request.POST.get('taste')
        selected_spirits = request.POST.getlist('spirit')
        user_profile.spirits = ', '.join(selected_spirits)

        user_profile.save()
        request.session.pop('selected_cocktail', None)
        request.session.pop('fallback_match_pool', None)
        request.session.pop('fallback_message', None)
        request.session.pop('show_fallback_prompt', None)

        match_pool, recommendation_message, is_exact_match = find_suggestion_pool(user_profile)

        if not match_pool:
            request.session['message'] = recommendation_message
            return redirect('profile')

        if is_exact_match:
            request.session['selected_cocktail'] = drink_to_session_data(random.choice(match_pool))
            return redirect('cocktails')

        request.session['fallback_match_pool'] = match_pool
        request.session['fallback_message'] = recommendation_message
        request.session['show_fallback_prompt'] = True
        return redirect('profile')

    return render(request, 'bar_pedro/profile.html', context)

@login_required
def cocktails(request):
    """This function is to run the drinks list match the user preferences and randomly suggest a cocktail"""
    user = request.user
    user_profile = UserProfile.objects.get(user=user)
    latest_post = user_profile.latest_post

    match_pool, computed_message, _ = find_suggestion_pool(user_profile)

    if not match_pool:
        request.session['message'] = computed_message
        return redirect("profile")

    cocktail_suggestion = None
    if 'selected_cocktail' in request.session:
        stored = request.session['selected_cocktail']
        if is_suggestion_in_pool(stored, match_pool):
            cocktail_suggestion = stored

    if not cocktail_suggestion:
        cocktail_suggestion = drink_to_session_data(random.choice(match_pool))
        request.session['selected_cocktail'] = cocktail_suggestion

    cocktail_drink = resolve_drink(cocktail_suggestion)

    context = {
        'member': user_profile,
        'motivational_msg': latest_post,
        'cocktails': cocktail_drink,
    }
    request.session.pop('message', None)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == "DMU":
            cocktail_suggestion = drink_to_session_data(random.choice(match_pool))
            request.session['selected_cocktail'] = cocktail_suggestion
            context['cocktails'] = resolve_drink(cocktail_suggestion)

        if action == "YES":
            username = user.username
            cocktail = request.session.get('selected_cocktail').get("cocktail")
            drink = Drinks.objects.get(cocktail=cocktail)
            rate = request.POST.get('rate')
            comment = request.POST.get('comment')

            DrinksMade.objects.create(user=username, cocktail=cocktail, rate=rate, comment=comment, drink=drink)

            user_profile.latest_post = random.choice(get_file_content_as_list(RESPONSE_FILE))
            user_profile.spirits = ""
            user_profile.save()

            del request.session['selected_cocktail']

            return redirect("profile")

        return render(request, 'bar_pedro/cocktails.html', context)

    return render(request, 'bar_pedro/cocktails.html', context)

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

