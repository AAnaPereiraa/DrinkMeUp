from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from .views import CustomPasswordResetView, CustomLoginView, CustomPasswordResetDoneView, CustomPasswordResetConfirmView, CustomPasswordResetCompleteView, CustomPasswordChangeDoneView, CustomPasswordChangeView, LandingPage, PrivacyPolicyView, ImprintView
from . import views


urlpatterns = [    
    ## Auth
    # Password management
    path('password-reset/', CustomPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', CustomPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', CustomPasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('password-change/', CustomPasswordChangeView.as_view(), name='password_change'),
    path('password-change/done/', CustomPasswordChangeDoneView.as_view(), name='password_change_done'),


    # Signin/Signout/Signup/Landing
    path('logout/', views.logout_endpoint, name='logout'),
    path("login/", CustomLoginView.as_view(), name="login"),
    path('signup/', views.signup_view, name="signup"),

    #Main pages
    path('', LandingPage.as_view(), name="welcome"),
    path("profile/", views.profile_view, name="profile"),
    path("guest/", views.guest_view, name="guest"),
    path("guest/cocktails/", views.guest_cocktails, name="guest_cocktails"),
    path('cocktails/', views.cocktails, name='cocktails'),
    path('menu/', views.menu, name='menu'),
    path('details/<int:id>/', views.cocktail_info, name='details'),
    path('delete/', views.delete_user_func, name='delete'),
    path("imprint/", ImprintView.as_view(), name="imprint"),
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("imprint.html", ImprintView.as_view()),
    path("privacy-policy.html", PrivacyPolicyView.as_view()),
 ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

