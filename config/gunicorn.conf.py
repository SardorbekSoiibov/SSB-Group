"""Gunicorn sozlamalari (production).

Ishga tushirish:  gunicorn config.wsgi -c config/gunicorn.conf.py
Har bir ishchi jarayon `threads` ta so'rovni parallel bajaradi. Bazaga ulanishlar soni
taxminan workers × threads bo'ladi — PostgreSQL `max_connections` undan katta bo'lsin.
"""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", 4))
keepalive = 5
timeout = 30
graceful_timeout = 30
# Uzoq ishlagan jarayonlar xotirasi o'smasligi uchun vaqti-vaqti bilan yangilanadi.
max_requests = 2000
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
