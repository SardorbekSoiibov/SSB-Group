"""Private, compressed logical backup with checksum; prefer pg_dump when installed."""
import gzip
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from django.conf import settings
from django.core.management import BaseCommand, call_command, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = 'Create a private database backup. No credentials are printed.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--format', choices=['json','pgdump'], default='json')

    def handle(self, *args, **options):
        destination=Path(options['output']).resolve()
        for public in [Path(settings.MEDIA_ROOT).resolve(),(settings.BASE_DIR/'static').resolve(),Path(settings.STATIC_ROOT).resolve()]:
            if destination.is_relative_to(public):raise CommandError('Backups cannot be saved in a public media/static directory.')
        if destination.exists():raise CommandError('Backup file already exists; refusing to overwrite.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix(destination.suffix+'.partial')
        if temporary.exists():raise CommandError('A partial backup exists; inspect it before retrying.')
        try:
            if options['format']=='pgdump':
                executable=shutil.which('pg_dump')
                if not executable:raise CommandError('pg_dump is not installed. Install matching PostgreSQL client tools, or use --format json.')
                database=settings.DATABASES['default'];environment=os.environ.copy()
                environment['PGPASSWORD']=str(database.get('PASSWORD',''))
                command=[executable,'--format=custom','--no-owner','--file',str(temporary),'-h',database.get('HOST') or 'localhost','-p',str(database.get('PORT') or 5432),'-U',database.get('USER') or 'postgres',database['NAME']]
                result=subprocess.run(command,env=environment,capture_output=True,timeout=600)
                if result.returncode:raise CommandError('pg_dump failed. Check database connectivity and permissions.')
            else:
                with transaction.atomic():
                    from django.db import connection
                    with connection.cursor() as cursor:cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                    with gzip.open(temporary,'wt',encoding='utf-8') as output:
                        call_command('dumpdata',use_natural_foreign_keys=True,use_natural_primary_keys=True,stdout=output)
            temporary.replace(destination)
            digest=hashlib.sha256()
            with destination.open('rb') as source:
                for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
            destination.with_suffix(destination.suffix+'.sha256').write_text(digest.hexdigest()+'  '+destination.name+'\n',encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'Backup created: {destination.name}; SHA-256: {digest.hexdigest()}'))
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
