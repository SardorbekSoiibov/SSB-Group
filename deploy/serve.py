"""Production web server for Windows (waitress). Started by deploy/start.bat, stopped by deploy/stop.bat.

Cloudflare Tunnel (cloudflared) connects from this same computer, so 127.0.0.1 is the only trusted proxy:
waitress takes the real visitor IP and https scheme from its X-Forwarded-* headers and ignores them from anyone else.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from waitress import serve  # noqa: E402

from config.wsgi import application  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("SSB_PORT", "8080"))
    print(f"SSB Group server: http://127.0.0.1:{port}", flush=True)
    # Haftalik reyting: har dushanba 00:00 da o'tgan haftani yopib, eng faol xodimni e'lon qiladi.
    from apps.enterprise.performance_system import start_scheduler
    start_scheduler()
    # Telegram bot (admin panel, kanallarga post) va bildirishnomalarni yuborish server bilan birga ishlaydi.
    from apps.notifications.runtime import start_worker
    start_worker()
    serve(
        application,
        host="127.0.0.1",
        port=port,
        threads=int(os.environ.get("SSB_THREADS", "8")),
        trusted_proxy="127.0.0.1",
        trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
        clear_untrusted_proxy_headers=True,
        max_request_body_size=60 * 1024 * 1024,
        ident="SSB",
    )
