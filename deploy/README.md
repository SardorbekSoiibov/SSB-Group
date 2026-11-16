# SSB Group — ssbgroup.uz

## 1 marta: domenni ulash
**`ULASH.bat`** ni ikki marta bosing va ekrandagini bajaring:

1. Domen hali Cloudflare'da bo'lmasa — brauzer ochiladi: bepul ro'yxatdan o'ting,
   **Add a domain → ssbgroup.uz → Free**. Cloudflare bergan **2 ta nameserver**ni
   domen olgan saytingiz panelida (DNS serverlar / NS) eskilari o'rniga yozing.
   *(Bu yagona qo'lda qilinadigan ish — .uz registrator panelini dastur boshqara olmaydi.)*
2. Brauzerda Cloudflare ruxsat sahifasi ochiladi → **ssbgroup.uz** → **Authorize**.
3. Qolganini dastur o'zi qiladi: tunnel yaratadi, `ssbgroup.uz` va `www.ssbgroup.uz`
   yozuvlarini qo'shadi va saytni yoqishni taklif qiladi.

Nameserverlar 1–24 soatda kuchga kiradi. Shundan keyin https://ssbgroup.uz ochiladi.

## Har kuni
| Tugma | Vazifasi |
|---|---|
| `start.bat`  | Saytni yoqadi va brauzerda ochadi |
| `stop.bat`   | Saytni o'chiradi |
| `status.bat` | Ishlayaptimi — ko'rsatadi |

Kompyuter o'chsa yoki uxlasa, sayt ham ishlamaydi (Windows: Uyqu rejimi → Hech qachon).

## Muammo bo'lsa
- **Error 1033** — tunnel ishlamayapti: `stop.bat` → `start.bat`; bo'lmasa `ULASH.bat` ni qayta bosing.
- **DNS_PROBE / sayt topilmadi** — nameserverlar hali kuchga kirmagan, kuting.
- **Server javob bermadi** — `logs\server-error.log`.

## Xavfsizlik
- Domen rejimida DEBUG o'chiq, cookie'lar faqat HTTPS, HSTS yoqilgan.
- Server faqat 127.0.0.1 da tinglaydi — tashqaridan faqat Cloudflare orqali kiriladi.
- Kalitlar: `%USERPROFILE%\.cloudflared\` — hech kimga bermang.
