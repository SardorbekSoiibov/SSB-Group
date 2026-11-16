# SSB Group — korporativ sayt + boshqaruv tizimi (CRM)

Bitta Django loyihasi, bitta PostgreSQL bazasi:

- **Ommaviy sayt** (`/`) — bosh sahifa (interaktiv 3D hero), biz haqimizda, xizmatlar, portfolio, jamoa, loyiha murojaati formasi, maxfiylik siyosati, sitemap, robots.txt.
- **SSB Management** (`/management/`) — rolga qarab ishlaydigan dashboardlar, xodimlar, rollar va huquqlar, loyihalar (ro'yxat, kanban, taqvim, yuklama), vazifalar (topshirish → ko'rib chiqish → qabul), mijozlar va murojaatlar, sayt kontenti (CMS), e'lonlar, bildirishnomalar, hisobotlar (CSV), sozlamalar, audit jurnali.

Texnologiyalar: Python 3.11+, Django 5.2, PostgreSQL, Django shablonlari, Tailwind CSS 4, Alpine.js, HTMX, Three.js.

---

## 1. O'rnatish (lokal)

Kerak: Python 3.11+, PostgreSQL 14+, Node.js 18+ (faqat CSS qayta yig'ish uchun).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env        # Linux/macOS: cp .env.example .env
# .env ichida DJANGO_SECRET_KEY va DATABASE_URL ni to'ldiring
```

PostgreSQL'da baza yarating:

```sql
CREATE USER ssb WITH PASSWORD 'ssb_password';
CREATE DATABASE ssb OWNER ssb;
```

### PostgreSQL tizimda bo'lmasa (Windows, lokal)

Loyiha `ArrayField` ishlatgani uchun SQLite islamaydi — PostgreSQL shart. Server o'rnatilmasa, portable build bilan ishga tushirish mumkin:

```powershell
# 1) Portable binarlar: zonky embedded-postgres jar ichidagi txz arxivini
#    loyiha ichidagi .pg\ papkasiga chiqaring (initdb, pg_ctl, postgres yetarli).
# 2) Klaster (.pgdata) bir marta yaratiladi:
.\.pg\bin\initdb.exe -D .\.pgdata -U ssb -A trust --encoding=UTF8 -E UTF8
#    so'ng .pgdata\postgresql.conf da portni 5433 qiling va listen_addresses = '127.0.0.1'
# 3) Har safar ishga tushirishda:
.\.pg\bin\pg_ctl.exe -D .\.pgdata -l .pgdata\server.log start
# 4) Baza bir marta: postgres db'iga ulinib CREATE DATABASE ssb OWNER ssb;
# 5) .env: DATABASE_URL=postgres://ssb:ssb_password@127.0.0.1:5433/ssb
```

`.pg\` va `.pgdata\` gitignore'da — ularni commit qilmang. To'xtatish: `pg_ctl -D .pgdata stop`.

Keyin:

```bash
python manage.py migrate
python manage.py bootstrap_company --username asoschi --first-name Ism --last-name Familiya --email siz@ssbgroup.uz
python manage.py seed_site          # tahrirlanadigan boshlang'ich sayt matnlari (ixtiyoriy)
python manage.py runserver
```

- Sayt: http://localhost:8000
- Boshqaruv: http://localhost:8000/management/

`bootstrap_company` standart rollarni (Asoschi, Hammuassis, CEO, Direktor, Team Lead, Kontent menejeri, Xodim), bo'limlarni va **asoschi hisobini** yaratadi. Parolni xavfsiz so'raydi; avtomatlashtirilgan o'rnatishda `--no-input` va `SSB_FOUNDER_PASSWORD` muhit o'zgaruvchisidan foydalaning. Buyruqni qayta ishga tushirish xavfsiz.

Windows'dagi `start.bat` birinchi ishga tushganda rahbar hisobini yaratadi: login `ssbgroup`. Parol `SSB_FOUNDER_PASSWORD` muhit o'zgaruvchisidan olinadi; u berilmagan bo'lsa, skript parolni terminalda so'raydi. Qolgan xodimlar hisoblarini rahbar CRM → «Xodimlar» bo'limida ochadi. Sayt internetga chiqishidan oldin parolni CRM'dagi profil sahifasida almashtiring.

### Demo ma'lumotlar (faqat sinash uchun)

```bash
python manage.py seed_demo
```

Faqat `DJANGO_DEBUG=True` bo'lsa ishlaydi. Namuna xodimlar (`dilnoza`, `jasur`, `aziza`, `bekzod`, `madina`, `sardor`, `nilufar`; parol: `demo-parol-2026`), mijoz, murojaatlar, loyihalar, vazifalar va 2 ta «Namuna» portfolio yozuvini yaratadi. **Ishga tushirishdan oldin bazani tozalang** — bu yerda haqiqiy mijoz yoki natija yo'q.

---

## 2. Muhit o'zgaruvchilari (`.env`)

| O'zgaruvchi | Vazifasi |
|---|---|
| `DJANGO_SECRET_KEY` | **Majburiy.** Uzun tasodifiy satr. |
| `DJANGO_DEBUG` | `True` faqat lokalda. Production'da `False`. |
| `DATABASE_URL` | `postgres://user:parol@host:5432/ssb` |
| `DJANGO_ALLOWED_HOSTS` | Vergul bilan: `ssbgroup.uz,www.ssbgroup.uz` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://ssbgroup.uz,https://www.ssbgroup.uz` |
| `SITE_URL` | Sitemap va robots.txt uchun: `https://ssbgroup.uz` |
| `CACHE_URL` | Production'da Redis: `redis://127.0.0.1:6379/1` (rate limit hamma worker'larda umumiy bo'lishi uchun). |
| `MEDIA_ROOT` | Ommaviy rasmlar (portfolio, jamoa). Veb-server to'g'ridan-to'g'ri beradi. |
| `PRIVATE_MEDIA_ROOT` | Vazifa fayllari va xodim rasmlari. **Hech qachon veb-server orqali ochmang** — faqat ruxsat tekshiradigan view'lar beradi. |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | Parolni tiklash xatlari uchun SMTP. Sozlanmasa, xatlar konsolga yoziladi. |
| `DJANGO_BEHIND_PROXY` | Nginx orqasida `True` (X-Forwarded-Proto). |
| `LOG_LEVEL` | `INFO` (standart). |

---

## 3. Testlar

```bash
python manage.py test apps
```

54 ta test: kirish/chiqish va rate limit, rollar va huquqlarni oshirib olishning oldini olish, xodimni taklif qilish va o'chirish, loyiha va vazifa holatlari, ish topshirish va tasdiqlash, bog'liq vazifalar, fayl cheklovlari va maxfiy fayllar, murojaat formasi (validatsiya, honeypot, rate limit), murojaat → loyiha → yakunlash → portfolio qoralamasi → nashr (to'liq jarayon), ommaviy/yopiq kontent chegarasi, CMS nashr huquqi, audit jurnalining o'zgarmasligi, bildirishnomalar takrorlanmasligi, hisobotlar va CSV.

---

## 4. Frontend assetlar

> **Muhim:** shablonlarga yangi Tailwind klass qo'shsangiz, `npm run build` ni ishga tushiring — aks holda klass `static/dist/app.css` da bo'lmaydi (manba: `frontend/app.css`) va dizayn buziladi (masalan, menyu so'zlari yopishib qoladi).

Interaktiv qism (`static/js/public.js`): bo'limlarning 3D chuqurlikdan chiqishi (`data-reveal`, `data-stagger`), bo'limlarga animatsiyali sakrash, «Qanday mahsulotlar quramiz» sahnasi (`static/js/product-scene.js`: aylantirish bilan boshqariladi, qurilma 3D holatdan tekislanadi, tor ekranda kamera harakat tomon suriladi), bo'limga qarab avtomatik tun/kun ranglari (`data-theme="dark"`), loyiha brifi, portfolio kartalarining egilishi (`data-tilt`). Animatsiyalar faqat `transform`/`opacity` bilan — GPU'da, sahifa qayta chizilmaydi. Kam harakat (`prefers-reduced-motion`) rejimida o'chadi.



Tayyor CSS `static/dist/app.css` ichida bor — Node.js faqat dizaynni o'zgartirganda kerak:

```bash
npm install
npm run build     # bir marta yig'ish
npm run watch     # ishlab chiqishda
```

Three.js, Alpine.js, HTMX va shriftlar (Bricolage Grotesque, Onest) `static/` ichida — tashqi CDN yoki Google Fonts kerak emas.

---

## 5. Production (Ubuntu + Nginx + Gunicorn)

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
GUNICORN_BIND=127.0.0.1:8001 gunicorn config.wsgi -c config/gunicorn.conf.py
```

`.env` da `CACHE_URL=redis://127.0.0.1:6379/1` bo'lishi shart (Redis o'rnatiladi: `apt install redis-server`).

**Yuklama.** Mehmonlar uchun ommaviy sahifalar tayyor HTML ko'rinishida Redis'dan beriladi (`apps/website/cache.py`): kesh issiq bo'lsa so'rov bazaga ham, shablonga ham tegmaydi, faqat CSRF tokeni har foydalanuvchiga alohida qo'yiladi. CMS'da kontent o'zgarsa, kesh darhol yangilanadi. 2 yadroli sinov mashinasida (yuklama generatori ham shu mashinada) bosh sahifa 300 ta bir vaqtdagi ulanishda ~750 so'rov/s, xatosiz berildi. 5 000 kishi bir vaqtda saytda bo'lsa ham, har biri bir necha soniyada bitta sahifa ochadi — bu taxminan 200–500 so'rov/s. Shuning uchun 2–4 yadroli server yetadi. Ishchilar soni `GUNICORN_WORKERS` (standart: yadro × 2 + 1) va `GUNICORN_THREADS` (4) bilan sozlanadi; PostgreSQL `max_connections` ≥ workers × threads + 10 bo'lsin.

Nginx (qisqacha):

```nginx
server {
    server_name ssbgroup.uz;
    client_max_body_size 30m;
    location /media/ { alias /srv/ssb/media/; }        # faqat MEDIA_ROOT, PRIVATE_MEDIA_ROOT emas!
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

Statik fayllarni WhiteNoise beradi (siqilgan, xeshlangan nom va bir yillik kesh sarlavhasi bilan). HTML'ni siqish uchun Nginx'da `gzip on; gzip_types text/html text/css application/javascript image/svg+xml;` yoqing. HTTPS (Let's Encrypt) yoqing — `DEBUG=False` bo'lganda secure cookie va HSTS avtomatik yoqiladi.

**Muddat eslatmalari** — kuniga bir marta (cron):

```
0 9 * * *  cd /srv/ssb && .venv/bin/python manage.py send_deadline_reminders
```

Takroriy ishga tushirish bir xil eslatmani qayta yubormaydi.

---

## 6. Arxitektura

```
config/          sozlamalar, URL'lar
apps/core        umumiy: singleton sozlamalar, fayl validatsiyasi, maxfiy storage, rate limit, test fixture
apps/accounts    User, Role (huquqlar to'plami), Department, kirish/parol, policies.py
apps/audit       o'zgarmas AuditEvent + record()/form_changes()
apps/notifications  Notification + yagona notify() kirish nuqtasi
apps/website     ommaviy sayt: SiteSettings, Service, PortfolioProject, TeamMember, Testimonial, Highlight
apps/crm         Client, Inquiry, Project, Milestone, Task, Comment, Attachment, Review, Announcement
                 policies.py  — obyekt darajasidagi ruxsatlar
                 services.py  — biznes jarayonlari (holat o'tishlari, topshirish, tasdiqlash, konversiya)
                 reports.py — faqat bazadagi haqiqiy yozuvlardan hisoblanadi
templates/       base_public.html, enterprise/base.html va sahifalar
static/js/hero.js  Three.js 3D hero
frontend/app.css   Tailwind manbasi (static/ ichida emas — collectstatic uni qayta ishlamaydi)
```

Muhim qarorlar:

- **Lavozim, bo'lim va xavfsizlik roli alohida.** Rol — `capabilities` ro'yxati (21 ta huquq), `rank` (daraja), `dashboard` turi va `scope` (butun kompaniya / faqat o'z bo'limi). Asoschi roli barcha huquqlarga ega va faqat `bootstrap_company` orqali yaratiladi.
- **Huquqni oshirib olish bloklangan:** hech kim o'zini, o'ziga teng yoki yuqori darajadagi xodimni boshqara olmaydi; faqat o'zida bor huquqlarni va o'zidan quyi darajadagi rollarni bera oladi. Hammuassis, CEO va Direktor huquqlari asoschi tomonidan sozlanadi.
- **Har bir amal serverda tekshiriladi** (`policies.py`). Shablonlar faqat tugmalarni yashiradi; URL yoki ID o'zgartirish boshqa xodimning ma'lumotiga yo'l ochmaydi.
- **Holatlar faqat `services.py` orqali o'zgaradi** — kanban, tugmalar va forma bitta mantiqni ishlatadi. Topshirish vazifani avtomatik qabul qilmaydi; ijrochi o'z ishini tasdiqlay olmaydi.
- **Progress** = qabul qilingan asosiy vazifalar / bekor qilinmagan asosiy vazifalar.
- **Yakunlangan loyiha avtomatik ommaga chiqmaydi:** «Portfolio uchun tayyorlash» (nashr huquqi kerak) qoralama yaratadi, keyin alohida «Nashr qilish».
- **CMS:** qoralama → oldindan ko'rish → nashr → nashrdan olish → arxiv. Nashr qilingan kontentni faqat nashr huquqi borlar o'zgartiradi. Ommaviy sahifalar faqat `published` yozuvlarni ko'rsatadi.
- **Fayllar:** vazifa fayllari va xodim rasmlari `PRIVATE_MEDIA_ROOT`'da, tasodifiy nom bilan saqlanadi, faqat ruxsat tekshiradigan view orqali yuklanadi. Kengaytma va hajm chegarasi sozlamalardan; xavfli turlar (.exe, .js, .html …) bloklangan.
- **Audit:** huquq, xodim, loyiha, holat, nashr va sozlama o'zgarishlari — kim, nima, qachon, IP, o'zgarishlar. Parollar yozilmaydi; yozuvni tahrirlab yoki o'chirib bo'lmaydi.
- **3D hero: Three.js** tanlandi (Spline emas) — sahna kodda, interaktivlik (kursor, scroll, touch), yorug'lik va material to'liq nazoratda, tashqi xizmatga bog'liqlik yo'q. Sarlavha va tugmalar HTML'da; WebGL bo'lmasa SVG poster ko'rinadi; `prefers-reduced-motion` va ko'rinmaydigan holatda render to'xtaydi; mobilda geometriya yengillashtiriladi.
- **Murojaat formasi spamdan himoyasi:** honeypot maydon, imzolangan vaqt belgisi (3 soniyadan tez yuborilgan forma rad etiladi), IP bo'yicha soatiga 5 ta.

---

## 7. Hali sozlanishi kerak bo'lganlar

- **SMTP** — parolni tiklash xatlari uchun. Ungacha xodimga kirish havolasi CRM'dagi «Taklif havolasi» orqali beriladi.
- **Telegram bildirishnomalari** — arxitektura tayyor: `apps/notifications/services.py → notify()` ichiga kanal qo'shiladi, biznes mantig'i o'zgarmaydi. Bot token kerak.
- **Haqiqiy kontent** — kompaniya tarixi, aloqa ma'lumotlari, jamoa rasmlari, portfolio va mijozlar fikrlari CRM → «Sayt kontenti» orqali kiritiladi. `seed_site` faqat tahrirlanadigan qoralama matn beradi; hech qanday soxta natija, mijoz yoki statistika qo'shilmaydi.
- **Redis** (`CACHE_URL`) — sahifa keshi va rate limit barcha Gunicorn worker'larida umumiy bo'lishi uchun.
