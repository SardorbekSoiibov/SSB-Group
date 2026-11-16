# SSB Boshqaruv

## Ishga tushirish

Mavjud `start.bat` PostgreSQL va Django xizmatlarini ochadi. Yagona dashboard `/management/enterprise/` manzilida. `/management/` shu manzilga doimiy yo‘naltiradi. Kirish mavjud kompaniya hisoblari bilan amalga oshiriladi. Yangi asoschi yoki moliyaviy namunaviy yozuvlar ishlab turgan bazaga avtomatik qo‘shilmaydi.

`python manage.py migrate` yangi sxema, moliyaviy himoya triggerlari va standart boshqaruv rollariga huquqlarni o‘rnatadi. `python manage.py test apps --noinput` alohida test bazasidan foydalanadi. PostgreSQL talab qilinadi; SQLite moliyaviy tranzaksiyalar uchun qo‘llanmaydi.

## Tuzilishi

`apps.enterprise` moliya, tasdiqlash, himoyalangan arxiv, ish jadvali, baholash, hisobotlar va vidjetlarni o‘z ichiga oladi. Mavjud `crm`, `accounts`, `notifications`, `audit` modullari saqlangan. `/management/enterprise/api/` Django REST Framework orqali ayni biznes xizmatlarini ishlatadi. API session cookie, CSRF va serverdagi huquq tekshiruvlariga tayanadi.

Windows ilova alohida baza yaratmaydi. Electron asosiy jarayoni mahalliy oyna boshqaruvini, sandbox ichidagi veb qism esa ayni Django saytini ishlatadi. Masofaviy sahifaga Node yoki IPC huquqi berilmaydi. Server uchun HTTPS talab etiladi; HTTP faqat localhostda ishlaydi. Login/parol va backend kalitlari `.exe` ichiga kiritilmaydi. Konfiguratsiyada faqat server manzili va oyna o‘lchami saqlanadi. Session brauzerning yopiq saqlash profilida bo‘ladi; umumiy kompyuterda chiqish tugmasidan foydalaniladi.

## Moliyaviy hisob

1. Vakolatli boshqaruvchi loyiha summasi va ulushlarini kiritadi. Boshlang‘ich kompaniya ulushi 30%; qolgan qism tanlangan loyiha xodimlari orasida teng yoki alohida foizlarda bo‘linadi.
2. Boshqa vakolatli boshqaruvchi kelishuvni tasdiqlaydi. Foizlar versiyalangan o‘zgarmas snapshotga yoziladi.
3. Mijozdan haqiqiy tushum qayd etilganda, shu snapshot asosida xodimga hisoblangan daromad yaratiladi. Kelishuvning o‘zi pul tushumi hisoblanmaydi.
4. Xodimga haqiqiy to‘lov alohida yoziladi va tasdiqlanadi. Hisoblangan, to‘langan va to‘lanishi kerak bo‘lgan summalar reyestrdan hisoblanadi; qo‘lda tahrirlanadigan balans yo‘q.
5. Xato yozuv o‘chirilmaydi: asl yozuvga bog‘langan tuzatish va sababi yaratiladi. Mijoz tushumi qaytarilsa tegishli xodim ulushlari ham izchil tuzatiladi. To‘langan daromadni qarzdorlikdan oshirib kamaytirish bloklanadi.

Barcha summalar `Decimal` / PostgreSQL `numeric` ko‘rinishida. Valyutalar aralashtirilmaydi. Har amal UUID va takror yuborishni tekshiradigan idempotency kalitiga ega. Yozish va tasdiqlash `atomic` tranzaksiyada, umumiy advisory lock bilan bajariladi. Immutability va tasdiqlangan operatsiyaga bog‘lanish bazaning o‘zida ham tekshiriladi. DBA/superuser bazani o‘zgartira olishi sababli ishlab chiqarishdagi ilova DB hisobi superuser yoki schema egasi bo‘lmasligi kerak.

Kompaniya ulushi = mijoz tushumi − loyiha xodimlari ulushi. Sof foyda = kompaniya ulushi − oylik − mukofot − operatsion xarajat. Kassadagi pul = mijoz tushumi − haqiqiy xodim to‘lovlari − operatsion xarajat. Qarzdorlik = hisoblangan daromad − haqiqiy to‘lov. Manba UUID va audit tarixi hisoblar yonidan ochiladi.

Tasdiqlash qoidalarida amal turi, valyuta, chegara va tasdiqlovchilar soni belgilanadi. So‘rov paytida qoida nusxalanadi; keyingi qoida eski so‘rovni o‘zgartirmaydi. Kelishuv va tuzatishda kamida bitta mustaqil tasdiqlovchi shart. Asoschi ham o‘z cheklangan so‘rovini o‘zi tasdiqlay olmaydi. Yagona boshqaruvchi bo‘lsa, moliyaviy tasdiq uchun ikkinchi vakolatli hisob kerak.

## Arxiv va baholash

Arxiv `private_media` ichida saqlanadi; uni veb-serverning ommaviy media aliasiga qo‘shmang. Kodlar Django password hasher orqali saqlanadi. Kod kirish huquqi 10 daqiqa; kod o‘zgarsa eski grant bekor bo‘ladi. Loyiha huquqi har yuklashda qayta tekshiriladi. Maksimal hajm 50 MB, ochilgan arxiv hajmi 500 MB. ZIP traversal, siqish bombasi, symlink va parollangan arxivlar rad etiladi.

`MALWARE_SCANNER` muhit o‘zgaruvchisiga mahalliy ClamAV executable manzilini bering. `REQUIRE_MALWARE_SCAN=True` holatida scanner bo‘lmasa yuklash bloklanadi; productionda bu boshlang‘ich holat. Debug rejimida scannersiz fayl holati ochiq ko‘rsatiladi. Bu kompyuterga antivirus o‘rnatilgani haqida da’vo qilinmaydi.

Faoliyat bahosi haqiqiy topshiriq tugashi va muddatlarga asoslanadi. Qo‘shimcha sifat va direktor bahosi berilsa formula: operatsion ball × 70% + sifat × 20% + direktor × 10%. Barcha kirish ko‘rsatkichlari baholash snapshotida saqlanadi. Xodim faqat rahbar tasdiqlagan o‘z baholarini ko‘radi. Baholash moliyaviy reyestrni o‘zgartirmaydi.

AI uchun `PERFORMANCE_AI_ENDPOINT` (HTTPS) va `PERFORMANCE_AI_KEY` serverda sozlanadi. Endpoint `POST {metrics, task}` qabul qilib, `{"analysis":"..."}` qaytaradigan ishonchli gateway bo‘lishi kerak. Xodim ismi, paroli yoki maoshi yuborilmaydi. Xizmat ulanmasa oddiy hisoblash ishlaydi va AI deb ko‘rsatilmaydi. Tashqi AI integratsiyasi haqiqiy provayder bilan alohida tekshirilishi kerak.

## Windows relizi

Manbalar `desktop/`, tayyor relizlar `desktop/release/` ichida. Yig‘ish: `cd desktop`, `npm ci`, `npm run dist`. Electron runtime rasmiy distributivdan olinadi. NSIS installer x64, Windows 10/11, tanlanadigan o‘rnatish katalogi, progress, desktop/Start Menu yorliqlari va uninstallni ta’minlaydi.

Dashboarddagi yuklash amali faqat mavjud haqiqiy `SSB-Boshqaruv-Setup-2.0.0.exe` faylini autentifikatsiyadan keyin beradi. Manzil `DESKTOP_RELEASE_PATH` bilan o‘zgartirilishi mumkin. Relizda server credentials yoki `.env` yo‘q.

Avtomatik yangilash arxitekturasi `electron-updater` bilan tayyor. `SSB_UPDATE_FEED` HTTPS manzilini desktop ishga tushish muhitida sozlang; reliz metama’lumoti, blockmap va installer shu feedda beriladi. Hozir tashqi update serveri va Windows code-signing sertifikati taqdim etilmagan. Shuning uchun build imzosiz; ommaviy production tarqatishdan oldin kompaniya sertifikati bilan imzolash, signed update feed va alohida Windows 10/11 sinovi zarur. Bu cheklov yashirilmaydi.

## Backup va tiklash

Tavsiya: har kuni PostgreSQL custom-format backup, har hafta private_media nusxasi; kamida 7 kunlik, 4 haftalik, 12 oylik saqlash. Nusxalar shifrlangan boshqa qurilmaga ko‘chiriladi; backup account va disk ruxsatlari cheklanadi. Scheduler kompaniya serverida sozlanadi, dastur o‘zicha OS vazifalarini yaratmaydi.

`python manage.py backup_database --format pgdump --output private_media/backups/YYYY-MM-DD.dump` (`pg_dump` PATH ichida bo‘lsin). SHA256 yon fayl yaratiladi; mavjud nusxa ustidan yozilmaydi. Kichik ko‘chirish uchun `--format json` gzip fixture ham mavjud. JSON katta production bazani tiklashning asosiy vositasi emas.

Tiklash mashqi yangi, alohida PostgreSQL bazasida bajariladi: checksumni tekshirish, `pg_restore --no-owner --dbname=<YANGI_BAZA> <backup>`, media nusxasini qaytarish, `manage.py check`, manbalar/qarzdorlik/foydani solishtirish. Jonli bazani o‘chirib qayta yaratish avtomatlashtirilmagan. Ilova yozishni to‘xtatib turish va to‘liq backup olish reliz oldidagi xizmat tartibining bir qismi. Moliyaviy triggerlarni ishlab turgan bazada o‘chirib qo‘ymang.

## Production sozlamalari

HTTPS reverse proxy, `DEBUG=False`, yangi `SECRET_KEY`, aniq `ALLOWED_HOSTS` / CSRF trusted origins, secure session/CSRF cookies va HSTS sozlang. Mavjud xavfsizlik sozlamalarini server domeniga mos tekshiring. Private media, `.env`, backup va development PostgreSQL ma’lumotlari ochiq hostingga yuborilmaydi. Ishlab chiqishdagi DB paroli productionga ko‘chirilmaydi.

Native va veb bildirishnomalar serverdan so‘raladi; bu WebSocket emas. Desktop yangi bildirishnomalarni 20 soniyada tekshiradi. Tashqi notification/push servisi talab qilinmaydi.
