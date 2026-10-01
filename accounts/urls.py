from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("login/verify/", views.login_2fa, name="login_2fa"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("setup/", views.setup, name="setup"),
    path("account/", views.my_account, name="my_account"),
    path("account/2fa/", views.two_factor_setup, name="two_factor_setup"),
    path("account/2fa/disable/", views.two_factor_disable, name="two_factor_disable"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_form, name="user_create"),
    path("users/<int:pk>/", views.user_form, name="user_edit"),
    path("users/<int:pk>/reset-2fa/", views.user_reset_two_factor, name="user_reset_2fa"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
]
