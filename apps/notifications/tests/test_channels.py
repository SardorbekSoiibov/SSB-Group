import hashlib
from datetime import timedelta
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from pathlib import Path
import tempfile
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from apps.core.testing import CompanyTestCase
from apps.notifications import channels
from apps.notifications.models import ChannelCheck, ExternalDelivery, TelegramConnection
from apps.notifications.services import notify


@override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.example.com',
                   EMAIL_USE_TLS=True, EMAIL_USE_SSL=False, EMAIL_NOTIFICATIONS_ENABLED=True,
                   TELEGRAM_BOT_TOKEN='123456:TEST_TOKEN', TELEGRAM_BOT_USERNAME='test_bot', TELEGRAM_NOTIFICATIONS_ENABLED=True)
class ChannelTests(CompanyTestCase):
    def setUp(self):
        self.dev.email = 'dev@example.com'
        self.dev.save()

    def binding(self):
        return TelegramConnection.objects.create(user=self.dev, enabled=True, chat_id=123,
                                                   bot_fingerprint=channels.fingerprint('telegram'))

    def test_configuration_alone_does_not_claim_connection(self):
        self.assertTrue(channels.status('email')['configured'])
        self.assertFalse(channels.status('email')['connected'])
        with patch.object(channels, 'get_connection'):
            channels.check_channel('email')
        self.assertTrue(channels.status('email')['connected'])
        with override_settings(EMAIL_HOST='changed.example.com'):
            self.assertFalse(channels.status('email')['connected'])

    def test_failed_check_never_exposes_credentials(self):
        with patch.object(channels, 'get_connection', side_effect=RuntimeError('secret-password')):
            with self.assertRaises(ValidationError) as error:
                channels.check_channel('email')
        self.assertNotIn('secret-password', str(error.exception))
        self.assertFalse(ChannelCheck.objects.get(channel='email').successful)

    def test_notifications_enqueue_both_channels_once_and_send_to_correct_person(self):
        self.binding()
        notify([self.dev], 'announcement', 'Test notice', dedupe_key='test-1')
        notify([self.dev], 'announcement', 'Test notice', dedupe_key='test-1')
        self.assertEqual(ExternalDelivery.objects.count(), 2)
        with patch.object(channels, 'send_email') as email, patch.object(channels, 'telegram_call') as telegram:
            self.assertEqual(channels.deliver_pending(), 2)
            self.assertEqual(channels.deliver_pending(), 0)
        self.assertEqual(email.call_args.args[0], self.dev)
        self.assertEqual(telegram.call_args.args[1]['chat_id'], 123)
        self.assertEqual(ExternalDelivery.objects.filter(status='sent').count(), 2)

    def test_external_failure_preserves_internal_notification_and_schedules_retry(self):
        note = notify([self.dev], 'announcement', 'Keep internal')[0]
        with patch.object(channels, 'send_email', side_effect=TimeoutError('secret')):
            channels.deliver_pending()
        self.assertTrue(self.dev.notifications.filter(pk=note.pk).exists())
        job = ExternalDelivery.objects.get()
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.status, 'pending')
        self.assertEqual(job.error_code, 'TimeoutError')
        self.assertGreater(job.next_attempt_at, timezone.now())

    def test_chat_and_muted_notifications_are_not_forwarded(self):
        self.binding()
        notify([self.dev], 'chat_message', 'Private chat')
        self.assertFalse(ExternalDelivery.objects.exists())
        self.dev.muted_notifications = ['announcement']
        self.dev.save()
        self.assertFalse(notify([self.dev], 'announcement', 'Muted'))

    def test_bot_link_is_single_use_and_private(self):
        with patch.object(channels, 'telegram_call', return_value={'username': 'test_bot'}):
            url = channels.create_link(self.dev)
        token = url.split('start=')[1]
        link = TelegramConnection.objects.get(user=self.dev)
        self.assertNotEqual(link.link_hash, token)
        self.assertFalse(link.enabled)
        update = {'update_id': 1, 'message': {'chat': {'type': 'private', 'id': 123}, 'from': {'id': 123}, 'text': '/start '+token}}
        with patch.object(channels, 'telegram_call', return_value=[update]):
            channels.poll_telegram()
        link.refresh_from_db()
        self.assertEqual(link.chat_id, 123)
        self.assertTrue(link.enabled)
        self.assertEqual(link.link_hash, '')
        update['message']['chat'] = {'type': 'private', 'id': 456}
        update['message']['from'] = {'id': 456}
        with patch.object(channels, 'telegram_call', return_value=[update]):
            channels.poll_telegram()
        link.refresh_from_db()
        self.assertEqual(link.chat_id, 123)

    def test_group_start_does_not_link_and_expired_token_is_rejected(self):
        token = 'a'*32
        link = TelegramConnection.objects.create(user=self.dev, link_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=timezone.now()-timedelta(minutes=1), bot_fingerprint=channels.fingerprint('telegram'))
        update = {'update_id': 2, 'message': {'chat': {'type': 'private', 'id': 123}, 'from': {'id': 123}, 'text': '/start '+token}}
        with patch.object(channels, 'telegram_call', return_value=[update]):
            channels.poll_telegram()
        link.refresh_from_db()
        self.assertFalse(link.enabled)
        link.expires_at = timezone.now()+timedelta(minutes=10)
        link.save()
        update['message']['chat']['type'] = 'group'
        with patch.object(channels, 'telegram_call', return_value=[update]):
            channels.poll_telegram()
        link.refresh_from_db()
        self.assertFalse(link.enabled)

    def test_token_change_requires_relink(self):
        self.binding()
        with override_settings(TELEGRAM_BOT_TOKEN='987654:NEW_TOKEN'):
            with self.assertRaises(ValidationError):
                channels.send_telegram(self.dev, 'Not sent')

    def test_employee_can_test_only_own_email_and_cannot_check_server(self):
        self.login(self.dev)
        with patch.object(channels, 'send_email') as send:
            response = self.client.post(reverse('crm:connections'), {'action': 'test_email', 'recipient': 'other@example.com'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(send.call_args.args[0].pk, self.dev.pk)
        self.assertEqual(self.client.post(reverse('crm:connections'), {'action': 'check_email'}).status_code, 403)

    def test_connection_page_renders_and_does_not_expose_bot_token(self):
        self.login(self.founder)
        response = self.client.get(reverse('crm:connections'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'TEST_TOKEN')

    def test_admin_saves_verified_token_without_restart_or_secret_echo(self):
        from apps.notifications.configuration import telegram_token
        cache.clear()
        token = '123456:' + 'ValidTokenExample_1234567890'
        self.login(self.founder)
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder)):
            env = Path(folder)/'.env'
            env.write_text('UNRELATED_SETTING=keep-me\n', encoding='utf-8')
            with patch.object(channels, 'telegram_call', return_value={'is_bot': True, 'username': 'verified_bot'}) as api:
                response = self.client.post(reverse('crm:connections'), {'action': 'save_telegram', 'bot_token': token})
            self.assertEqual(response.status_code, 302)
            api.assert_called_once_with('getMe', token=token)
            self.assertEqual(telegram_token(), token)
            self.assertIn('UNRELATED_SETTING=keep-me', env.read_text(encoding='utf-8'))
            self.assertTrue(channels.status('telegram')['connected'])
            page = self.client.get(reverse('crm:connections'))
            self.assertNotContains(page, token)
            self.assertContains(page, 'name="bot_token"')

    def test_unverified_token_never_overwrites_saved_token(self):
        cache.clear()
        self.login(self.founder)
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder)):
            env = Path(folder)/'.env'
            env.write_text('TELEGRAM_BOT_TOKEN=123456:ExistingToken_123456789012345\n', encoding='utf-8')
            before = env.read_bytes()
            with patch.object(channels, 'telegram_call', side_effect=ValidationError('Bot tekshirilmadi')):
                self.client.post(reverse('crm:connections'), {'action': 'save_telegram', 'bot_token': '123456:NewToken_1234567890123456789'})
            self.assertEqual(env.read_bytes(), before)

    def test_employee_cannot_replace_company_bot(self):
        self.login(self.dev)
        response = self.client.post(reverse('crm:connections'), {'action': 'save_telegram', 'bot_token': '123456:Token_12345678901234567890'})
        self.assertEqual(response.status_code, 403)

    def test_worker_start_is_once_per_web_process(self):
        from apps.notifications import runtime
        with patch.object(runtime, '_worker', None), patch.object(runtime.threading, 'Thread') as thread:
            thread.return_value.is_alive.return_value = True
            runtime.start_worker()
            runtime.start_worker()
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()

    def test_failed_token_can_be_corrected_and_retried_immediately(self):
        cache.clear()
        self.login(self.founder)
        data = {'action': 'save_telegram', 'bot_token': '123456:ValidLookingToken_1234567890'}
        with patch.object(channels, 'telegram_call', side_effect=ValidationError('Token tekshirilmadi')) as api:
            self.client.post(reverse('crm:connections'), data)
            self.client.post(reverse('crm:connections'), data)
        self.assertEqual(api.call_count, 2)
        self.assertFalse(cache.get(f'channel-action-v2:{self.founder.pk}:save_telegram'))

    def test_successful_test_message_is_not_sent_twice_on_double_click(self):
        cache.clear()
        self.login(self.dev)
        with patch.object(channels, 'send_email') as send:
            self.client.post(reverse('crm:connections'), {'action': 'test_email'})
            self.client.post(reverse('crm:connections'), {'action': 'test_email'})
        send.assert_called_once()

    def test_failed_test_message_can_be_retried_without_waiting(self):
        cache.clear()
        self.login(self.dev)
        with patch.object(channels, 'send_email', side_effect=ValidationError('Ulanish uzildi')) as send:
            self.client.post(reverse('crm:connections'), {'action': 'test_email'})
            self.client.post(reverse('crm:connections'), {'action': 'test_email'})
        self.assertEqual(send.call_count, 2)

    def test_network_error_is_distinguished_and_token_is_not_exposed(self):
        with patch.object(channels, 'urlopen', side_effect=URLError(ConnectionRefusedError())):
            with self.assertRaises(ValidationError) as caught:
                channels.telegram_call('getMe')
        self.assertEqual(caught.exception.code, 'telegram_network')
        self.assertNotIn('TEST_TOKEN', str(caught.exception))

    def test_invalid_token_and_busy_bot_have_specific_errors(self):
        for code in [401, 404, 409, 429]:
            with patch.object(channels, 'urlopen', side_effect=HTTPError('https://api.telegram.org/botSECRET/getMe', code, 'error', {}, None)):
                with self.assertRaises(ValidationError) as caught:
                    channels.telegram_call('getMe')
            self.assertEqual(caught.exception.code, f'telegram_http_{code}')
            self.assertNotIn('SECRET', str(caught.exception))

    def test_timeout_is_distinguished(self):
        with patch.object(channels, 'urlopen', side_effect=TimeoutError()):
            with self.assertRaises(ValidationError) as caught:
                channels.telegram_call('getMe')
        self.assertEqual(caught.exception.code, 'telegram_timeout')
