from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from apps.audit.services import record
from . import channels
from .models import ChannelCheck, ExternalDelivery, TelegramConnection


@never_cache
@login_required
@sensitive_post_parameters('bot_token')
def connections(request):
    if not request.user.is_active:
        raise PermissionDenied
    link = None
    manager = request.user.has_cap('settings.manage')
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action in ['check_email', 'check_telegram', 'save_telegram'] and not manager:
            raise PermissionDenied
        if action not in ['check_email', 'check_telegram', 'save_telegram', 'test_email', 'test_telegram', 'link', 'refresh', 'disconnect']:
            raise PermissionDenied
        sending_test = action in ['test_email', 'test_telegram']
        key = f'channel-action-v2:{request.user.pk}:{action}'
        if not cache.add(key, True, 30 if sending_test else 60):
            messages.info(request, 'Sinov xabari yaqinda yuborildi. Qayta yuborish uchun 30 soniya kuting.' if sending_test
                          else 'So‘rovingiz tekshirilmoqda. Tugmani qayta bosishingiz shart emas.')
            return redirect('crm:connections')
        succeeded = False
        try:
            if action == 'save_telegram':
                token = request.POST.get('bot_token', '').strip()
                import re
                if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', token):
                    raise ValidationError('Token noto‘g‘ri. BotFather yuborgan tokenni to‘liq nusxalang.')
                bot = channels.telegram_call('getMe', token=token)
                if not bot.get('is_bot'):
                    raise ValidationError('Bu token Telegram botga tegishli emas.')
                from .configuration import save_telegram
                save_telegram(token, bot.get('username', ''))
                ChannelCheck.objects.update_or_create(channel='telegram', defaults={'fingerprint': channels.fingerprint('telegram'), 'successful': True})
                messages.success(request, f"@{bot['username']} bot tekshirildi va saqlandi. Endi 2-qadamda Telegram hisobingizni ulang.")
            elif action.startswith('check_'):
                channels.check_channel(action.removeprefix('check_'))
                messages.success(request, 'Serverga ulanish muvaffaqiyatli tekshirildi.')
            elif action == 'test_email':
                channels.send_email(request.user, 'SSB Boshqaruv — sinov xati', 'Email yuborish ishlayapti. Bu siz so‘ragan sinov xati.')
                messages.success(request, 'Sinov xati profilingizdagi emailga yuborildi. Kiruvchi va spam papkasini tekshiring.')
            elif action == 'test_telegram':
                channels.send_telegram(request.user, '✅ <b>Sinov xabari</b>\n\nTelegram bildirishnomalari ishlayapti. Vazifalar, muddatlar va e’lonlar shu yerga keladi.\n\n<i>SSB Boshqaruv</i>')
                request.session['telegram_tested'] = channels.fingerprint('telegram')
                messages.success(request, 'Shaxsiy Telegram hisobingizga sinov xabari yuborildi.')
            elif action == 'link':
                link = channels.create_link(request.user)
            elif action == 'refresh':
                channels.poll_telegram()
                messages.success(request, 'Telegram ulanishlari tekshirildi. Hisob holati quyida ko‘rinadi.')
            else:
                TelegramConnection.objects.filter(user=request.user).update(enabled=False, chat_id=None, link_hash='', expires_at=None)
                messages.success(request, 'Telegram hisobingiz uzildi.')
            succeeded = True
            record(request.user, 'channels.'+action, request.user, {})
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        except Exception:
            messages.error(request, 'Yuborish amalga oshmadi. Ulanish sozlamalari va profilingizni tekshiring.')
        finally:
            # Only successful test messages retain a cooldown. Failed attempts
            # and configuration operations can be corrected and retried immediately.
            if not sending_test or not succeeded:
                cache.delete(key)
        if not link:
            return redirect('crm:connections')
    own = TelegramConnection.objects.filter(user=request.user, bot_fingerprint=channels.fingerprint('telegram')).first()
    jobs = ExternalDelivery.objects.filter(notification__recipient=request.user)
    from .runtime import start_after_commit
    start_after_commit()
    return render(request, 'boshqaruv/operations/connections.html', {'email': channels.status('email'),
        'telegram': channels.status('telegram'), 'telegram_account': own, 'link': link, 'manager': manager,
        'telegram_tested': bool(own and own.enabled and request.session.get('telegram_tested') == channels.fingerprint('telegram')),
        'pending_count': jobs.filter(status='pending').count(), 'failed_count': jobs.filter(status='failed').count()})
