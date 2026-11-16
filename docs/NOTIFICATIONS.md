# Bildirishnomalar

## Ishlash tartibi

Vazifa biriktirilishi, izoh, tekshiruvga topshirish, tekshiruv natijasi, loyiha holati, yangi murojaat, e’lon, moliyaviy tasdiq/to‘lov, arxiv fayli, ish jadvali va tasdiqlangan baholash tegishli xodimlarga bazada saqlanadigan xabar yaratadi. O‘z amalingiz haqidagi xabar ayrim jarayonlarda o‘zingizga qayta yuborilmaydi. Profil sozlamalarida o‘chirilgan xabar turlari yuborilmaydi.

Kabinetning yuqorisidagi qo‘ng‘iroq o‘qilmagan xabarlar sonini ko‘rsatadi. Faol veb sahifa serverni har 15 soniyada tekshiradi. Yangi xabar bosiladigan qisqa xabar sifatida chiqadi. Qo‘ng‘iroq xabarlar markazini ochadi; xabar sarlavhasini bosish uni o‘qilgan deb belgilab, tegishli sahifani ochadi. Barchasini birgalikda o‘qilgan deb belgilash va o‘qilmaganlarini filtrlash mumkin. Boshqa sessiyada o‘qilgan xabar keyingi tekshiruvda hisoblagichdan tushadi.

Windows 2.0.5 ilovasi tizim bildirishnomalarini har 20 soniyada tekshiradi. Ilovaga dastlab kirilganda eski xabarlar qaytadan qalqib chiqmaydi, ammo qo‘ng‘iroqda va xabarlar markazida qoladi. Keyingi yangi xabarlar Windows bildirishnomasi sifatida chiqariladi. Oyna yoki ilova yopilgan paytda tashqi push xizmati ishlamaydi. Windows bildirishnomalari va ovozi operatsion tizimdagi ruxsatlar, ovoz va bezovta qilmaslik rejimiga bog‘liq. Veb sahifa majburiy ovoz ijro etmaydi.

Internet uzilsa saqlangan xabarlar yo‘qolmaydi. Qayta ulanishda oxirgi olingan xabardan davom etiladi. Ko‘p xabar birdan yaratilsa ular kursor orqali bo‘lib olinadi; faqat oxirgi 20 ta bilan cheklanmaydi. Xabar matni HTML sifatida bajarilmaydi. Har bir foydalanuvchi faqat o‘z xabarlarini ko‘radi va o‘qilgan deb belgilaydi; o‘zgartiruvchi amallar CSRF bilan himoyalangan.

## Muddatlar

Kabinet yoki Windows ilovasi ochiq bo‘lganda yaqinlashgan/o‘tgan muddatlar avtomatik tekshiriladi, ko‘pi bilan daqiqada bir marta. Yaqin muddat chegarasi boshqaruv sozlamalaridan olinadi. Vazifa ijrochisi, muddati o‘tgan vazifada esa loyiha rahbari ham xabar oladi. Tugatilgan, arxivlangan yoki bekor qilingan loyiha bo‘yicha yangi eslatma yaratilmaydi. Bir kun ichida ayni eslatma takrorlanmaydi.

Hech kim tizimga kirmagan paytda ham kunlik eslatmalarni yaratish uchun server jadvaliga `python manage.py send_deadline_reminders` qo‘yiladi. Buyruqni takroran bajarish o‘sha kunning xabarlarini ko‘paytirmaydi. Operatsion tizim scheduler vazifasi ushbu tuzatishda yaratilmagan.

## Tekshiruv — 2026-11-03

- Server: 126 testdan 125 tasi o‘tdi, alohida Windows testi odatiy to‘plamda o‘tkazib yuborildi; keyin haqiqiy yig‘ilgan Windows ilovasida alohida ishga tushirilib o‘tdi.
- Edge: 8 holat o‘tdi — dastlab eski xabarni qayta chiqarmaslik, avtomatik hisoblagich, xavfsiz matn, uzilishdan tiklanish, kursorni saqlash, boshqa sessiyadan o‘qish, keyingi paketni olish, sessiya tugashi.
- Server sinovlari: 235 xabarli oqim, foydalanuvchilar izolyatsiyasi, CSRF, tranzaksiya rollback, takrorlardan himoya, noto‘g‘ri havolalar, bekor qilingan loyihalar, kunlik eslatmalar va filtrlar.
- Windows: boshqa foydalanuvchi yuborgan e’lonning real kabinetga kelishi va o‘qilgach hisoblagichdan tushishi tekshirildi. Operatsion tizim qalqib chiquvchi oynasi/ovozining har bir Windows sozlamasida chiqishi avtomatik kafolatlanmaydi.

Dalillar: `.setup/notification-regression-tests.log`, `.setup/notification-windows-tests.log`, `.setup/notification-browser-result.html`, `.setup/windows-journey-result.json`.
