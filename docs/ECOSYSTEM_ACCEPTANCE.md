# SSB Boshqaruv 2.0.0 — tekshiruv holati

Veb va Windows bitta Django/PostgreSQL tizimiga ulanadi. EXE ichida alohida dashboard yoki moliyaviy hisoblash yo‘q. Asosiy manzil `/management/enterprise/`; eski dashboard view va shabloni olib tashlangan. Biznes modullari saqlangan.

## Ushbu relizdagi tuzatishlar

- Desktop `shell.js` dagi sintaksis xatosi bartaraf qilindi; startup, server sozlash, ulanish holatlari va oyna tugmalari ishlaydi.
- Fayl yuklashda saqlash oynasi va progress holati bor. Boshqa serverdan kelgan avtomatik download rad etiladi.
- Yangilash tugmasi ko‘rinadigan title bar ichiga ko‘chirildi. Tarmoq xatosi foydalanuvchiga ko‘rsatiladi. Feed sozlanmaganida ishlayotgan yangilanish haqida da’vo qilinmaydi.
- Hisob almashganda native bildirishnoma keshi tozalanadi; oldingi sessiya holati yangi hisobga ko‘chirilmaydi.
- Tezkor amallar menyusi serverdagi ruxsatlarga mos. Ctrl/Cmd + K yoki `/` qidiruvni, Alt + N tezkor amallarni ochadi. Mobil qurilmada qidiruv sahifasi ochiladi.
- Sahifa yo‘li, moliyaviy reyestr qidiruvi, sana/tur filtrlari, tartiblash va 30 yozuvli sahifalash qo‘shildi. Filtrlar haqiqiy umumiy balansni o‘zgartirmaydi.
- Tushum grafigi faqat tasdiqlangan reyestrdan chiziladi. Aniq summalar va eksport jadvalda saqlangan.

## Haqiqiy desktop sinovi

Yakuniy to‘liq test to‘plami: 103 test, barchasi o‘tgan, desktop sinovi ham shu hisobga kiritilgan. Brauzerda 21 holat (6 rol va haqiqiy tushum grafigi × 3 ekran kengligi) tekshirildi: JavaScript xatosi yoki gorizontal toshish aniqlanmadi; Alt + N va Ctrl/Cmd + K ham tekshirildi.

`apps/enterprise/tests/test_windows_journey.py` alohida vaqtinchalik PostgreSQL bazasi va Django live serverni ochadi. `desktop/qa/journey.cjs` yig‘ilgan EXE’ni alohida yashirin profil bilan boshqaradi. Bu QA skripti installerga kiritilmaydi. Vaqtinchalik test hisobining paroli Node jarayoniga stdin orqali beriladi; manba kodiga yoki EXE’ga yozilmaydi.

Tekshirilgan jarayon:

1. EXE’da haqiqiy kirish formasi orqali autentifikatsiya.
2. Yagona Enterprise dashboardga yo‘naltirish.
3. Alohida veb sessiyada vazifani tahrirlash va desktop API’da o‘zgarishni ko‘rish.
4. Desktop sessiyada vazifani tahrirlash va veb sessiyada yangi qiymatni ko‘rish.
5. Desktop orqali ruxsat tekshiriladigan himoyalangan loyiha faylini yuklab olish.
6. Masofaviy sahifada Node va mahalliy IPC yo‘qligini tekshirish.
7. Desktopdan chiqish va sessiya API’si kirishni rad etishini tekshirish.

Qaytarish: `SSB_WINDOWS_JOURNEY=1`, `SSB_NODE=<node.exe>` bilan `python manage.py test apps --noinput`. `SSB_DESKTOP_EXE` o‘zgaruvchisi o‘rnatilgan EXE’ni ko‘rsatishi ham mumkin. Test ishlab turgan kompaniya bazasini tozalamaydi.

## Tashqi sozlamalar va qolgan qabul shartlari

Windows code-signing sertifikati va HTTPS update feed berilmagan. 1.0.1 installer imzosiz; yangilanish arxitekturasi va `latest.yml` mavjud, xizmat ommaviy ishga tushirilmagan.

Haqiqiy AI gateway manzili/kaliti va antivirus executable serverda sozlanishi kerak. AI gateway kontrakti mock bilan, odatiy ko‘rsatkichlarga asoslangan baholash esa haqiqiy yozuvlar bilan tekshiriladi. Production fayl yuklash antivirus sozlanmaganda yopiq holatda qoladi. Gatewayga xodimning ismi yoki maoshi yuborilmaydi; AI natijasi moliyaviy huquqlarni o‘zgartirmaydi.

Kompyuterda ochiq turgan 1.0.0 ilovasini majburan yopish bajarilmagan. 1.0.1 installer paketining yaxlitligi va yig‘ilgan EXE sinovi bajariladi; mavjud ochiq ilovani yangilab o‘rnatish sinovi uni yopishga ruxsat kelgach tugatiladi. Shu bosqich bajarilmaguncha installer yangilash sinovi to‘liq o‘tdi deb ko‘rsatilmaydi.
