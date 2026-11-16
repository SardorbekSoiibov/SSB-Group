from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("kirish/", views.LoginView.as_view(), name="login"),
    path("chiqish/", views.LogoutView.as_view(), name="logout"),
    path("parol/", views.PasswordChangeView.as_view(), name="password_change"),
    path("qurilmalar/", views.device_list, name="devices"),
    path("qurilmalar/<int:pk>/chiqarish/", views.device_revoke, name="device_revoke"),
    path("qurilmalar/boshqalari/chiqarish/", views.device_revoke_others, name="device_revoke_others"),
    path("parol-tiklash/", views.PasswordResetView.as_view(), name="password_reset"),
    path("parol-tiklash/yuborildi/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("parol-ornatish/<uidb64>/<token>/", views.SetPasswordView.as_view(), name="set_password"),
]
