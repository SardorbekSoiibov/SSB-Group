from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from apps.enterprise import performance_system as system


class Command(BaseCommand):
    help = 'Tugagan haftani yopadi: SSB AI tahlili, rahbar bahosi, reyting va “eng faol xodim” e’loni. Qayta ishga tushirish xavfsiz.'

    def add_arguments(self, parser):
        parser.add_argument('--actor', help='Eski moslik uchun; endi talab qilinmaydi')
        parser.add_argument('--week', help='Tugagan hafta dushanbasi, YYYY-MM-DD; standart: o‘tgan hafta')

    def handle(self, *args, **options):
        try:
            start = parse_date(options['week']) if options.get('week') else system.due_week()
            if not start:
                raise ValueError
            week = system.close_week(start)
        except (ValueError, ValidationError) as error:
            raise CommandError(str(error) or 'Sana noto‘g‘ri.')
        if week is None:
            self.stdout.write(f'Hafta {start}: qabul qilingan vazifa yo‘q, reyting chiqarilmadi.')
        else:
            self.stdout.write(f'Hafta {week.starts_on}: {week.evaluations.count()} xodim, e’lon: {week.published_at:%d.%m.%Y %H:%M}.')
