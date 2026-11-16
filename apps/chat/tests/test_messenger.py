"""Telegram-style features of the staff chat: reply, edit, delete, forward, reactions, pin, files, presence."""
import json
import uuid
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.chat.models import Message, Presence, Reaction
from apps.core.testing import CompanyTestCase
from apps.notifications.models import Notification


def png():
    buffer = BytesIO()
    Image.new('RGB', (4, 4), 'navy').save(buffer, 'PNG')
    return SimpleUploadedFile('rasm.png', buffer.getvalue(), content_type='image/png')


def release(response):
    # response.close() would close the test transaction's DB connection.
    for close in response._resource_closers:
        close()


class MessengerTests(CompanyTestCase):
    def setUp(self):
        self.login(self.dev)
        self.url = reverse('chat:messages', args=[self.designer.pk])

    def post(self, url, data=None):
        return self.client.post(url, json.dumps(data or {}), content_type='application/json')

    def send(self, body='Salom', **extra):
        return self.post(self.url, {'body': body, 'client_id': str(uuid.uuid4()), **extra})

    def message(self, **extra):
        return Message.objects.get(pk=self.send(**extra).json()['item']['id'])

    def as_designer(self, **params):
        self.login(self.designer)
        return self.client.get(reverse('chat:messages', args=[self.dev.pk]), params).json()

    def test_reply_is_linked_and_must_belong_to_the_conversation(self):
        first = self.message(body='Birinchi')
        item = self.send(body='Javob', reply_to=first.pk).json()['item']
        self.assertEqual(item['reply_to']['id'], first.pk)
        self.assertEqual(item['reply_to']['preview'], 'Birinchi')
        foreign = Message.objects.create(sender=self.lead, recipient=self.designer, body='Maxfiy')
        response = self.send(body='Javob', reply_to=foreign.pk)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('Maxfiy', response.content.decode())

    def test_edit_rules(self):
        item = self.message(body='Eski')
        url = reverse('chat:message', args=[item.pk])
        data = self.client.patch(url, json.dumps({'body': 'Yangi'}), content_type='application/json').json()['item']
        self.assertEqual((data['body'], data['edited']), ('Yangi', True))
        self.assertEqual(self.client.patch(url, json.dumps({'body': '  '}), content_type='application/json').status_code, 400)
        Message.objects.filter(pk=item.pk).update(created_at=timezone.now() - timedelta(hours=49))
        self.assertEqual(self.client.patch(url, json.dumps({'body': 'Kech'}), content_type='application/json').status_code, 400)
        self.login(self.designer)
        self.assertEqual(self.client.patch(url, json.dumps({'body': 'Begona'}), content_type='application/json').status_code, 403)

    def test_delete_clears_content_for_both_sides_and_only_sender_may_delete(self):
        item = self.message(body='Maxfiy matn')
        url = reverse('chat:message', args=[item.pk])
        self.login(self.designer)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.login(self.dev)
        self.assertTrue(self.client.delete(url).json()['item']['deleted'])
        item.refresh_from_db()
        self.assertEqual(item.body, '')
        self.assertNotIn('Maxfiy matn', Notification.objects.get(recipient=self.designer, dedupe_key=f'chat:{item.pk}').body)
        data = self.as_designer()
        self.assertTrue(data['items'][0]['deleted'])
        self.assertNotIn('Maxfiy', json.dumps(data))

    def test_changes_to_old_messages_reach_an_open_conversation(self):
        item = self.message(body='Eski')
        moment = self.as_designer()['server_time']
        self.login(self.dev)
        self.client.patch(reverse('chat:message', args=[item.pk]), json.dumps({'body': 'Yangi'}), content_type='application/json')
        changes = self.as_designer(after=item.pk, since=moment)['changes']
        self.assertEqual([(c['id'], c['body']) for c in changes], [(item.pk, 'Yangi')])
        self.assertEqual(self.client.get(reverse('chat:messages', args=[self.dev.pk]), {'since': 'yaroqsiz'}).status_code, 400)

    def test_reaction_toggle_replace_and_validation(self):
        item = self.message()
        url = reverse('chat:react', args=[item.pk])
        self.assertEqual(self.post(url, {'emoji': '👍'}).json()['item']['reactions'], [{'emoji': '👍', 'count': 1, 'mine': True}])
        self.assertEqual(self.post(url, {'emoji': '🔥'}).json()['item']['reactions'][0]['emoji'], '🔥')
        self.assertEqual(Reaction.objects.count(), 1)
        self.assertEqual(self.post(url, {'emoji': '🔥'}).json()['item']['reactions'], [])
        self.assertEqual(self.post(url, {'emoji': '<script>'}).status_code, 400)

    def test_pin_is_shared_by_both_participants(self):
        item = self.message(body='Muhim')
        self.assertTrue(self.post(reverse('chat:pin', args=[item.pk]), {'pinned': True}).json()['item']['pinned'])
        self.assertEqual(self.as_designer()['pinned'], {'id': item.pk, 'preview': 'Muhim'})
        self.post(reverse('chat:pin', args=[item.pk]), {'pinned': False})
        self.assertIsNone(self.client.get(reverse('chat:messages', args=[self.dev.pk])).json()['pinned'])

    def test_third_party_cannot_touch_a_private_message(self):
        item = self.message(body='Shaxsiy')
        self.login(self.founder)
        self.assertEqual(self.post(reverse('chat:react', args=[item.pk]), {'emoji': '👍'}).status_code, 404)
        self.assertEqual(self.post(reverse('chat:pin', args=[item.pk]), {'pinned': True}).status_code, 404)
        self.assertEqual(self.client.delete(reverse('chat:message', args=[item.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('chat:file', args=[item.pk])).status_code, 404)
        response = self.post(reverse('chat:forward', args=[self.lead.pk]), {'message': item.pk, 'client_id': str(uuid.uuid4())})
        self.assertEqual(response.status_code, 404)

    def test_forward_copies_message_with_original_author(self):
        item = self.message(body='Uzatiladi')
        self.login(self.designer)
        data = self.post(reverse('chat:forward', args=[self.lead.pk]), {'message': item.pk, 'client_id': str(uuid.uuid4())}).json()['item']
        self.assertEqual((data['body'], data['forwarded_from']), ('Uzatiladi', self.dev.display_name))
        self.assertFalse(data['editable'])

    def test_image_and_file_upload_download_and_privacy(self):
        response = self.client.post(self.url, {'body': '', 'client_id': str(uuid.uuid4()), 'file': png()})
        self.assertEqual(response.status_code, 201, response.content)
        attachment = response.json()['item']['attachment']
        self.assertTrue(attachment['image'])
        shown = self.client.get(attachment['url'])
        self.assertEqual(shown['Content-Type'], 'image/png')
        self.assertIn('inline', shown['Content-Disposition'])
        release(shown)
        saved = self.client.get(attachment['url'], {'download': '1'})
        self.assertIn('attachment', saved['Content-Disposition'])
        release(saved)
        self.login(self.outsider)
        self.assertEqual(self.client.get(attachment['url']).status_code, 404)

    def test_bad_uploads_are_rejected(self):
        for upload in (SimpleUploadedFile('virus.exe', b'MZ'), SimpleUploadedFile('soxta.png', b'rasm emas')):
            response = self.client.post(self.url, {'body': 'x', 'client_id': str(uuid.uuid4()), 'file': upload})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.count(), 0)
        # SVG is allowed as a document but never rendered inline: it can carry scripts.
        svg = SimpleUploadedFile('chizma.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        item = self.client.post(self.url, {'body': '', 'client_id': str(uuid.uuid4()), 'file': svg}).json()['item']
        self.assertFalse(item['attachment']['image'])
        response = self.client.get(item['attachment']['url'])
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        release(response)

    def test_deleting_a_file_message_removes_the_stored_file(self):
        item_id = self.client.post(self.url, {'body': '', 'client_id': str(uuid.uuid4()), 'file': png()}).json()['item']['id']
        item = Message.objects.get(pk=item_id)
        storage, name = item.attachment.storage, item.attachment.name
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.delete(reverse('chat:message', args=[item_id]))
        self.assertFalse(storage.exists(name))

    def test_search_finds_only_this_conversation_and_around_loads_context(self):
        wanted = self.message(body='Shartnoma loyihasi')
        for number in range(30):
            self.send(body=f'Xabar {number}')
        Message.objects.create(sender=self.lead, recipient=self.dev, body='Shartnoma boshqa suhbatda')
        results = self.client.get(self.url, {'q': 'shartnoma'}).json()['results']
        self.assertEqual([row['id'] for row in results], [wanted.pk])
        self.assertEqual(self.client.get(self.url, {'q': 'x'}).status_code, 400)
        ids = [row['id'] for row in self.client.get(self.url, {'around': wanted.pk}).json()['items']]
        self.assertIn(wanted.pk, ids)

    def test_presence_and_typing_are_visible_only_to_the_target(self):
        self.post(reverse('chat:typing', args=[self.designer.pk]))
        peer = self.as_designer()['peer']
        self.assertTrue(peer['online'])
        self.assertTrue(peer['typing'])
        self.login(self.lead)
        self.assertFalse(self.client.get(reverse('chat:messages', args=[self.dev.pk])).json()['peer']['typing'])
        Presence.objects.filter(user=self.dev).update(last_seen=timezone.now() - timedelta(minutes=5),
                                                      typing_at=timezone.now() - timedelta(minutes=5))
        peer = self.as_designer()['peer']
        self.assertFalse(peer['online'])
        self.assertFalse(peer['typing'])

    def test_contacts_show_status_and_file_preview(self):
        self.client.post(self.url, {'body': '', 'client_id': str(uuid.uuid4()), 'file': png()})
        row = next(p for p in self.client.get(reverse('chat:contacts')).json()['items'] if p['id'] == self.designer.pk)
        self.assertEqual(row['last'], '🖼 Rasm')
        self.assertTrue(row['last_mine'])
        self.assertFalse(row['last_read'])

    def names(self, query):
        return [row['name'] for row in self.client.get(reverse('chat:contacts'), {'q': query}).json()['items']]

    def test_search_covers_the_whole_database(self):
        from apps.accounts.models import User
        self.founder.first_name, self.founder.last_name = 'Sardorbek', 'Soyibov'
        self.founder.save()
        self.designer.first_name, self.designer.last_name, self.designer.job_title = 'Ozod', 'G‘ulomov', 'Bosh dizayner'
        self.designer.status = User.Status.DEACTIVATED
        self.designer.save()
        self.assertIn('Sardorbek Soyibov', self.names('sardorbek soyibov'))
        self.assertIn('Sardorbek Soyibov', self.names('soyibov sardorbek'))
        self.assertIn('Sardorbek Soyibov', self.names('asoschi'))
        self.assertIn('Ozod G‘ulomov', self.names("g'ulomov"))
        self.assertIn('Ozod G‘ulomov', self.names('bosh dizayner'))
        self.assertEqual(self.names('mavjud-emas-odam'), [])
        self.assertNotIn(self.dev.display_name, self.names(self.dev.username))
        self.assertEqual(self.client.get(reverse('chat:conversation', args=[self.designer.pk])).status_code, 200)
        self.assertEqual(self.send().status_code, 400)

    def test_last_seen_uses_activity_anywhere_in_the_system(self):
        from apps.accounts.models import User
        moment = timezone.now() - timedelta(hours=3)
        User.objects.filter(pk=self.designer.pk).update(last_login=moment)
        peer = self.client.get(self.url).json()['peer']
        self.assertFalse(peer['online'])
        self.assertIsNotNone(peer['last_seen'])
        self.login(self.designer)
        self.client.get(reverse('enterprise:api_notifications'))
        self.login(self.dev)
        self.assertTrue(self.client.get(self.url).json()['peer']['online'])

    def test_only_the_founder_turns_the_badge_on_and_chat_shows_it(self):
        url = reverse('crm:employee_verify', args=[self.designer.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(self.client.post(reverse('crm:employee_verify', args=[self.dev.pk])).status_code, 403)
        self.login(self.founder)
        self.client.post(url)
        self.client.post(reverse('crm:employee_verify', args=[self.founder.pk]))
        self.login(self.dev)
        rows = {row['id']: row for row in self.client.get(reverse('chat:contacts')).json()['items']}
        self.assertTrue(rows[self.designer.pk]['verified'])
        self.assertTrue(rows[self.founder.pk]['verified'])
        self.assertFalse(rows[self.lead.pk]['verified'])
        self.assertContains(self.client.get(reverse('chat:conversation', args=[self.designer.pk])), 'chat-verified')
        self.login(self.founder)
        self.client.post(url)
        self.login(self.dev)
        self.assertFalse(self.client.get(self.url).json()['peer']['verified'])

    def test_screenshot_permission_reaches_the_page(self):
        from apps.accounts.forms import EmployeeForm
        self.assertIn('allow_screenshots', EmployeeForm(actor=self.founder).fields)
        self.assertNotContains(self.client.get(reverse('chat:index')), 'data-screenshots')
        type(self.dev).objects.filter(pk=self.dev.pk).update(allow_screenshots=False)
        page = self.client.get(reverse('chat:index'))
        self.assertContains(page, 'data-screenshots="blocked"')
        self.assertContains(page, 'capture-guard.js')
        desktop = self.client.get(reverse('chat:index'), HTTP_USER_AGENT='SSBDesktop/2.0.6')
        self.assertContains(desktop, 'data-screenshots="blocked"')
        self.assertNotContains(desktop, 'capture-guard.js')
        type(self.founder).objects.filter(pk=self.founder.pk).update(allow_screenshots=False)
        self.login(self.founder)
        self.assertNotContains(self.client.get(reverse('chat:index')), 'data-screenshots')
