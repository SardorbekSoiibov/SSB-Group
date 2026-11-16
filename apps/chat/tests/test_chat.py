import uuid

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.chat.models import Message
from apps.core.testing import CompanyTestCase
from apps.notifications.models import Notification


class StaffChatTests(CompanyTestCase):
    def setUp(self):
        self.login(self.dev)
        self.url = reverse('chat:messages', args=[self.designer.pk])

    def send(self, body='Salom, loyiha haqida gaplashamizmi?', client_id=None, url=None):
        return self.client.post(url or self.url, {'body': body, 'client_id': str(client_id or uuid.uuid4())},
                                content_type='application/json')

    def test_delivery_notification_and_private_payload(self):
        response = self.send()
        self.assertEqual(response.status_code, 201)
        item = Message.objects.get()
        self.assertEqual(item.sender, self.dev)
        self.assertEqual(item.recipient, self.designer)
        notice = Notification.objects.get(recipient=self.designer, kind=Notification.Kind.CHAT)
        self.assertEqual(notice.url, reverse('chat:conversation', args=[self.dev.pk]))
        self.login(self.designer)
        data = self.client.get(reverse('chat:messages', args=[self.dev.pk])).json()
        self.assertEqual(data['items'][0]['body'], item.body)
        self.assertFalse(data['items'][0]['mine'])
        self.assertIsNone(Message.objects.get().read_at)  # GET never marks messages read.
        self.assertNotIn('password', str(data))

    def test_duplicate_request_does_not_duplicate_message_or_notice(self):
        key = uuid.uuid4()
        self.assertEqual(self.send(client_id=key).status_code, 201)
        self.assertEqual(self.send(client_id=key).status_code, 200)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(kind=Notification.Kind.CHAT).count(), 1)
        self.assertEqual(self.send('Different text', client_id=key).status_code, 409)
        self.assertEqual(self.send(client_id=key, url=reverse('chat:messages', args=[self.lead.pk])).status_code, 409)

    def test_third_party_including_founder_cannot_read_private_conversation(self):
        item = self.send().json()['item']
        for actor in [self.outsider, self.founder]:
            self.login(actor)
            self.assertEqual(self.client.get(self.url).json()['items'], [])
            response = self.client.post(reverse('chat:read', args=[self.designer.pk]),
                {'through': item['id']}, content_type='application/json')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(self.client.get(reverse('chat:contacts')).json()['unread'], 0)
        self.assertIsNone(Message.objects.get().read_at)

    def test_read_cursor_does_not_consume_new_arrival_or_other_senders(self):
        first = self.send().json()['item']
        second = self.send('Keyinroq kelgan xabar').json()['item']
        other = Message.objects.create(sender=self.lead, recipient=self.designer, body='Other sender')
        self.login(self.designer)
        response = self.client.post(reverse('chat:read', args=[self.dev.pk]),
            {'through': first['id']}, content_type='application/json')
        self.assertEqual(response.json()['read'], 1)
        self.assertEqual(response.json()['unread'], 2)
        self.assertIsNone(Message.objects.get(pk=second['id']).read_at)
        other.refresh_from_db(); self.assertIsNone(other.read_at)
        self.assertEqual(Notification.objects.filter(recipient=self.designer, read_at__isnull=True).count(), 1)
        self.login(self.dev)
        self.assertEqual(self.client.get(self.url).json()['read_through'], first['id'])

    def test_history_and_forward_paging_have_no_gaps(self):
        rows = Message.objects.bulk_create([Message(sender=self.dev, recipient=self.designer,
                                                    body=f'History {i}') for i in range(125)])
        initial = self.client.get(self.url).json()
        self.assertEqual([i['id'] for i in initial['items']], [r.pk for r in rows[-50:]])
        self.assertTrue(initial['has_more'])
        older = self.client.get(self.url, {'before': rows[-50].pk}).json()
        self.assertEqual([i['id'] for i in older['items']], [r.pk for r in rows[25:75]])
        after = self.client.get(self.url, {'after': 0}).json()
        self.assertEqual(len(after['items']), 100)
        self.assertTrue(after['has_more'])
        rest = self.client.get(self.url, {'after': after['items'][-1]['id']}).json()
        self.assertEqual([i['id'] for i in rest['items']], [r.pk for r in rows[100:]])
        self.assertFalse(rest['has_more'])

    def test_validation_and_no_self_chat(self):
        for body in ['', '   ', 'x' * 4001, 12, 'bad\x00text']:
            self.assertEqual(self.send(body).status_code, 400)
        self.assertEqual(self.client.post(self.url, {'body':'hello','client_id':'invalid'}, content_type='application/json').status_code, 400)
        self.assertEqual(self.send(url=reverse('chat:messages', args=[self.dev.pk])).status_code, 404)
        self.assertFalse(Message.objects.exists())
        for query in [{'after':'-1'}, {'before':'bad'}, {'after':'9'*40}, {'before':1,'after':2}]:
            self.assertEqual(self.client.get(self.url, query).status_code, 400)

    def test_inactive_peer_history_preserved_but_new_sends_blocked(self):
        self.send()
        self.designer.status = User.Status.DEACTIVATED
        self.designer.save()
        response = self.client.get(self.url)
        self.assertEqual(len(response.json()['items']), 1)
        self.assertFalse(response.json()['peer']['active'])
        self.assertEqual(self.send('Cannot send now').status_code, 400)
        self.assertContains(self.client.get(reverse('chat:conversation', args=[self.designer.pk])), 'disabled')
        self.outsider.status = User.Status.SUSPENDED
        self.outsider.save()
        # Anyone in the database can be found and opened; only sending stays blocked.
        self.assertEqual(self.client.get(reverse('chat:messages', args=[self.outsider.pk])).status_code, 200)
        self.assertEqual(self.send('Cannot send', url=reverse('chat:messages', args=[self.outsider.pk])).status_code, 400)

    def test_muted_chat_only_suppresses_notice_not_message(self):
        self.designer.muted_notifications = [Notification.Kind.CHAT]
        self.designer.save()
        self.assertEqual(self.send().status_code, 201)
        self.assertEqual(Message.objects.count(), 1)
        self.assertFalse(Notification.objects.filter(recipient=self.designer).exists())

    def test_contacts_search_unread_and_navigation(self):
        Message.objects.create(sender=self.designer, recipient=self.dev, body='Unread preview')
        response = self.client.get(reverse('chat:contacts'), {'q': self.designer.username})
        self.assertEqual(response.json()['unread'], 1)
        self.assertEqual(response.json()['items'][0]['id'], self.designer.pk)
        self.assertEqual(response.json()['items'][0]['unread'], 1)
        self.assertEqual(response.json()['items'][0]['last'], 'Unread preview')
        response = self.client.get(reverse('chat:index'))
        self.assertContains(response, 'Xodimlar chati')
        self.assertContains(response, 'data-chat-unread')
        self.assertContains(response, 'boshqaruv/chat.js')
        self.assertEqual(self.client.get(reverse('enterprise:api_notifications')).json()['chat_unread'], 1)

    def test_authentication_csrf_and_disabled_role(self):
        client = Client(enforce_csrf_checks=True); client.force_login(self.dev)
        self.assertEqual(client.post(self.url, {'body':'Unauthorized mutation','client_id':str(uuid.uuid4())}, content_type='application/json').status_code, 403)
        self.client.logout()
        self.assertIn(self.client.get(self.url).status_code, [401,403])
        self.assertEqual(self.client.get(reverse('chat:index')).status_code, 302)
        self.login(self.dev)
        self.dev.role.is_active = False; self.dev.role.save()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_text_is_returned_as_data_not_executable_markup(self):
        text = '<img src=x onerror=alert(1)> & <script>steal()</script>'
        response = self.send(text)
        self.assertEqual(response.json()['item']['body'], text)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('no-store', response['Cache-Control'])
