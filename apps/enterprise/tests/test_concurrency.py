import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from django.test import TransactionTestCase
from django.db import close_old_connections, connection
from django.core.exceptions import ValidationError
from apps.accounts.models import Role, User, Capability
from apps.crm.models import Project
from apps.enterprise import finance


class FinancialConcurrencyTests(TransactionTestCase):
    def test_two_simultaneous_payments_cannot_overdraw_employee(self):
        owner_role=Role.objects.create(name='Owner concurrency',rank=0,is_owner=True,dashboard='founder')
        approver_role=Role.objects.create(name='Approver concurrency',rank=10,capabilities=Capability.values)
        employee_role=Role.objects.create(name='Employee concurrency',rank=60)
        owner=User.objects.create(username='owner_concurrency',role=owner_role)
        approver=User.objects.create(username='approver_concurrency',role=approver_role)
        employee=User.objects.create(username='employee_concurrency',role=employee_role)
        project=Project.objects.create(name='Concurrent project',manager=owner)
        project.members.add(employee)
        def request(kind,amount,**extra):
            return finance.request_operation(approver,kind=kind,amount=amount,currency='UZS',description='Concurrent payment source',idempotency_key=uuid.uuid4(),**extra)
        agreement=request('agreement','10000000',project=project,payload={'company_percent':'30','shares':[{'employee':employee.pk,'percent':'70'}]})
        finance.decide(owner,agreement.pk,True,'Agreement verified')
        request('receipt','10000000',project=project)
        first=request('payment','4000000',employee=employee)
        second=request('payment','4000000',employee=employee)
        def approve(pk):
            close_old_connections()
            try:
                finance.decide(User.objects.get(pk=owner.pk),pk,True,'Bank payment verified')
                return True
            except ValidationError:
                return False
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(approve,[first.pk,second.pk]))
        self.assertEqual(sum(results),1)
        balance=finance.employee_balance(employee,'UZS')
        self.assertEqual(balance['paid'],Decimal('4000000'))
        self.assertEqual(balance['payable'],Decimal('3000000'))
