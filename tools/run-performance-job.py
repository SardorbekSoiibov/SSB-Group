"""Windowless Scheduled Task entry point, with a local diagnostic log."""
import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.chdir(root)
sys.path.insert(0, str(root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
(root / '.setup').mkdir(exist_ok=True)
with (root / '.setup' / 'weekly-performance-job.log').open('a', encoding='utf-8', buffering=1) as log:
    sys.stdout = sys.stderr = log
    parser = argparse.ArgumentParser()
    parser.add_argument('--actor', required=True)
    options = parser.parse_args()
    try:
        import django
        django.setup()
        from django.core.management import call_command
        print(datetime.now().isoformat(), 'weekly performance job')
        call_command('process_weekly_performance', actor=options.actor)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
