# Email va Telegram ulanishi

Haqiqiy yuborish uchun tashqi pochta hisobi va Telegram bot kerak. Ular hozir tayyor emas; loyihada ulangan deb ko‘rsatilmaydi.

## Email

Pochta provayderidan SMTP server, port, login va SMTP/app parolini oling. Maxfiy qiymatlarni faqat `.env` ga kiriting, Git yoki chatga yubormang:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=provayder-bergan-server
EMAIL_PORT=587
EMAIL_HOST_USER=sizning-manzilingiz
EMAIL_HOST_PASSWORD=provayder-bergan-parol
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=SSB Group <sizning-manzilingiz>
EMAIL_NOTIFICATIONS_ENABLED=True
```

465-portdagi implicit SSL ishlatilsa: `EMAIL_USE_SSL=True`, `EMAIL_USE_TLS=False`. Ikkalasini birga yoqmang. Yuboruvchi manzilni provayder tasdiqlashi kerak. Email qutisiga tushish provayder va domenning SPF/DKIM/DMARC sozlamalariga ham bog‘liq.

Server qayta ishga tushgach **Sozlamalar → Ulanishlarni sozlash va tekshirish** orqali serverni tekshiring. Profilga haqiqiy email kiriting va **O‘zimga sinov xati** tugmasini bosing. SMTP tekshiruvi serverga ulanishni tasdiqlaydi; xat qabulini sinov xati bilan tekshiring.

## Telegram

Telegramdagi rasmiy **@BotFather** orqali bot yarating: `/newbot` → bot nomi → `bot` bilan tugaydigan username. **Ulanishlar** sahifasining 1-qadamida tokenni kiriting va **Tokenni tekshirish va saqlash** tugmasini bosing. Token avval Telegram orqali tekshiriladi, keyin mavjud `.env` faylida saqlanadi; qolgan sozlamalar saqlanadi. Token sahifaga qaytarilmaydi, auditga yozilmaydi. Bot nomi avtomatik aniqlanadi. Serverni qayta yoqish kerak emas.

Muqobil ravishda serverda qo‘lda sozlash ham mumkin:

```dotenv
TELEGRAM_BOT_TOKEN=BotFather-bergan-token
TELEGRAM_BOT_USERNAME=bot_username
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

2-qadamda har bir xodim o‘z hisobida **Telegramda botni ochish** tugmasini bosadi. Chiqqan havola orqali botga o‘tib **Start / Boshlash** bosiladi. Sahifaga qaytib **Start bosdim — tekshirish**, keyin 3-qadamda **Telegramimga sinov yuborish** bosiladi. O‘rnatilgan token yoki namunaviy token sahifada ochiq ko‘rsatilmaydi; yo‘riqnomadagi soxta misol haqiqiy token o‘rnini bosa olmaydi.

Username orqali bildirishnoma yuborilmaydi: chat ID bir martalik, 10 daqiqalik token orqali haqiqiy shaxsiy chatga bog‘lanadi. Guruhlarda ulash qabul qilinmaydi. Har bir Telegram chat faqat bitta xodimga bog‘lanadi. `/stop` yoki sahifadagi **Hisobni uzish** orqali o‘chiriladi. Token/bot almashsa hisobni qayta bog‘lash kerak.

Bot boshqa tizimda webhook bilan ishlayotgan bo‘lsa, polling bilan to‘qnashadi. Faol webhookni tekshirmasdan avtomatik o‘chiradigan kod qo‘shilmadi.

## Yetkazish ishchisi

```powershell
.\.venv\Scripts\python.exe manage.py run_notification_worker
# Bir martalik tekshirish/yuborish:
.\.venv\Scripts\python.exe manage.py run_notification_worker --once
```

Ulanish sahifasi ochilganda yoki yangi tashqi bildirishnoma navbatga qo‘yilganda, haqiqiy kanal sozlangan bo‘lsa veb-server jarayonida fon yetkazish ishchisi boshlanadi. U bot Start so‘rovlarini va xabar navbatini har 10 soniyada tekshiradi. Server yopilsa shu fon ishchisi ham to‘xtaydi; bu Windows scheduled task emas. Yuqoridagi alohida buyruq production xizmat boshqaruvchisi bilan ishlatish uchun saqlangan. Parallel ishchilar DB qulf va noyoblik qoidalarini ishlatadi. Hech qanday Windows avtomatik vazifasi o‘rnatilmadi. Pochta yoki bot hali sozlanmagan bo‘lsa tarmoqqa chiqadigan fon ishchisi boshlanmaydi.

Ilova ichidagi bildirishnoma va tashqi yetkazish navbati bitta DB tranzaksiyasida yoziladi. Tashqi tarmoq so‘rovi asosiy amal ichida yuborilmaydi. Har xabar/kanal uchun bitta navbat yozuvi bor; ishchilar bir yozuvni bir vaqtda olmaydi. Xatoda 2, 4, 8, 16 daqiqadan keyin qayta uriniladi; beshinchi xatodan keyin “failed”. Yetkazish holati foydalanuvchiga ko‘rinadi. Kanal yoki foydalanuvchi o‘chirilsa, yoxud bildirishnoma turi o‘chirilgan bo‘lsa navbat bekor qilinadi. Shaxsiy chat xabarlari tashqi kanallarga ko‘chirilmaydi.

SMTP yoki Telegram so‘rovini tashqi server qabul qilib, javob tarmoqda yo‘qolsa, qayta urinish tashqi tomonda takroriy xabar berishi mumkin. Tashqi xizmat uchun mutlaq exactly-once va 100% yetkazish kafolati yo‘q. Asosiy ilova bildirishnomasi saqlanib qoladi.

Rasmiy manbalar: [Django email](https://docs.djangoproject.com/en/5.2/topics/email/), [Telegram Bot API](https://core.telegram.org/bots/api), [Telegram deep links](https://core.telegram.org/bots/features#deep-linking).
