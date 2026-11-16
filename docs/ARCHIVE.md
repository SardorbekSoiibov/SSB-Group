# Umumiy loyiha arxivi

Menyu: **Kompaniya → Xavfsiz arxiv**, manzil `/management/enterprise/archives/`.

## Ikki bosqichli himoya

**1-bosqich — bo‘limga kirish kodi.** Kod sahifa ustidagi modal oynada so‘raladi; Esc bilan yopilmaydi, undan chiqish “Bosh sahifaga qaytish” havolasi orqali. Orqa fon bezak bo‘lib, unda arxiv ma’lumoti yo‘q. Asoschi kodni shu modalda yoki bo‘lim ichidagi “Kodni yangilash” tugmasi orqali almashtiradi. Kod butun kompaniya uchun bitta, uni faqat Asoschi shu sahifada o‘rnatadi yoki yangilaydi. Bazada faqat xeshi saqlanadi. Kod har tashrifda so‘raladi: boshqa sahifaga o‘tilganda `ArchiveVisitMiddleware` ruxsatni bekor qiladi. Arxiv ichidagi sahifalar, sahifani yangilash va fondagi so‘rovlar (bildirishnomalar, API) tashrifni tugatmaydi. Ruxsat ko‘pi bilan 1 soat amal qiladi. Kod yangilansa, barcha ochiq ruxsatlar bekor bo‘ladi. Bir hisob uchun 15 daqiqada 8 ta noto‘g‘ri urinishdan keyin kirish vaqtincha yopiladi.

**2-bosqich — yuklab olishda misol.** “Yuklab olish” tugmasi misol modalini ochadi (masalan `7 × 4 = ?`). Fayl yuborila boshlaganda server tasdiq cookie’sini qo‘yadi va modal “Yuklab olish boshlandi” holatiga o‘tadi. To‘g‘ri javobdan keyingina fayl beriladi. Javob faqat serverdagi sessiyada saqlanadi, misol bitta faylga bog‘langan, 5 daqiqa amal qiladi va har bir javobdan keyin bekor bo‘ladi: noto‘g‘ri javobda yangi misol beriladi. Noto‘g‘ri javob audit jurnaliga yoziladi.

## Fayllar

Koddan o‘tgan har bir faol xodim kompaniyaning barcha loyihalarini ko‘radi va o‘z loyihasini qo‘shadi. Faqat `.rar` va `.zip` qabul qilinadi. Loyiha nomi qo‘lda yoziladi, muallif sifatida yuklagan xodim ko‘rsatiladi. Yuklashda arxiv tuzilmasi va (ulangan bo‘lsa) antivirus tekshiriladi, yuklab olishda SHA-256 yaxlitligi tekshiriladi. Fayllar ochiq URL orqali berilmaydi.

## O‘chirish

Loyihani faqat uning muallifi yoki Asoschi, bo‘lim kodi kiritilgan holda o‘chiradi. Ikki bosqich: nima o‘chishi ko‘rsatiladi, keyin parol so‘raladi. Yozuv va fayl bazadan butunlay o‘chadi, buni qaytarib bo‘lmaydi; Audit tarixida faqat o‘chirilgani haqida qator qoladi.

## Tekshiruv

`apps.enterprise.tests.test_archive_access` — kod, tashrif, misol, muallif va fayl qoidalari. `SSB_ARCHIVE_BROWSER=1` — haqiqiy Edge brauzerida to‘liq oqim, jumladan bayt-baytga mos yuklab olish. Haqiqiy RAR fayl avtomatik sinovda ishlatilmagan (sinov ZIP bilan bajariladi).
