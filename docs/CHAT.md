# Xodimlar chati

Menyu: **Ish maydoni → Xodimlar chati**, manzil `/management/chat/`.

Faol xodimni ism yoki lavozim bo‘yicha topib, shaxsiy suhbat ochiladi. Enter xabar yuboradi; Shift + Enter yangi qator ochadi. Xabar uzunligi 4000 belgigacha. Suhbat oynasi ochiq va faol bo‘lsa, yangi xabarlar har 3 soniyada olinadi. Xabarni qabul qilgan xodim suhbatni ochgach “O‘qildi” belgisi yangilanadi. Menyudagi son o‘qilmagan chat xabarlarini bildiradi. Yangi xabar bildirishnomalar markaziga ham tushadi; profil sozlamasida “Chat xabari” o‘chirilsa, bildirishnoma o‘chadi, yozishmaning o‘zi saqlanadi.

Oxirgi 50 xabar dastlab yuklanadi, oldingi tarix alohida tugma bilan ochiladi. Yangi xabarlar ID kursori bilan ketma-ket olinadi. Internet uzilganda matn oynada qoladi, qayta yuborish ayni UUID bilan bajariladi va server nusxa yaratmaydi. Sahifa yangilanganda joriy qoralama shu brauzer sessiyasida, foydalanuvchi va suhbatdoshga alohida saqlanadi. Xabarlar PostgreSQL bazasida saqlanadi; xodim faolsizlantirilganda eski tarix qoladi, unga yangi xabar yuborish bloklanadi.

Suhbat API faqat joriy foydalanuvchining juftligini tanlaydi. Asoschi ham boshqa ikki xodimning yozishmasini chat sahifasi/API orqali o‘qiy olmaydi. O‘qilganlik uchun POST, CSRF va ko‘rsatilgan xabar kursori tekshiriladi. Xabar matni HTML sifatida bajarilmaydi. Xabar va bildirishnoma bitta bazaviy tranzaksiyada yaratiladi.

Bu serverdan davriy so‘rov orqali ishlaydigan shaxsiy matnli chat. Alohida WebSocket/Redis yoki tashqi chat xizmati talab qilinmaydi. Windows ilovasi ham ayni serverdagi chatni ochadi. Ilova yopiq holatda tashqi push xizmati yo‘q; Windows tizim bildirishnomalari operatsion tizim ruxsatlariga bog‘liq.

Sxema: `chat/0001_initial` va `notifications/0002_alter_notification_kind`. Mavjud hisoblar, parollar va moliyaviy yozuvlar o‘chirilmaydi.

Tekshiruvlar: `apps.chat.tests.test_chat` — maxfiylik, rollar, CSRF, takror yuborish, kursordan olish, o‘qilganlik, faolsiz hisob, xabar matni. `SSB_CHAT_BROWSER=1` bilan ikki haqiqiy Edge sessiyasi o‘rtasida xabar/javob, o‘qilganlik, eski tarix, internet uzilishi, qayta yuborish, saqlanish va mobil ko‘rinish tekshiriladi. Windows sinovi `SSB_WINDOWS_JOURNEY=1` bilan vebdan ilovaga va ilovadan vebga chat xabarini tekshiradi. Hammasi alohida test bazasida bajariladi.

## Telegram uslubidagi imkoniyatlar (2026-11-04)

Xabar ustida o‘ng tugma, uzoq bosish yoki `⋯` menyu ochadi: javob berish, matnni nusxalash, tahrirlash (48 soat ichida), qadash, uzatish, yuklab olish, hamma uchun o‘chirish va 8 ta reaksiya. Ikki marta bosish javob beradi; ↑ oxirgi xabarni tahrirlaydi; Esc bekor qiladi.

Rasm va fayllarni tugma, sudrab tashlash yoki joylash (paste) bilan yuborish mumkin. Turi va hajmi vazifa ilovalari bilan bir xil sozlamalardan olinadi. Haqiqiy PNG/JPEG/WEBP rasm suhbatda ko‘rinadi; SVG hech qachon sahifada ochilmaydi, faqat yuklab olinadi. Fayllarni faqat suhbat ishtirokchilari ochadi. O‘chirilgan xabarning matni va fayli serverdan ham o‘chiriladi; uzatilgan nusxa alohida fayl bo‘lib qoladi.

Shuningdek: onlayn/oxirgi faollik, “yozmoqda…”, ✓/✓✓, sana ajratgichlari, “Yangi xabarlar” chizig‘i, suhbat ichida qidirish va eski xabarga sakrash, pastga tushish tugmasi, emoji paneli. Tahrir, o‘chirish, reaksiya va qadash ochiq suhbatga `since` kursori orqali keyingi so‘rovda yetib boradi.

Barcha vaqtlar kompaniya vaqt zonasi (`TIME_ZONE`) bo‘yicha ko‘rsatiladi, “Bugun/Kecha” server soatidan hisoblanadi: xodim kompyuterining vaqt zonasi natijaga ta’sir qilmaydi.

Hozircha yo‘q: guruh suhbatlari, kanallar, ovozli xabar va qo‘ng‘iroqlar. Tizim hali ham davriy so‘rovda ishlaydi (3 soniya), WebSocket yo‘q.

Sxema: `chat/0002_telegram_features` (faqat qo‘shimcha). Testlar: `apps.chat.tests.test_messenger`, `SSB_MESSENGER_BROWSER=1` bilan `test_messenger_browser`.
