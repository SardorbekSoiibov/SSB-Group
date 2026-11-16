"""One Enterprise dashboard for every role, with the existing business modules intact."""
import json
import os
from html.parser import HTMLParser

from django.conf import settings
from django.core.cache import cache
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import NoReverseMatch, resolve, reverse

from apps.core.dates import parse_filter_date
from apps.core.testing import CompanyTestCase, PASSWORD
from apps.enterprise.insights import allowed_widgets
from apps.enterprise.models import DashboardLayout


class SidebarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_aside=False
        self.in_nav=False
        self.links=[]

    def handle_starttag(self,tag,attrs):
        if tag=='aside':self.in_aside=True
        if tag=='nav' and self.in_aside:self.in_nav=True
        if tag=='a' and self.in_aside and self.in_nav:
            data=dict(attrs)
            if data.get('href','').startswith('/management/'):
                self.links.append(data)

    def handle_endtag(self,tag):
        if tag=='nav':self.in_nav=False
        if tag=='aside':self.in_aside=False


class UnifiedDashboardTests(CompanyTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.director=cls.make_user('director','Direktor')

    def test_legacy_entry_redirects_to_one_canonical_page(self):
        self.login(self.founder)
        self.assertRedirects(self.client.get('/management/'),reverse('enterprise:overview'),status_code=301)
        self.assertEqual(resolve(reverse('enterprise:overview')).view_name,'enterprise:overview')
        with self.assertRaises(NoReverseMatch):reverse('crm:dashboard')
        with self.assertRaises(TemplateDoesNotExist):get_template('crm/dashboard.html')
        self.assertFalse((settings.BASE_DIR/'apps/crm/dashboard.py').exists())
        for old_template in ['enterprise/base.html','enterprise/overview.html','base_crm.html']:
            with self.assertRaises(TemplateDoesNotExist):get_template(old_template)
        for url in ['/management/dashboard/','/management/old-dashboard/','/management/enterprise/dashboard/']:
            self.assertEqual(self.client.get(url).status_code,404,url)

    def test_login_uses_enterprise_for_all_roles_including_modal(self):
        for user in [self.founder,self.cofounder,self.director,self.ceo,self.lead,self.dev]:
            self.client.logout();cache.clear()
            response=self.client.post(reverse('accounts:login'),{'username':user.username,'password':PASSWORD})
            self.assertRedirects(response,reverse('enterprise:overview'))
            self.client.logout();cache.clear()
            response=self.client.post(reverse('accounts:login'),{'username':user.username,'password':PASSWORD},HTTP_X_SSB_MODAL='1')
            self.assertEqual(response.json()['redirect'],reverse('enterprise:overview'))

    def test_role_dashboard_and_sidebar_share_only_enterprise_layout(self):
        for user in [self.founder,self.cofounder,self.director,self.ceo,self.lead,self.dev]:
            self.login(user)
            response=self.client.get(reverse('enterprise:overview'))
            self.assertEqual(response.status_code,200)
            self.assertIn('no-store',response['Cache-Control'])
            self.assertTemplateUsed(response,'boshqaruv/dashboards/'+{'founder':'founder','cofounder':'cofounder','management':'director','employee':'employee'}[user.dashboard_kind]+'.html')
            self.assertTemplateUsed(response,'boshqaruv/base.html')
            self.assertContains(response,'data-app="boshqaruv-v2"')
            self.assertNotContains(response,'workspace.css')
            self.assertNotContains(response,'enterprise-shell.js')
            self.assertEqual(response.context['dashboard_kind'],user.dashboard_kind)
            self.assertEqual(response.context['available'],allowed_widgets(user))
            self.assertContains(response,'data-dashboard-kind="'+user.dashboard_kind+'"')
            self.assertNotContains(response,'dashboard-page')
            parser=SidebarParser();parser.feed(response.content.decode())
            self.assertEqual(sum(link['href']==reverse('enterprise:overview') for link in parser.links),1)
            self.assertEqual(sum('aria-current' in link for link in parser.links),1)
            for link in parser.links:
                target=resolve(link['href'])
                self.assertIsNotNone(target.func)
                page=self.client.get(link['href'])
                self.assertEqual(page.status_code,200,(user.username,link['href'],page.status_code))
            if os.environ.get('SSB_CAPTURE_REPLACEMENT'):
                root=settings.BASE_DIR/'.setup/dashboard-replacement';root.mkdir(parents=True,exist_ok=True)
                (root/f'{user.username}.html').write_bytes(response.content)

    def test_saved_widget_order_size_and_visibility_survive_dashboard_entry(self):
        self.login(self.founder)
        layout=[{'key':'finance','size':'wide'},{'key':'projects','size':'normal'}]
        response=self.client.post(reverse('enterprise:layout'),{'layout':json.dumps(layout)})
        self.assertRedirects(response,reverse('enterprise:overview'))
        self.assertEqual(DashboardLayout.objects.get(user=self.founder).widgets,layout)
        response=self.client.get('/management/',follow=True)
        self.assertEqual(response.context['selected'],layout)
        rows=response.context['widgets']
        self.assertEqual([row['key'] for row in rows if row['enabled']],['finance','projects'])
        self.assertEqual(rows[0]['size'],'wide')
        self.login(self.dev)
        self.assertNotIn('finance',self.client.get(reverse('enterprise:overview')).context['available'])

    def test_only_current_sidebar_section_is_active(self):
        self.login(self.founder)
        for name in ['overview','finance','balance','rules','schedule','archives','performance','reports','desktop']:
            response=self.client.get(reverse('enterprise:'+name))
            parser=SidebarParser();parser.feed(response.content.decode())
            self.assertEqual(sum('aria-current' in link for link in parser.links),1,name)

    def test_shared_filters_do_not_depend_on_removed_dashboard(self):
        self.assertIsNone(parse_filter_date('2026-02-30'))
        self.assertIsNone(parse_filter_date('invalid'))
        self.assertEqual(parse_filter_date('2026-01-01').isoformat(),'2026-01-01')
        self.login(self.founder)
        for name in ['crm:audit','crm:projects','crm:tasks','crm:profile']:
            self.assertEqual(self.client.get(reverse(name)).status_code,200,name)
