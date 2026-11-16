from django.urls import reverse
from apps.core.testing import CompanyTestCase
from apps.website.models import TeamMember, PublicationStatus


class TeamCardsTests(CompanyTestCase):
    def test_director_creates_publishes_and_updates_public_card(self):
        director = self.make_user('director', 'Direktor')
        self.login(director)
        response = self.client.post(reverse('crm:cms_create', args=['team']), {
            'name': 'Ali Valiyev', 'public_title': 'Dasturchi', 'bio': 'Veb tizimlarni yaratadi.',
            'skills': 'Python, Django', 'order': 0,
        })
        self.assertEqual(response.status_code, 302)
        member = TeamMember.objects.get(name='Ali Valiyev')
        self.assertEqual(member.status, PublicationStatus.DRAFT)
        self.assertNotContains(self.client.get(reverse('website:home')), member.name)
        self.assertEqual(self.client.post(reverse('crm:cms_status', args=['team', member.pk]), {'action': 'publish'}).status_code, 302)
        response = self.client.get(reverse('website:home'))
        self.assertContains(response, member.name)
        self.assertContains(response, 'member-card')
        self.assertContains(response, member.bio)
        self.assertEqual(self.client.get(reverse('crm:cms_edit', args=['team', member.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('crm:cms_create', args=['services'])).status_code, 200)
        # Founder may restrict website rights while keeping team-card management.
        role=director.role
        role.capabilities=[cap for cap in role.capabilities if cap not in ['cms.edit','cms.publish']]
        role.save()
        self.assertEqual(self.client.get(reverse('crm:cms_create', args=['services'])).status_code,403)
        self.assertEqual(self.client.get(reverse('crm:cms_create', args=['team'])).status_code,200)

    def test_employee_cannot_manage_or_publish_team(self):
        member = TeamMember.objects.create(name='Ali Valiyev', public_title='Dasturchi')
        self.login(self.dev)
        self.assertEqual(self.client.get(reverse('crm:cms_create', args=['team'])).status_code, 403)
        self.assertEqual(self.client.post(reverse('crm:cms_status', args=['team', member.pk]), {'action': 'publish'}).status_code, 403)
        member.refresh_from_db()
        self.assertEqual(member.status, PublicationStatus.DRAFT)

    def test_publish_rejects_external_return_url(self):
        member = TeamMember.objects.create(name='Ali Valiyev', public_title='Dasturchi')
        self.login(self.founder)
        response = self.client.post(reverse('crm:cms_status', args=['team', member.pk]), {
            'action': 'publish', 'next': 'https://external.example/redirect',
        })
        self.assertRedirects(response, reverse('crm:cms_list', args=['team']))

    def test_publish_preserves_local_return_url(self):
        member = TeamMember.objects.create(name='Ali Valiyev', public_title='Dasturchi')
        self.login(self.founder)
        target = reverse('crm:cms_edit', args=['team', member.pk])
        response = self.client.post(reverse('crm:cms_status', args=['team', member.pk]), {
            'action': 'publish', 'next': target,
        })
        self.assertRedirects(response, target)
