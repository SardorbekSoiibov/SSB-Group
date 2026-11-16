from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from urllib.parse import urlencode

from apps.audit.services import record
from apps.core import ratelimit

from . import devices
from .forms import LoginForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from .models import User


class LoginView(auth_views.LoginView):
    template_name = "accounts/_login_modal.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get("X-SSB-Modal") == "1":
            return TemplateResponse(self.request, "accounts/_login_modal.html", context, **response_kwargs)
        # Windows ilovasi faqat boshqaruv tizimini ko'rsatadi: kirish oynasi saytda emas, o'z sahifasida ochiladi.
        from apps.core.desktop_only import is_desktop
        if is_desktop(self.request):
            return TemplateResponse(self.request, "accounts/desktop_login.html", context, **response_kwargs)
        # Alohida kirish sahifasi yo'q: bosh sahifaga qaytaramiz, u yerda kirish oynasi o'zi ochiladi.
        params = {"kirish": "1"}
        nxt = self.get_redirect_url()
        if nxt:
            params["next"] = nxt
        return redirect(f"{reverse('website:home')}?{urlencode(params)}")

    def _ident(self):
        username = (self.request.POST.get("username") or "").lower()
        return f"{username}|{ratelimit.client_ip(self.request)}"

    def post(self, request, *args, **kwargs):
        if ratelimit.is_limited("login", self._ident(), settings.LOGIN_RATE_LIMIT):
            form = self.get_form()
            form.errors.clear()
            form.add_error(None, "Juda ko'p urinish. 15 daqiqadan so'ng qayta urinib ko'ring.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        ratelimit.hit("login", self._ident(), settings.LOGIN_RATE_LIMIT)
        record(None,'auth.login_failed',None,{'login':str(self.request.POST.get('username',''))[:100]},self.request)
        return super().form_invalid(form)

    def form_valid(self, form):
        ratelimit.reset("login", self._ident())
        response = super().form_valid(form)
        # "Meni eslab qol": 30 kun tizimda qoladi. Belgilanmasa — brauzer yopilganda sessiya tugaydi.
        self.request.session.set_expiry(devices.REMEMBER_FOR if self.request.POST.get("remember") else 0)
        record(self.request.user,'auth.login',self.request.user,request=self.request)
        if self.request.headers.get("X-SSB-Modal") == "1":
            return JsonResponse({"redirect": response.url})
        return response


class LogoutView(auth_views.LogoutView):
    def post(self,request,*args,**kwargs):
        if request.user.is_authenticated:record(request.user,'auth.logout',request.user,request=request)
        return super().post(request,*args,**kwargs)


class PasswordChangeView(LoginRequiredMixin, auth_views.PasswordChangeView):
    template_name = "boshqaruv/auth/password_change.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("crm:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Joriy qurilma qoladi, qolgan barcha qurilmalar chiqariladi (eski parol bilan ochilgan sessiyalar).
        devices.register(self.request)
        others = devices.revoke_all(self.request.user, keep_key=self.request.session.session_key)
        record(self.request.user, "user.password_changed", self.request.user, {"devices_signed_out": others}, request=self.request)
        messages.success(self.request, "Parol o'zgartirildi." + (f" Boshqa {others} ta qurilmadan chiqarildingiz." if others else ""))
        return response


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "boshqaruv/auth/password_reset.html"
    form_class = PasswordResetForm
    email_template_name = "accounts/email/password_reset.txt"
    subject_template_name = "accounts/email/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        ip = ratelimit.client_ip(self.request)
        if ratelimit.is_limited("reset", ip, settings.LOGIN_RATE_LIMIT):
            # Same response as success so the endpoint cannot be used to probe accounts.
            return redirect(self.success_url)
        ratelimit.hit("reset", ip, settings.LOGIN_RATE_LIMIT)
        return super().form_valid(form)


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "boshqaruv/auth/password_reset_done.html"


class SetPasswordView(auth_views.PasswordResetConfirmView):
    """Used both for password recovery and for accepting an invitation."""

    template_name = "boshqaruv/auth/set_password.html"
    form_class = SetPasswordForm
    success_url = reverse_lazy("accounts:login")
    post_reset_login = False

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.user
        devices.revoke_all(user)
        if user.status == User.Status.INVITED:
            user.status = User.Status.ACTIVE
            user.save(update_fields=["status", "is_active"])
        record(user, "user.password_changed", user, request=self.request)
        messages.success(self.request, "Parol o'rnatildi. Endi tizimga kiring.")
        return response


# ------------------------------------------------------------------ qurilmalar (modal oyna)

def _devices_response(request, status=200, notice=""):
    from django.shortcuts import render

    current = request.session.session_key
    items = []
    for d in devices.active_devices(request.user):
        info = devices.describe(d.user_agent)
        items.append({"obj": d, "info": info, "current": d.session_key == current})
    items.sort(key=lambda x: (not x["current"], -x["obj"].last_seen.timestamp()))
    return render(request, "accounts/_devices.html", {"items": items, "others": sum(1 for i in items if not i["current"]),
                                                       "notice": notice}, status=status)


@login_required
@never_cache
def device_list(request):
    return _devices_response(request)


@login_required
@require_POST
def device_revoke(request, pk):
    removed = devices.revoke(request.user, pk, request.session.session_key)
    if removed:
        record(request.user, "auth.device_revoked", request.user, {"device": pk}, request)
    return _devices_response(request, notice="Qurilmadan chiqarildi." if removed else "Bu qurilma allaqachon chiqarilgan.")


@login_required
@require_POST
def device_revoke_others(request):
    removed = devices.revoke_others(request.user, request.session.session_key)
    record(request.user, "auth.devices_revoked", request.user, {"count": removed}, request)
    return _devices_response(request, notice=f"{removed} ta qurilmadan chiqarildi." if removed else "Boshqa qurilma yo‘q.")
