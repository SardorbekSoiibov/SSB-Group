# Yagona Enterprise dashboard

Dashboard manzili: `/management/enterprise/` (`enterprise:overview`). Standart kirish, modal kirish, ommaviy saytdagi kabinet havolalari va sidebar logotipi shu sahifani ochadi. `/management/` eski saqlangan havolalar uchun faqat 301 yo‘naltirishdir; unda alohida sahifa yoki view yo‘q.

## Tekshirilgan bog‘lanishlar

Oldingi dashboard `/management/` → `crm:dashboard` → `people.dashboard` → `apps.crm.dashboard.build` → `templates/crm/dashboard.html` orqali ishlagan. Shu sahifa, view, hisoblash moduli va faqat unga tegishli `.dashboard-*` CSS qoidalari olib tashlandi. Eski URL nomi ro‘yxatdan chiqarildi.

Enterprise dashboard `/management/enterprise/` → `enterprise:overview` → `apps.enterprise.views.overview` → `templates/enterprise/overview.html` orqali ishlaydi. Uning vidjetlari, moliyaviy xizmatlari, ruxsatlari, per-user saqlanadigan joylashuvi va dizayni saqlandi. Asoschi, hammuassis, direktor va xodimlar uchun shu bitta view mavjud rol sozlamalari va huquqlardan foydalanadi; qo‘shimcha dashboard yaratilmagan.

## Saqlangan umumiy qismlar

Oldingi `base_crm.html` ikkala dashboard va barcha biznes sahifalarining umumiy maketi bo‘lgan. Enterprise ishlatayotgan ko‘rinish `templates/enterprise/base.html` nomi ostida yagona maket bo‘ldi. Barcha biznes shablonlar shu maketni ishlatadi. Sidebar’dagi takroriy dashboard havolasi olib tashlandi. Sidebar, bildirishnomalar, tasdiqlash dialogi, mobil menyu va kanban uchun umumiy JavaScript `static/js/enterprise-shell.js` ichida saqlandi.

`crm/_icon.html`, `_nav_link.html`, `_avatar.html`, jadval va forma komponentlari yangi dashboard hamda loyihalar, vazifalar va hisob boshqaruvida ishlatilgani uchun saqlandi. `workspace.css` faqat umumiy forma, jadval va moslashuv qoidalarini saqlaydi; eski dashboard vidjetlari uslublari olib tashlangan. Asosiy Enterprise dizayni `enterprise.css` ichida o‘z holicha qolgan.

Audit va ish hisobotlari foydalanadigan sana yordamchisi eski dashboard hisoblash modulidan mustaqil `apps/core/dates.py` ga ajratildi. Moliyaviy va ish jarayoni hisobotlari alohida ishlaydigan biznes modullaridir; ular dashboard nusxalari emas.

## Ma’lumotlar va tekshiruv

Bu almashtirish model, migratsiya yoki biznes yozuvlarini o‘zgartirmaydi. Xodimlar, rollar, loyihalar, vazifalar, moliyaviy operatsiyalar, ulush snapshotlari, arxivlar va foydalanuvchi joylashuvlari saqlanadi. Ishlab turgan bazani tozalash yoki qayta yaratish bu ishga kirmaydi.

`python manage.py test apps --noinput` alohida test bazasida kirish yo‘nalishlari, barcha rollar, yagona sidebar, mavjud havolalar, vidjetlarni saqlash, ruxsatlar va biznes modullarini tekshiradi. `test_dashboard_replacement.py` eski sahifa va URL nomi mavjud emasligini ham tekshiradi.

Yakuniy tekshiruv: 96 ta test muvaffaqiyatli o‘tdi. Asoschi, hammuassis, direktor, bosh direktor, jamoa rahbari va xodim sahifalari 1440, 768 va 390 piksel kenglikda tekshirildi. JavaScript xatosi va gorizontal toshish topilmadi. Vidjetni yashirish, qayta qo‘shish, kengaytirish va joylashuvni saqlash tekshirildi.

Windows’da PostgreSQL jurnali `.setup/postgresql.log` ga yoziladi. Jurnalni `.pgdata` katalogidan tashqarida saqlash avvalgi kutilmagan yopilishdan tiklanishda fayl bandligi muammosini bartaraf qiladi. Baza qayta yaratilmaydi.
