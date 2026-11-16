# Moliyaviy tahlil

`/management/enterprise/reports/` faqat `finance.view` huquqiga ega foydalanuvchilarga ochiladi. Xodim o‘z hisobini “Shaxsiy hisobim” orqali ko‘radi. Hisobotlar serverdagi ruxsat doirasi bilan cheklanadi. Eksport ham ayni huquq tekshiruvi va hisoblangan qatorlardan foydalanadi.

Kunlik, haftalik, oylik va yillik tushum faqat reyestrning mijoz tushumi yozuvlari yig‘indisidir. Tasdiqlangan qaytarishlar manfiy yozuv sifatida tushumni kamaytiradi. Haftaning boshi dushanba; sana `Asia/Tashkent` vaqt zonasidagi operatsiya yakuniy tasdiqlangan vaqtiga asoslanadi. Kutayotgan so‘rov, loyiha byudjeti yoki kelishuvning o‘zi haqiqiy tushum hisoblanmaydi.

Hisoblangan daromad = loyiha ulushi + ish haqi + mukofot. Haqiqiy to‘lov alohida hisoblanadi. Qolgan qarzdorlik = hisoblangan − to‘langan. Kompaniya ulushi = mijoz tushumi − loyiha xodimlari ulushi. Sof foyda = kompaniya ulushi − ish haqi − mukofot − operatsion xarajat. Barcha hisob-kitoblar Decimal/PostgreSQL numeric bilan amalga oshiriladi; valyutalar aralashtirilmaydi.

Odatdagi hisobotlar boshlanish va tugash sanasi oralig‘ini, ikki kunni ham qo‘shgan holda oladi. Qarzdorlik va loyiha rentabelligi **tugash sanasi holatiga** butun tasdiqlangan tarixdan hisoblanadi; ularda boshlanish sanasi o‘chiriladi va bu qoida ochiq yoziladi. Rentabellik uchun o‘sha sanagacha tasdiqlangan so‘nggi kelishuv nusxasi olinadi. Keyingi tushum, to‘lov va kelishuvlar avvalgi sana natijasiga qo‘shilmaydi.

Loyiha, xodim va lavozim filtrlari birga ishlaydi. Tushum/kompaniya foydasi/xarajat hisobotlarida xodim yoki lavozim tanlash ularga bog‘liq loyihalarning to‘liq kompaniya hisobini ko‘rsatadi; izoh sahifada mavjud. Xodim daromadi, haqiqiy to‘lov, mukofot va qarzdorlikda esa aynan tanlangan xodim/lavozim hisoblanadi. Lavozim va bo‘lim — xodimning hozirgi lavozimi va bo‘limidir; loyiha foizlari tasdiqlangan tarixiy kelishuv nusxasidan olinadi.

Noto‘g‘ri sana, teskari davr, noma’lum hisobot/valyuta/eksport uchun filtrlarda xato ko‘rsatiladi va noto‘g‘ri hisob yoki fayl chiqarilmaydi. Bo‘sh jadval tasdiqlangan manba yo‘qligini bildiradi. Namunaviy pul yozuvi qo‘shilmaydi.

Hisoblash vaqtida PostgreSQL moliya yozuvchilarining ayni advisory lock kalitiga shared lock olinadi: bitta hisobotning turli qismlariga yangi moliyaviy amal aralashmaydi. Manbalarni ochish bo‘limida mos reyestr yozuvlarining UUID, summa va asl tarixiga havola mavjud. Dastlab oxirgi 30 manba ko‘rsatiladi.

CSV UTF-8 BOM, Excel haqiqiy XLSX, PDF haqiqiy Unicode PDF hisoblanadi. Matnli formula kiritishdan himoya mavjud. Excel 15 ta ahamiyatli raqamdan katta sonni aniq saqlay olmagani uchun bunday summa matn katagi sifatida eksport qilinadi; raqamlar yaxlitlab yo‘qotilmaydi. Barcha eksportlar `private, no-store` va yuklash audit yozuviga ega.

Tekshiruv: `apps.enterprise.tests.test_financial_reports` aniq tushum/ulush/to‘lov/ish haqi/mukofot/xarajat/qaytarish misollarini, sana holatini, valyuta va uch format mosligini tekshiradi. `SSB_REPORT_BROWSER=1` haqiqiy Edge brauzerida filtrlar, manbalar, Excel/PDF/CSV tugmalari, xato sana va mobil ko‘rinishni alohida test bazasida tekshiradi.

2026-11-03 yakuniy tekshiruv: barcha uchta brauzer/Windows sinovi yoqilgan umumiy to‘plamda 146 test o‘tdi; undan keyin qo‘shilgan Toshkent yarim tuni chegarasining alohida testi ham o‘tdi. Jami 147 ta tekshiruv. Dalillar `.setup/chat-finance-final-tests.log`, `.setup/financial-midnight-test.log`, `.setup/financial-reports-browser-result.json`, `.setup/chat-browser-result.json` va `.setup/windows-journey-result.json` ichida. Sinov ma’lumotlari ishlab turgan bazaga qo‘shilmagan.
