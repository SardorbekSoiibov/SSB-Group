# Haftalik baholash va reyting

## Doira va zaxira

Faqat “Jamoa bahosi va AI”, “Haftalik reyting” hamda talabdagi shaxsiy natija kartasi o‘zgartirildi. Moliya uchun mavjud `finance.request_operation` ishlatiladi. Umumiy menyu, autentifikatsiya, rollar, global sozlamalar va boshqa modullar qayta ishlanmadi.

Kod zaxirasi: `.setup/performance-before-20261105-165241.zip`. Migratsiyalar mavjud yozuvlarni yangilamaydi yoki o‘chirmaydi. Eski `PerformanceReview`, `ReviewApproval`, `WeeklyRating`, `WeeklyPlace` yozuvlari tarix sifatida saqlanadi. Eski baholar `/management/enterprise/performance/history/` orqali, eski reytinglar reyting sahifasidagi tarixdan ochiladi.

## Ishlash tartibi

1. Hafta: dushanba 00:00 dan keyingi dushanba 00:00 gacha, oxirgi chegara kiritilmaydi. Zona: `Asia/Tashkent`.
2. Kompaniya doirasidagi `performance.manage` vakolati bor rahbar tugagan haftani tayyorlaydi. Faol xodimlar, ta’sischi va superuserlardan tashqari, bir marta tanlanadi. Haftaning ro‘yxati va dalillari keyingi qayta ishga tushirishda o‘zgarmaydi.
3. Vazifalar, loyiha nomlari, muddatlar, qabul va qaytarish yozuvlari o‘qiladi. Asl dalillar va asl ball saqlanadi. Qo‘lda yaratilgan soxta faoliyat qo‘shilmaydi.
4. Rahbar alohida tekshirish sahifasida dalillar, mezonlar, tahlil va tarixni ko‘radi. Rahbar bahosi majburiy. Boshqa ballarni ham tuzatish mumkin; sabab kamida 10 belgi. Izoh ham kamida 10 belgi. O‘zini tasdiqlash mumkin emas. Cheklangan rahbar faqat mavjud `visible_employees` doirasida ishlaydi.
5. Qoralamani saqlash, tuzatishga qaytarish, qaytarilgan bahoni tuzatish va yakuniy tasdiqlash mavjud. Asl ball o‘zgarmaydi. Tasdiqlangan baho qayta tahrirlanmaydi.
6. Barcha baholar tasdiqlanmaguncha rasmiy reyting yo‘q. Tasdiqlangach yakuniy ball kamayish tartibida o‘rinlar olinadi. Teng ballarda ID o‘sish tartibi qo‘llanadi; bu qoida sahifada ochiq yozilgan.
7. E’lon qilingan reytingda ism, lavozim, ball, yutuqlar nusxasi saqlanadi. Keyingi vazifa yoki lavozim tahriri tarixni qayta hisoblamaydi. Fotosuratlar mavjud himoyalangan xodim rasmi xizmatidan olinadi.
8. Xodim o‘zining e’lon qilingan tasdiqlangan tahlilini ko‘radi. Boshqa xodimning maxfiy tahlili va rahbar izohi ochilmaydi. Umumiy reyting va uning tarixidagi ommaviy ballar/yutuqlar ko‘rinadi.

## Formula va AI

Og‘irliklar har hafta tayyorlashda sozlanadi va shu hafta bilan muzlatiladi. Dastlabki qiymatlar: bajarilish 25%, sifat 25%, hissa 20%, muddat 15%, rahbar 15%. Jami 100%. Har bir mezon 0–100; umumiy ball vaznlangan yig‘indi, ikki kasr xonagacha.

AI mavjud bo‘lmagandagi ochiq hisob:

| Mezon | Hisob |
|---|---|
| Bajarilish | 100 × shu haftada qabul qilingan / max(haftada muddati tushgan, haftada qabul qilingan, 1) |
| Sifat | 100 × qabul qilingan / max(qabul qilingan + shu haftadagi tuzatish so‘rovlari, 1) |
| Hissa | 100 × xodimning qabul qilingan vazifalari / max(uning natija bergan loyihalarida haftada qabul qilingan barcha vazifalar, 1) |
| Muddat | 100 × muddatida qabul qilingan / max(muddatli qabul qilingan vazifalar, 1) |
| Rahbar | Avval 0, tasdiqlashdan oldin rahbar aniq bahosini kiritadi |

**Cheklov:** mavjud vazifada murakkablik/ish hajmi/ish soati alohida qayd etilmaydi. Ustuvorlik murakkablik deb olinmaydi. Hissa — vazifalar ulushi, iqtisodiy qiymat yoki sarflangan vaqt emas. Ish sifati qayta ishlashlardan olinadigan ko‘rsatkich; haqiqiy sifatni rahbar tekshiradi. Bu cheklovlar har baholashda ko‘rsatiladi; rahbar dalilli sabab bilan ballni tuzatishi mumkin.

Mavjud `PERFORMANCE_AI_ENDPOINT` va `PERFORMANCE_AI_KEY` integratsiyasi qayta ishlatiladi; global sozlamalar o‘zgarmadi. HTTPS endpointga ism yoki maxfiy kalitni payloadga qo‘shmasdan vazifa dalillari yuboriladi; kalit Authorization sarlavhasida. Vazifa matnlari ishonchsiz ma’lumot deb belgilanadi. AI besh mezon balli, kuchli/zaif tomonlar, tavsiyalar va yozma tahlilni JSON formatida qaytaradi. Jami ball mahalliy formula bilan tekshiriladi/hisoblanadi. Yutuqlar ro‘yxati AI javobidan olinmaydi, faqat qabul qilingan vazifalardan tuziladi. AI rahbar bahosini oldindan qo‘ymaydi. AI ishlamasa, noto‘g‘ri JSON/chegaradan tashqari ball bersa yoki timeout bo‘lsa, ochiq hisobga qaytiladi. AI matni rahbar tekshirishi kerak bo‘lgan tavsiya sifatida ko‘rsatiladi.

Joriy muhitda AI endpoint va kalit sozlanmagan. Haqiqiy provayder bilan jonli so‘rov sinovi bajarilmagan; integratsiya strukturali test javobi va xato holatlari bilan tekshirildi.

## Mukofotlar

Har hafta 1/2/3-o‘rin uchun bitta mukofot: turi, tavsifi, qiymati, valyutasi, holati. Qoralamani nashrdan oldin tayyorlash mumkin; tasdiqlash faqat e’lon qilingan o‘rin egasiga. Tasdiqlangan mukofot shartlari o‘zgarmaydi; sovg‘a/e’tirof keyin topshirildi deb belgilanishi mumkin.

Pul mukofotini tasdiqlash `finance.request_operation(kind='bonus')` orqali barqaror UUID bilan bitta so‘rov yaratadi. Mavjud moliyaviy vakolat va mustaqil tasdiqlash qoidalari saqlanadi. Bu avtomatik bank to‘lovi emas. Moliyaviy holat mavjud operatsiyadan jonli olinadi. Qayta yuborish ikkinchi bonus yaratmaydi. Rad etilgan moliyaviy so‘rov mavjud reyestrda rad etilgan sifatida qoladi; tizim o‘zicha boshqa so‘rov yaratmaydi.

## Avtomatlashtirish

Qo‘lda bajarish:

```powershell
.\.venv\Scripts\python.exe manage.py process_weekly_performance --actor ssbgroup
# Eski scheduler nomi ham shu oqimga ulanadi:
.\.venv\Scripts\python.exe manage.py generate_weekly_reviews --actor ssbgroup
# Eski tugagan haftani tayyorlash:
.\.venv\Scripts\python.exe manage.py process_weekly_performance --actor ssbgroup --week 2026-10-26
```

Windows uchun tayyor o‘rnatish skripti:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/install-performance-schedule.ps1 -Actor ssbgroup
```

Bu faqat joriy buyruq jarayonining execution policy parametridir; tizim policy sozlamasi o‘zgarmaydi. Vazifa foydalanuvchi sessiyasida yashirin `pythonw.exe` bilan har 5 daqiqada tekshiradi. Dushanba 00:00 dan so‘ng tugagan hafta tayyorlanadi; tasdiq yo‘q bo‘lsa nashr kechiktiriladi. Mashina, foydalanuvchi sessiyasi va PostgreSQL ishlashi kerak. Log: `.setup/weekly-performance-job.log`. Parallel ishga tushish va takroriy baholash/nashr/mukofotlar bloklangan.

**O‘rnatish holati:** avtomatik ruxsat tekshiruvi doimiy Windows vazifasini ro‘yxatdan o‘tkazishni rad etdi. Shu sabab vazifa o‘rnatilmadi; script va buyruqlar tayyor, alohida aniq ruxsat kutiladi. Rad etishdan keyin boshqa yo‘l bilan doimiy ishga tushirish o‘rnatilmadi.

## O‘zgargan fayllar va sababi

| Fayl | Sabab |
|---|---|
| `apps/enterprise/models.py` | Haftalik davr, xodim bahosi va mukofot modeli; asl/yakuniy balllarni ajratish |
| `apps/enterprise/migrations/0008_unified_weekly_performance.py` | Faqat yangi uch jadval, noyoblik va ball chegaralari |
| `apps/enterprise/migrations/0009_weekly_history_guards.py` | Asl dalillar, tasdiqlangan ball va tarixni DB darajasida himoyalash |
| `apps/enterprise/performance_system.py` | Haqiqiy dalillar, formula, AI/fallback, rahbar qarori, nashr, idempotent mukofot va moliya integratsiyasi |
| `apps/enterprise/performance_views.py` | Shu ikki modulning formasi, tekshirish, reyting, mukofot va tarix sahifalari |
| `apps/enterprise/urls.py` | Faqat ikki modul yo‘llarini yangi oqimga ulash va zarur sub-sahifalar |
| `apps/enterprise/management/commands/process_weekly_performance.py` | Qayta bajarish xavfsiz bo‘lgan haftalik tayyorlash/nashr buyrug‘i |
| `apps/enterprise/management/commands/generate_weekly_reviews.py` | Eski scheduler nomini yangi yagona tizimga ulash |
| `apps/enterprise/templatetags/__init__.py` | Yangi lokal template tag paketi |
| `apps/enterprise/templatetags/weekly_performance.py` | Shaxsiy dashboardga tasdiqlangan natijani xavfsiz olish |
| `templates/boshqaruv/dashboards/employee.html` | Talabdagi bitta shaxsiy natija kartasini mavjud tuzilishga qo‘shish |
| `templates/boshqaruv/business/_personal_performance.html` | Shaxsiy ball, o‘rin va tahlil/tarix havolalari |
| `templates/boshqaruv/business/_performance_nav.html` | Ikki modul va tarixiy haftalar o‘rtasidagi lokal navigatsiya |
| `templates/boshqaruv/business/performance_weekly.html` | Hafta tayyorlash va baholash ro‘yxati |
| `templates/boshqaruv/business/evaluation_detail.html` | Dalillar, asl/yakuniy mezonlar, AI matni, direktor tekshiruvi, audit |
| `templates/boshqaruv/business/rating_weekly.html` | Rasmiy TOP-3, barcha o‘rinlar, mukofotlar va eski tarix |
| `templates/boshqaruv/business/_reward_editor.html` | Uch o‘rin uchun mukofot shakli va pul jarayoni izohi |
| `templates/boshqaruv/business/reward_form.html` | Mukofot xatolarini kiritilgan qiymatlarni yo‘qotmay ko‘rsatish |
| `static/boshqaruv/weekly-performance.css` | Faqat shu sahifalarga tegishli mavjud dizayn ranglaridagi responsive ko‘rinish |
| `tools/install-performance-schedule.ps1` | Tasdiqdan keyin o‘rnatiladigan Windows avtomatik vazifasi |
| `tools/run-performance-job.py` | Ko‘rinmas oynasiz scheduler ishga tushiruvchisi va lokal log |
| `tools/qa/performance-browser.cjs` | Brauzerda tasdiqlash → nashr → TOP-3 → mobil oqim sinovi |
| `apps/enterprise/tests/test_performance_browser.py` | Alohida test serveri/bazasida brauzer tekshiruvi |
| `apps/enterprise/tests/test_unified_performance.py` | Dalillar, AI, formula, ruxsatlar, tarix, mukofot, scheduler regressiya testlari |
| `apps/enterprise/tests/test_operations.py` | Eski baholar uchun tarix yo‘li va yangi scheduler modeliga mos tekshiruv |
| `apps/enterprise/tests/test_project_erase.py` | Faqat baholashga tegishli testlarni yangi oqim/tarixga moslash; loyiha o‘chirish testlari o‘zgarmadi |
| `apps/enterprise/tests/test_weekly_rating.py` | Eski qo‘lda o‘rin belgilash o‘rniga faqat tasdiqlangan reyting; eski tarix xizmatlari testlari saqlandi |
| `docs/WEEKLY_PERFORMANCE_ACCEPTANCE.md` | Ishlash tartibi, cheklovlar, schedule holati va fayllar ro‘yxati |

## Tekshiruv

Testlar alohida PostgreSQL test bazasidan foydalanadi. Brauzer QA yozuvlari haqiqiy bazaga kiritilmaydi.

- `manage.py test apps --noinput`: 294 test, 287 muvaffaqiyatli, 7 opt-in/muhitga bog‘liq test o‘tkazib yuborilgan. Log: `.setup/performance-all-apps-tests.log`.
- Yangi tizimning 18 ta testi oxirgi kod bilan qayta o‘tdi: dalillar, hafta chegaralari, formula, vaznlar, AI JSON, fallback, ruxsatlar, asl/yakuniy ball, sabab, qaytarish, tasdiq, TOP-3, tarixning DB himoyasi, mukofot, moliyaviy tasdiq va idempotent scheduler.
- Alohida haqiqiy headless Edge sinovi o‘tdi: uch xodimni brauzerdagi formalar orqali tasdiqlash, nashr, TOP-3, g‘olib va 390px mobil ko‘rinish. Gorizontal sahifa chiqishi yo‘q. Desktop va mobil screenshotlar ko‘zdan kechirildi. Natija: `.setup/performance-browser-result.json`.
- `manage.py check`: xato yo‘q. `makemigrations --check --dry-run`: model va migratsiyalar mos.
- Haqiqiy bazadagi ikkala modul va baholash tafsiloti vakolatli foydalanuvchi bilan HTTP 200 qaytardi.
- 2026-10-26 — 2026-11-01 uchun 3 ta haqiqiy baholash qoralamasi tayyorlandi. Hech biri avtomatik tasdiqlanmadi yoki e’lon qilinmadi. Haqiqiy mukofot/bonus yaratilmagan.
- Windows vazifasi o‘rnatilmagan: avtomatik ruxsat tekshiruvi ikki marta rad etdi. `process_weekly_performance` buyrug‘i va brauzerdagi qo‘lda ish jarayoni ishlaydi.
