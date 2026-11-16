import uuid
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.urls import reverse
from apps.core.testing import CompanyTestCase
from apps.accounts.models import User
from apps.enterprise import finance
from apps.enterprise.models import FinanceOperation, LedgerEntry, AgreementSnapshot, ApprovalRule


class FinancialTests(CompanyTestCase):
    def test_departed_employee_keeps_payable_and_can_receive_actual_payment(self):
        from apps.accounts.models import User
        from apps.enterprise.forms import OperationForm
        self.earned();self.dev.status=User.Status.DEACTIVATED;self.dev.save()
        self.assertFalse(self.dev.is_active)
        self.assertTrue(OperationForm(actor=self.founder).fields['employee'].queryset.filter(pk=self.dev.pk).exists())
        payout=self.operation('payment','2000000',employee=self.dev)
        finance.decide(self.founder,payout.pk,True,'Departed employee transfer verified')
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['payable'],Decimal('5000000'))
        self.login(self.founder)
        report=self.client.get(reverse('enterprise:reports'),{'report':'outstanding'})
        self.assertTrue(any(row[0]==self.dev.display_name and row[3]==Decimal('5000000') for row in report.context['rows']))
    def test_real_excel_pdf_exports_and_formula_safety(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from apps.enterprise.exports import export_report
        self.earned();self.login(self.founder)
        excel=self.client.get(reverse('enterprise:reports'),{'report':'earnings','export':'xlsx'})
        self.assertEqual(excel.status_code,200)
        book=load_workbook(BytesIO(excel.content));self.assertEqual(book.active.cell(2,2).value,7000000)
        pdf=self.client.get(reverse('enterprise:reports'),{'report':'earnings','export':'pdf'})
        self.assertTrue(pdf.content.startswith(b'%PDF-'))
        malicious=export_report('xlsx','safe',['Name'],[['=1+1']],'Safe export')
        self.assertNotEqual(load_workbook(BytesIO(malicious.content)).active.cell(2,1).data_type,'f')
        self.login(self.dev);self.assertEqual(self.client.get(reverse('enterprise:reports'),{'export':'xlsx'}).status_code,403)

    def test_company_defaults_only_affect_new_confirmed_agreements(self):
        from apps.core.models import WorkspaceSettings
        from apps.enterprise.forms import OperationForm
        self.earned();settings=WorkspaceSettings.load();settings.company_share_percent=35;settings.save()
        form=OperationForm(actor=self.founder);self.assertEqual(form.initial['company_percent'],35)
        self.assertEqual(AgreementSnapshot.objects.first().company_percent,30)
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['earned'],Decimal('7000000'))

    def test_project_cancellation_keeps_all_financial_history(self):
        from apps.crm.services import transition_project,WorkflowError
        self.earned()
        with self.assertRaises(WorkflowError):transition_project(self.founder,self.project,'cancelled','')
        transition_project(self.founder,self.project,'cancelled','Client cancelled the project')
        self.assertEqual(self.project.status,'cancelled')
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['earned'],Decimal('7000000'))
        self.assertEqual(self.project.ledger_entries.count(),2)
    def test_http_payment_request_approval_and_private_balance(self):
        self.earned();self.login(self.ceo)
        response=self.client.post(reverse('enterprise:finance'),{'kind':'payment','amount':'2000000','currency':'UZS',
            'employee':self.dev.pk,'project':self.project.pk,'description':'Bank transfer document HTTP journey','idempotency_key':str(uuid.uuid4())})
        self.assertEqual(response.status_code,302)
        payment=FinanceOperation.objects.get(kind='payment')
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['paid'],0)
        self.assertEqual(self.client.post(reverse('enterprise:decision',args=[payment.pk]),{'decision':'approve','reason':'Only the founder approves'}).status_code,403)
        self.login(self.founder)
        self.assertEqual(self.client.post(reverse('enterprise:decision',args=[payment.pk]),{'decision':'approve','reason':'Transfer document checked'}).status_code,302)
        self.login(self.dev);response=self.client.get(reverse('enterprise:balance'))
        self.assertEqual(response.context['balance']['payable'],Decimal('5000000'))

    def test_ledger_filters_pagination_and_chart_use_real_sources(self):
        self.earned()
        for index in range(35):self.operation('receipt','100',project=self.project)
        self.login(self.founder)
        response=self.client.get(reverse('enterprise:finance'),{'category':'receipt','order':'oldest','q':'Bank','page':2})
        self.assertEqual(response.context['page'].paginator.count,36)
        self.assertEqual(len(response.context['entries']),6)
        self.assertTrue(all(entry.category=='receipt' for entry in response.context['entries']))
        # A display filter must not reduce the actual company balance.
        self.assertEqual(response.context['summary']['client_receipts'],Decimal('10003500'))
        report=self.client.get(reverse('enterprise:reports'),{'report':'daily'})
        self.assertEqual(sum(point['amount'] for point in report.context['chart']),Decimal('10003500'))
        import os
        if os.environ.get('SSB_CAPTURE_REPLACEMENT'):
            from django.conf import settings
            (settings.BASE_DIR/'.setup/finance-chart.html').write_bytes(report.content)
    def operation(self,kind,amount,**kwargs):
        return finance.request_operation(self.ceo,kind=kind,amount=amount,currency='UZS',description='Bank hujjati test manbasi',idempotency_key=kwargs.pop('key',uuid.uuid4()),**kwargs)

    def agreement(self,percent='70',amount='10000000'):
        item=self.operation('agreement',amount,project=self.project,payload={'company_percent':str(100-Decimal(percent)),'shares':[{'employee':self.dev.pk,'percent':percent}]})
        finance.decide(self.founder,item.pk,True,'Kelishuv tekshirildi')
        return item

    def earned(self):
        self.agreement();return self.operation('receipt','10000000',project=self.project)

    def test_example_earned_is_not_paid(self):
        self.earned();balance=finance.employee_balance(self.dev,'UZS')
        self.assertEqual(balance['earned'],Decimal('7000000'));self.assertEqual(balance['paid'],0)
        payment=self.operation('payment','2000000',employee=self.dev,project=self.project)
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['paid'],0)
        finance.decide(self.founder,payment.pk,True,'To‘lov hujjati tekshirildi')
        balance=finance.employee_balance(self.dev,'UZS')
        self.assertEqual(balance['earned'],Decimal('7000000'));self.assertEqual(balance['paid'],Decimal('2000000'));self.assertEqual(balance['payable'],Decimal('5000000'))
        self.assertEqual(finance.profitability(self.project)['net_profit'],Decimal('3000000'))

    def test_only_founder_decides_and_founder_requests_post_at_once(self):
        item=self.operation('bonus','100',employee=self.dev)
        self.assertEqual(item.status,'pending')
        with self.assertRaises(PermissionDenied):finance.decide(self.ceo,item.pk,True,'Tasdiqlash sababi')
        finance.decide(self.founder,item.pk,True,'Asoschi tasdiqladi');item.refresh_from_db()
        self.assertEqual(item.status,'approved')
        own=finance.request_operation(self.founder,kind='bonus',amount='50',currency='UZS',description='Asoschi mukofoti',idempotency_key=uuid.uuid4(),employee=self.dev)
        self.assertEqual(own.status,'approved')

    def test_idempotency_returns_same_operation_and_rejects_changed_intent(self):
        key=uuid.uuid4();item=self.operation('salary','100',employee=self.dev,key=key)
        duplicate=self.operation('salary','100',employee=self.dev,key=key)
        self.assertEqual(item.pk,duplicate.pk)
        with self.assertRaises(ValidationError):self.operation('salary','200',employee=self.dev,key=key)

    def test_snapshots_and_future_rules_do_not_change_earned_money(self):
        self.earned();self.agreement('50');self.assertEqual(finance.employee_balance(self.dev,'UZS')['earned'],Decimal('7000000'))
        self.operation('receipt','2000000',project=self.project)
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['earned'],Decimal('8000000'))
        self.assertEqual(AgreementSnapshot.objects.filter(project=self.project).count(),2)

    def test_correction_is_append_only_and_reverses_related_shares(self):
        receipt=self.earned();entry=receipt.entries.get(category='receipt')
        item=self.operation('correction','1000000',payload={'entry_id':str(entry.pk)})
        finance.decide(self.founder,item.pk,True,'Bank tushumi qisman qaytarildi')
        entry.refresh_from_db();self.assertEqual(entry.amount,Decimal('10000000'))
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['earned'],Decimal('6300000'))
        self.assertEqual(finance.company_summary(LedgerEntry.objects.all(),'UZS')['company_revenue'],Decimal('2700000'))
        with self.assertRaises(ValueError):LedgerEntry.objects.filter(pk=entry.pk).update(amount=1)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:cursor.execute('DELETE FROM enterprise_ledgerentry WHERE id=%s',[entry.pk])

    def test_overpayment_rejected_without_partial_post(self):
        self.earned();payment=self.operation('payment','7000001',employee=self.dev)
        with self.assertRaises(ValidationError):finance.decide(self.founder,payment.pk,True,'To‘lov tekshirildi')
        self.assertEqual(payment.entries.count(),0)
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['paid'],0)

    def test_rules_frozen_on_request_and_currencies_separate(self):
        item=self.operation('bonus','100',employee=self.dev)
        ApprovalRule.objects.create(kind='bonus',currency='UZS',threshold=0,approvals=3,updated_by=self.founder)
        finance.decide(self.founder,item.pk,True,'Qoidaning oldingi nusxasi')
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['earned'],100)
        self.assertEqual(finance.employee_balance(self.dev,'USD')['earned'],0)

    def test_employee_financial_privacy_and_api(self):
        self.earned();self.login(self.designer)
        entry=LedgerEntry.objects.filter(employee=self.dev).first()
        self.assertEqual(self.client.get(reverse('enterprise:entry',args=[entry.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('enterprise:api_ledger')).json(),[])
        self.assertEqual(self.client.get(reverse('enterprise:reports')).status_code,403)
        self.login(self.dev);response=self.client.get(reverse('enterprise:api_ledger'))
        self.assertTrue(all(item['employee']==self.dev.pk for item in response.json()))

    def test_operation_intent_cannot_be_overwritten(self):
        item=self.operation('salary','100',employee=self.dev)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():FinanceOperation.objects.filter(pk=item.pk).update(amount=200)

    def test_bad_distribution_and_decimal_precision_rejected(self):
        with self.assertRaises(ValidationError):self.agreement('120')
        with self.assertRaises(ValidationError):self.operation('salary','1.001',employee=self.dev)
        with self.assertRaises(ValidationError):self.operation('salary','NaN',employee=self.dev)

    def test_unallocated_payment_cannot_be_paid_again_through_project(self):
        self.earned()
        payment=self.operation('payment','6000000',employee=self.dev)
        finance.decide(self.founder,payment.pk,True,'Umumiy hisobdan to‘landi')
        duplicate=self.operation('payment','2000000',employee=self.dev,project=self.project)
        with self.assertRaises(ValidationError):finance.decide(self.founder,duplicate.pk,True,'Loyiha bo‘yicha tekshiruv')
        self.assertEqual(finance.employee_balance(self.dev,'UZS')['payable'],Decimal('1000000'))
