import csv
from datetime import datetime
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch
import uuid

from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.core.testing import CompanyTestCase
from apps.crm.models import Project
from apps.enterprise import finance
from apps.enterprise.exports import export_report
from apps.enterprise.models import LedgerEntry


class FinancialReportTests(CompanyTestCase):
    def operation(self, day, kind, amount, *, approve=True, **kwargs):
        at = timezone.make_aware(datetime(2026, 1, day, 12))
        with patch('django.utils.timezone.now', return_value=at):
            item = finance.request_operation(self.ceo, kind=kind, amount=amount,
                currency=kwargs.pop('currency', 'UZS'), description='Verified bank document',
                idempotency_key=uuid.uuid4(), **kwargs)
            if item.status == 'pending' and approve:
                finance.decide(self.founder, item.pk, True, 'Founder review of bank document')
        return item

    def dataset(self):
        self.operation(5, 'agreement', '10000000', project=self.project,
            payload={'company_percent':'30','shares':[{'employee':self.dev.pk,'percent':'70'}]})
        receipt = self.operation(6, 'receipt', '10000000', project=self.project)
        self.operation(7, 'salary', '1000000', employee=self.dev, project=self.project)
        self.operation(7, 'bonus', '500000', employee=self.dev, project=self.project)
        self.operation(8, 'payment', '2000000', employee=self.dev, project=self.project)
        self.operation(9, 'expense', '250000', project=self.project)
        self.operation(10, 'bonus', '999999', employee=self.dev, project=self.project, approve=False)
        original = receipt.entries.get(category='receipt')
        self.operation(11, 'correction', '1000000', payload={'entry_id':str(original.pk)})
        other = Project.objects.create(name='Dollar project', manager=self.lead, created_by=self.founder)
        other.members.add(self.dev)
        self.operation(5,'agreement','1000',currency='USD',project=other,
            payload={'company_percent':'30','shares':[{'employee':self.dev.pk,'percent':'70'}]})
        self.operation(6,'receipt','1000',currency='USD',project=other)
        self.login(self.founder)

    def report(self, name, **kwargs):
        return self.client.get(reverse('enterprise:reports'),
            {'report':name,'dan':'2026-01-01','gacha':'2026-01-31','currency':'UZS',**kwargs})

    def test_all_money_reports_match_actual_ledger_including_corrections(self):
        self.dataset()
        for name in ['daily','weekly','monthly','annual']:
            response = self.report(name)
            self.assertEqual(response.status_code,200)
            self.assertEqual(sum(row[1] for row in response.context['rows']),Decimal('9000000'))
        expected = {'expenses':'1750000','earnings':'7800000','bonuses':'500000',
                    'payouts':'2000000','departments':'7800000'}
        for name, amount in expected.items():
            response = self.report(name)
            self.assertEqual(sum(row[1] for row in response.context['rows']),Decimal(amount),name)
        rows = self.report('profit').context['rows']
        self.assertEqual([row[1] for row in rows],[Decimal('2700000'),Decimal('1750000'),Decimal('950000')])
        rows = self.report('outstanding').context['rows']
        self.assertEqual(rows[0][1:],[Decimal('7800000'),Decimal('2000000'),Decimal('5800000')])
        rows = self.report('profitability').context['rows']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][1:],[Decimal(value) for value in
            ['9000000','6300000','2700000','1750000','950000','1000000','5800000']])

    def test_as_of_end_date_excludes_future_payments_and_agreements(self):
        self.dataset()
        self.assertEqual(self.report('outstanding',gacha='2026-01-06').context['rows'][0][3],Decimal('7000000'))
        rows = self.report('profitability',gacha='2026-01-06').context['rows']
        self.assertEqual(rows[0][1:],[Decimal(value) for value in ['10000000','7000000','3000000','0','3000000','0','7000000']])
        self.assertEqual(self.report('profitability',gacha='2026-01-04').context['rows'],[])

    def test_filters_project_employee_role_and_currency(self):
        self.dataset()
        for name, value in [('project',self.project.pk),('employee',self.dev.pk),('position',self.dev.role_id)]:
            response = self.report('monthly',**{name:value})
            self.assertEqual(sum(row[1] for row in response.context['rows']),Decimal('9000000'),name)
        self.assertEqual(self.report('earnings',employee=self.designer.pk).context['rows'],[])
        usd = self.report('monthly',currency='USD')
        self.assertEqual(sum(row[1] for row in usd.context['rows']),Decimal('1000'))
        self.assertEqual(self.report('monthly',dan='2026-02-01',gacha='2026-02-28').context['rows'],[])

    def test_bad_filters_show_errors_and_never_export_wrong_period(self):
        self.login(self.founder)
        for values in [{'dan':'2026-02-31'},{'gacha':'not-a-date'}, {'dan':'2026-02-01','gacha':'2026-01-01'},
                       {'currency':'XXX'}, {'report':'unknown'}, {'export':'exe'}]:
            response = self.report('monthly',**values)
            self.assertEqual(response.status_code,400)
            self.assertContains(response,'role="alert"',status_code=400)
            self.assertNotIn('Content-Disposition',response)

    def test_all_three_exports_match_page_rows_and_are_private(self):
        self.dataset()
        expected = self.report('earnings').context['rows']
        csv_response = self.report('earnings',export='csv')
        parsed = list(csv.reader(StringIO(csv_response.content.decode('utf-8-sig'))))
        self.assertEqual(Decimal(parsed[1][1]),expected[0][1])
        excel = self.report('earnings',export='xlsx')
        book = load_workbook(BytesIO(excel.content))
        self.assertEqual(Decimal(str(book.active.cell(2,2).value)),expected[0][1])
        pdf = self.report('earnings',export='pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        for response in [csv_response,excel,pdf]:
            self.assertIn('no-store',response['Cache-Control'])
            self.assertIn('attachment',response['Content-Disposition'])

    def test_excel_preserves_large_decimal_exactly_and_neutralizes_formulas(self):
        amount = Decimal('12345678901234567.89')
        response = export_report('xlsx','precision',['Name','Amount'],[['=HYPERLINK("https://example.com")',amount]],'Precision')
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet.cell(2,2).value,str(amount))
        self.assertNotEqual(sheet.cell(2,1).data_type,'f')

    def test_report_privacy_empty_state_and_no_financial_mutation(self):
        self.login(self.dev)
        for kind in ['', 'csv','xlsx','pdf']:
            self.assertEqual(self.report('monthly',export=kind).status_code,403)
        self.login(self.founder)
        before = LedgerEntry.objects.count()
        response = self.report('monthly')
        self.assertEqual(response.context['rows'],[])
        self.assertContains(response,'tasdiqlangan')
        self.assertEqual(LedgerEntry.objects.count(),before)

    def test_posting_day_uses_tashkent_midnight_not_utc_day(self):
        self.operation(5,'agreement','10000000',project=self.project,
            payload={'company_percent':'30','shares':[{'employee':self.dev.pk,'percent':'70'}]})
        midnight=timezone.make_aware(datetime(2026,1,7,0,10))
        with patch('django.utils.timezone.now',return_value=midnight):
            finance.request_operation(self.founder,kind='receipt',amount='10000000',currency='UZS',
                project=self.project,description='Tashkent midnight bank receipt',idempotency_key=uuid.uuid4())
        self.login(self.founder)
        self.assertEqual(self.report('daily',dan='2026-01-07',gacha='2026-01-07').context['rows'][0][0],'2026-01-07')
        self.assertEqual(self.report('daily',dan='2026-01-06',gacha='2026-01-06').context['rows'],[])
