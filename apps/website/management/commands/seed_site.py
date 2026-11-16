"""Starter website content: services, process steps, values. Runs only on an empty CMS.

Everything here is editable draft copy for leadership to review in the CRM (Sayt kontenti).
It contains no clients, statistics or achievements.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.website.models import Highlight, PublicationStatus, Service, SiteSettings, Technology

TECH = ["Python", "Django", "PostgreSQL", "JavaScript", "React", "Tailwind CSS", "Figma", "Telegram Bot API",
        "Docker", "REST API", "Three.js", "Aiogram"]

SERVICES = [
    ("Veb-saytlar", "web", "Kompaniya saytlari, landing sahifalar va onlayn do'konlar — tez, mobilga mos va qidiruv tizimlarida topiladigan.",
     "Sayt sizning birinchi taqdimotingiz. Biz uni maqsaddan boshlaymiz: kim kiradi, nima qilishi kerak va bu biznesga nima beradi. "
     "Dizayn, kontent tuzilmasi, ishlab chiqish va ishga tushirishni bitta jamoa olib boradi.",
     "Mobil qurilmalarga to'liq moslashgan\nKontentni o'zingiz boshqarasiz\nSEO uchun to'g'ri tuzilma\nTez yuklanish",
     ["Django", "Tailwind CSS", "JavaScript", "PostgreSQL"]),
    ("CRM tizimlari", "crm", "Mijozlar, buyurtmalar, xodimlar va hisobotlarni bitta tizimda yuritish uchun sizning jarayoningizga moslangan CRM.",
     "Tayyor CRM'lar ko'pincha biznesni o'ziga moslashtiradi. Biz esa sizning ish jarayoningizni o'rganib, aynan unga mos tizim quramiz: "
     "rollar va huquqlar, vazifalar, mijozlar bazasi, hisobotlar.",
     "Jarayoningizga moslangan\nRollar va kirish huquqlari\nHisobot va eksport\nBosqichma-bosqich joriy etish",
     ["Python", "Django", "PostgreSQL", "REST API"]),
    ("Telegram botlar", "bot", "Buyurtma qabul qilish, mijozlarga xizmat ko'rsatish va ichki jarayonlar uchun Telegram botlar.",
     "Mijozlaringiz allaqachon Telegramda. Bot buyurtma qabul qiladi, savollarga javob beradi, to'lov va bildirishnomalarni "
     "boshqaradi hamda CRM bilan ulanadi.",
     "Buyurtma va so'rovlarni avtomatlashtirish\nCRM va sayt bilan integratsiya\nAdmin panel\nKo'p tilli interfeys",
     ["Python", "Aiogram", "Telegram Bot API", "PostgreSQL"]),
    ("UI/UX dizayn", "design", "Foydalanuvchi tushunadigan interfeyslar: tadqiqot, prototip va dizayn tizimi.",
     "Yaxshi dizayn chiroyli bo'lishdan oldin tushunarli bo'lishi kerak. Foydalanuvchi ssenariylaridan boshlaymiz, "
     "prototipni sinaymiz va ishlab chiqishga tayyor dizayn tizimini topshiramiz.",
     "Foydalanuvchi ssenariylari\nInteraktiv prototiplar\nDizayn tizimi\nDasturchilar uchun tayyor maketlar",
     ["Figma"]),
    ("Biznes jarayonlarini avtomatlashtirish", "automation", "Takrorlanuvchi qo'l mehnatini — hisobotlar, jadval va xabarlarni — avtomatik jarayonlarga aylantirish.",
     "Excel jadvallar, qo'lda yuboriladigan xabarlar va takroriy hisobotlar vaqt oladi va xato beradi. "
     "Biz ularni tizimlar orasida avtomatik ishlaydigan jarayonlarga aylantiramiz.",
     "Tizimlar orasida integratsiya\nAvtomatik hisobotlar\nXatolar kamayadi\nXodimlar vaqti tejaladi",
     ["Python", "REST API", "Docker"]),
    ("Maxsus dasturiy ta'minot", "code", "Tayyor yechim topilmaganda — biznesingiz uchun noldan ishlab chiqilgan tizim.",
     "Murakkab yoki noyob vazifalar uchun arxitekturadan boshlab ishlab chiqamiz: talablarni aniqlash, prototip, "
     "bosqichma-bosqich ishlab chiqish va qo'llab-quvvatlash.",
     "Aniq texnik topshiriq\nBosqichma-bosqich yetkazish\nKod va hujjatlar sizniki\nQo'llab-quvvatlash",
     ["Python", "Django", "PostgreSQL", "Docker"]),
    ("Raqamli mahsulotlar", "product", "G'oyadan MVP'gacha: startaplar va yangi yo'nalishlar uchun mahsulot ishlab chiqish.",
     "G'oyani tezda sinab ko'rish uchun eng kichik ishlaydigan versiyani quramiz, foydalanuvchilar fikrini yig'amiz va "
     "mahsulotni shu asosda o'stiramiz.",
     "MVP qisqa muddatda\nFoydalanuvchi bilan sinov\nO'sishga tayyor arxitektura\nAnalitika",
     ["React", "Django", "PostgreSQL", "Figma"]),
]

PROCESS = [
    ("Muhokama", "Vazifa, maqsad va cheklovlarni birga aniqlaymiz."),
    ("Taklif", "Ish hajmi, muddat va narxni yozma ravishda kelishamiz."),
    ("Dizayn", "Prototip va maketlarni siz bilan tasdiqlaymiz."),
    ("Ishlab chiqish", "Bosqichma-bosqich quramiz va har bosqichni ko'rsatamiz."),
    ("Ishga tushirish", "Sinovdan o'tkazamiz, joylaymiz va qo'llab-quvvatlaymiz."),
]

REASONS = [
    ("Bitta jamoa — butun loyiha", "Dizayn, ishlab chiqish va ishga tushirishni bir jamoa olib boradi. Mas'uliyat aniq."),
    ("Jarayon shaffof", "Har bir bosqich, muddat va natija sizga ko'rinib turadi."),
    ("Mahalliy bozorni bilamiz", "O'zbekistondagi biznes jarayonlari, to'lov tizimlari va foydalanuvchilar odatlarini hisobga olamiz."),
    ("Ishga tushirgandan keyin ham", "Loyihani topshirib ketmaymiz: qo'llab-quvvatlash va rivojlantirishni davom ettiramiz."),
]

VALUES = [
    ("Halollik", "Muddat va narx haqida rostini aytamiz — yoqimsiz bo'lsa ham."),
    ("Sifat", "Kod, dizayn va hujjatlar keyingi jamoa ham tushunadigan darajada bo'lishi kerak."),
    ("Mas'uliyat", "Har bir vazifaning aniq egasi bor."),
    ("O'sish", "Har bir loyihadan keyin jamoa sifatida kuchliroq bo'lamiz."),
]

EXPERTISE = [
    ("Ichki qism", "Python, Django, REST API, PostgreSQL"),
    ("Tashqi qism", "JavaScript, React, Tailwind CSS, Three.js"),
    ("Dizayn", "Figma, dizayn tizimlari, prototiplash"),
    ("Integratsiyalar", "Telegram Bot API, to'lov tizimlari, tashqi API'lar"),
    ("Infratuzilma", "Docker, Linux serverlar, CI/CD"),
]


class Command(BaseCommand):
    help = "Fill an empty CMS with editable starter content."

    @transaction.atomic
    def handle(self, *args, **opts):
        if Service.objects.exists() or Highlight.objects.exists():
            self.stdout.write(self.style.WARNING("CMS bo'sh emas — hech narsa o'zgartirilmadi."))
            return
        tech = {name: Technology.objects.get_or_create(name=name)[0] for name in TECH}
        for i, (title, icon, summary, desc, benefits, techs) in enumerate(SERVICES):
            s = Service(title=title, icon=icon, summary=summary, description=desc, benefits=benefits, order=i)
            s.set_status(PublicationStatus.PUBLISHED)
            s.save()
            s.technologies.set([tech[t] for t in techs])
        for kind, rows in ((Highlight.Kind.PROCESS, PROCESS), (Highlight.Kind.REASON, REASONS),
                           (Highlight.Kind.VALUE, VALUES), (Highlight.Kind.EXPERTISE, EXPERTISE)):
            for i, (title, body) in enumerate(rows):
                h = Highlight(kind=kind, title=title, body=body, order=i)
                h.set_status(PublicationStatus.PUBLISHED)
                h.save()
        site = SiteSettings.load()
        site.intro_title = "Biznes uchun ishlaydigan dasturlar quramiz"
        site.intro_text = (
            "SSB Group — veb-saytlar, CRM tizimlari, Telegram botlar va biznes jarayonlarini avtomatlashtirish bilan "
            "shug'ullanadigan IT kompaniya.\n\nHar bir loyihani biznesingizdagi aniq muammodan boshlaymiz va "
            "ishlaydigan, qo'llab-quvvatlanadigan tizim bilan yakunlaymiz."
        )
        site.mission = "Biznesga kundalik ishini soddalashtiradigan, ishonchli va tushunarli dasturiy tizimlar yaratish."
        site.vision = "O'zbekistonda biznes raqamli tizimlar haqida o'ylaganda birinchi eslaydigan jamoa bo'lish."
        site.philosophy = (
            "Eng sodda yechimdan boshlaymiz va uni bosqichma-bosqich o'stiramiz. Ishlayotgan mahsulotni tugallanmagan "
            "murakkablik uchun buzmaymiz. Har bir qaror uzoq muddatga mo'ljallangan."
        )
        site.save()
        self.stdout.write(self.style.SUCCESS("Boshlang'ich kontent yaratildi. CRM → Sayt kontenti orqali tahrirlang."))
