<div align="center">

# STARTUM Enterprise

### One Center. Multiple Directions. One Connected Education Platform.

**STARTUM** — o‘quvchilar, ustozlar, administratorlar va ta’lim markazi faoliyatini yagona raqamli muhitda birlashtirish uchun ishlab chiqilgan ta’lim platformasi.

[Website](#-ommaviy-veb-sayt) · [Admin Panel](#-website-admin-panel) · [Telegram Bot](#-telegram-bot) · [Installation](#-ishga-tushirish) · [API](#-api-va-integratsiya) · [Security](#-xavfsizlik) · [Roadmap](#-mavjud-cheklovlar-va-keyingi-rivojlantirish)

</div>

---

## Loyiha haqida

STARTUM Enterprise ta’lim markazining ommaviy sayti, ariza qabul qilish jarayoni, administrator boshqaruvi va Telegram orqali ishlaydigan ta’lim xizmatlarini bir-biriga bog‘laydi.

Loyiha quyidagi asosiy qismlardan tashkil topgan:

- **Public Website** — markaz, fanlar, maxsus dasturlar, ustozlar, ta’lim tizimi, jadval, FAQ va ariza formasi haqida ma’lumot beruvchi sayt.
- **FastAPI Backend** — sayt va Admin Panel uchun REST API, server-side validatsiya, autentifikatsiya va biznes qoidalari.
- **Website Admin Panel** — arizalar, foydalanuvchilar, kurslar, ustozlar, guruhlar, materiallar, kalendar va tizim faoliyatini boshqarish interfeysi.
- **Telegram Bot** — o‘quvchi va ustoz kabinetlari, administrator buyruqlari, ta’lim jarayonlari va xabarnomalar.
- **SQLite Database** — foydalanuvchilar, administratorlar, kurslar, arizalar, o‘quv materiallari va ta’lim jarayoniga oid ma’lumotlar uchun yagona ma’lumotlar ombori.

> **Muhim:** repository source code va konfiguratsiya namunalarini o‘z ichiga oladi. Production domeni, haqiqiy Telegram tokeni, administrator parollari va faol ma’lumotlar bazasi alohida, mas’ul egasi tomonidan sozlanadi. Kodda mavjud bo‘lgan har bir modul ishlab chiqarish muhitida to‘liq tekshirilgan degani emas. Holatlar quyida ochiq ko‘rsatilgan.

## Mundarija

- [Asosiy imkoniyatlar](#-asosiy-imkoniyatlar)
- [Ommaviy veb-sayt](#-ommaviy-veb-sayt)
- [Qidiruv va kurs katalogi](#-qidiruv-va-kurs-katalogi)
- [Ariza topshirish](#-ariza-topshirish-va-qabul-jarayoni)
- [Website Admin Panel](#-website-admin-panel)
- [Telegram Bot](#-telegram-bot)
- [Ta’lim platformasi modullari](#-taлим-platformasi-modullari)
- [Til, dizayn va mobil qo‘llab-quvvatlash](#-til-dizayn-va-mobil-qo‘llab-quvvatlash)
- [Texnologiyalar](#-texnologiyalar)
- [Loyiha tuzilishi](#-loyiha-tuzilishi)
- [Ishga tushirish](#-ishga-tushirish)
- [Environment sozlamalari](#-environment-sozlamalari)
- [Admin hisobini tayyorlash](#-admin-hisobini-tayyorlash)
- [API va integratsiya](#-api-va-integratsiya)
- [Ma’lumotlar bazasi va migratsiyalar](#-ma’lumotlar-bazasi-va-migratsiyalar)
- [Test va sifat nazorati](#-test-va-sifat-nazorati)
- [Xavfsizlik](#-xavfsizlik)
- [Deploy va saytni egasiga topshirish](#-deploy-va-saytni-egasiga-topshirish)
- [Mavjud cheklovlar va keyingi rivojlantirish](#-mavjud-cheklovlar-va-keyingi-rivojlantirish)
- [Muammolarni bartaraf etish](#-muammolarni-bartaraf-etish)
- [Hissa qo‘shish](#-hissa-qo‘shish)

---

## ✨ Asosiy imkoniyatlar

| Yo‘nalish | Imkoniyatlar | Koddagi holat |
|---|---|---|
| Ommaviy sayt | Ko‘p bo‘limli responsive website | Mavjud; production domenida alohida tekshiriladi |
| Ko‘p tillilik | Uzbek, Russian, English | Tarjima lug‘atlari va til almashtirish mavjud; barcha yangi matnlar tarjima auditidan o‘tishi kerak |
| Tema | Light Mode va Dark Mode | Mavjud; brauzer va qurilma bo‘yicha vizual QA tavsiya qilinadi |
| Kurs katalogi | Faol kurslar va maxsus dasturlarni backenddan olish | API mavjud; ishlab chiqarish katalogi DB ma’lumotlariga bog‘liq |
| Qidiruv | Kurs, ustoz va e’lon qilingan public materiallar | Qisman: news qidiruvi uchun tasdiqlangan model yo‘q |
| Arizalar | Forma, backend validatsiya, duplicate/rate-limit himoyasi, status tracking | Kodda mavjud; production DB va Telegram yetkazilishi alohida tasdiqlanadi |
| Website Admin | Login, sessiya, role guard, ariza va katalog boshqaruvi | Mavjud; ayrim ta’lim modullari qisman |
| Telegram Bot | User, admin, teacher va owner yo‘nalishlari | Router va handlerlar mavjud; live Telegram sinovi talab qilinadi |
| Xabarnomalar | Database-backed outbox va retry | Mavjud; real bot token bilan yetkazilish tekshirilishi kerak |
| Ta’lim modullari | Guruhlar, materiallar, homework, attendance, quiz, progress | Qisman; to‘liq LMS deb hisoblanmaydi |
| PWA | Manifest, service worker, offline sahifa | Qisman; offline/install tajribasi real browserda tasdiqlanishi kerak |
| Hisobot | CSV export | Route darajasida mavjud; XLSX eksport yo‘q |

## 🌐 Ommaviy veb-sayt

Sayt foydalanuvchiga STARTUM markazini tanishtiradi, ta’lim yo‘nalishlarini ko‘rsatadi va markaz bilan bog‘lanish yoki ariza yuborish imkonini beradi.

### Sayt bo‘limlari

| Bo‘lim | Anchor | Mazmuni |
|---|---|---|
| Bosh sahifa / Hero | `#home` | STARTUM brendi, asosiy xabar, vizual material va tezkor faktlar |
| Asosiy fanlar | `#subjects` | Fanlar katalogi, qidiruv, qidiruv turi, saralash va kategoriya filtrlari |
| Maxsus dasturlar | `#special` | IELTS/CEFR, milliy sertifikat, maktabga tayyorlov va boshqa maxsus yo‘nalishlar |
| Ustozlar | `#teachers` | Ustoz profillari va ular haqidagi ma’lumotlar |
| Ta’lim tizimi | `#system` | STARTUM ta’lim jarayoni va metodik yondashuvining bosqichlari |
| Biz haqimizda | `#about` | Markaz yondashuvi, maqsad va o‘quv jarayoni haqida ma’lumot |
| Yo‘nalish tanlash / FIT | `#fit` | Foydalanuvchiga mos ta’lim yo‘lini aniqlashga yordam beruvchi interaktiv blok |
| Jadval | `#schedule` | Akademik kalendar va e’lon qilingan tadbirlar |
| Natijalar | `#results` | Sayt tarkibidagi natija va progress haqida taqdimot bo‘limi |
| Manzil | `#location` | Markaz joylashuvi va aloqa ma’lumotlari |
| FAQ | `#faq` | Ko‘p beriladigan savollar va javoblar |
| Ariza / Aloqa | `#contact` | Ariza yuborish formasi va aloqa kanallari |
| Maxfiylik siyosati | `privacy.html` | Shaxsiy ma’lumotlardan foydalanish haqida e’lon qilingan siyosat |

### Foydalanuvchi saytdan qanday foydalanadi?

1. Saytni ochadi va o‘ziga qulay tilni tanlaydi.
2. Light/Dark ko‘rinishidan foydalanadi.
3. Asosiy fanlar yoki maxsus dasturlarni ko‘radi.
4. Qidiruv va kategoriyalar orqali mavjud yo‘nalishni izlaydi.
5. Ustozlar, ta’lim tizimi, jadval, manzil va FAQ bilan tanishadi.
6. Ariza formasiga ism-familiya, telefon, mavjud bo‘lsa Telegram username va tanlangan yo‘nalishni kiritadi.
7. Arizani yuboradi va serverdan qaytgan natijani ko‘radi.

Saytda ko‘rsatiladigan faol yo‘nalishlar katalogi backenddagi ma’lumotlarga bog‘liq. Katalogni o‘zgartirishdan oldin Admin Panel orqali boshqarish imkoniyatlari va tegishli ruxsatlarni tekshirish lozim.

## 🔎 Qidiruv va kurs katalogi

Katalog qidiruvi quyidagi boshqaruv elementlarini o‘z ichiga oladi:

- **Qidiruv maydoni** — fan yoki kurs nomi va mavjud kalit so‘zlar bo‘yicha izlash.
- **Qidiruv turi** — `Barchasi`, `Fanlar`, `Kurslar`.
- **Saralash** — tavsiya etilgan/relevance va alifbo bo‘yicha. `Yangi qo‘shilganlar` faqat real `created_at` ma’lumoti mavjud bo‘lsa ko‘rsatilishi mumkin.
- **Kategoriyalar** — aniq fanlar, tillar, gumanitar yo‘nalishlar va maxsus dasturlar.
- **Tozalash** — qidiruv va filtrlarni dastlabki holatga qaytarish.

Qidiruv matnni normallashtirish va case-insensitive moslashtirishdan foydalanadi. Global qidiruv API kurslar, ustozlar va e’lon qilingan umumiy materiallarni qo‘llab-quvvatlaydi.

**Ma’lumot cheklovlari:** joriy `courses` sxemasida tasdiqlangan `price` ustuni va alohida `packages` jadvali yo‘q. Shu sababli narx bo‘yicha saralash yoki mavjud bo‘lmagan paketlarni ko‘rsatish mumkin emas. Kurslar va maxsus dasturlar `courses` yozuvlaridagi `kind` qiymati orqali farqlanadi.

Koddagi boshlang‘ich katalogda asosiy fanlar va maxsus dasturlar uchun seed ma’lumotlar mavjud. Ishlab chiqarish saytidagi yakuniy ro‘yxat esa faol database yozuvlari bilan belgilanadi; README’dagi yoki source ichidagi seed ro‘yxatni production katalogining kafolatlangan joriy nusxasi deb qabul qilmang.

## 📝 Ariza topshirish va qabul jarayoni

### Ariza formasi maydonlari

- Ism-familiya — majburiy.
- Telefon raqami — majburiy.
- Telegram username — ixtiyoriy; berilsa `@username` formatida.
- Yo‘nalish — server katalogidan keladigan faol kurslardan tanlanadi.
- Qisqa xabar — ixtiyoriy.

Eski clientlar yuborishi mumkin bo‘lgan `level` va `preferred_time` maydonlari API kontraktida moslik uchun qabul qilinadi; joriy soddalashtirilgan formadagi asosiy talablar bilan adashtirmang.

### Ariza oqimi

```text
Foydalanuvchi
    │
    ▼
Frontend form (frontend/script.js)
    │  POST /api/applications
    ▼
FastAPI validatsiya
    │  faol course slug tekshiruvi
    ▼
SQLite web_applications
    │
    ├── tracking token (bazada faqat hash)
    │
    └── notification_outbox
             │
             ▼
       Telegram retry worker
             │
             ▼
       Faol Telegram adminlar
```

Backend quyidagilarni bajaradi:

- Ism, telefon, Telegram username va til qiymatlarini tekshiradi.
- Yo‘nalishning faol kurs yozuviga mosligini tekshiradi.
- Qisqa muddat ichidagi takroriy arizalarni cheklaydi.
- IP fingerprint asosidagi rate-limit qo‘llaydi.
- Arizaga ID va kuzatuv kodi yaratadi; kuzatuv kodi bazada hash holida saqlanadi.
- Arizani saqlagandan keyin Telegram xabarini outbox navbatiga qo‘shadi.
- Telegram vaqtincha ishlamasa, ariza yozuvini o‘chirmaydi; navbat keyingi retry uchun saqlanadi.

### Ariza holatlari

Amaldagi asosiy statuslar:

- `new` — yangi ariza.
- `in_review` — ko‘rib chiqilmoqda.
- `contacted` — mijoz bilan bog‘lanilgan.
- `accepted` — qabul qilingan.
- `rejected` — rad etilgan.

Eski bazalardagi ayrim legacy qiymatlar migratsiya yoki moslik qoidalarida saqlanishi mumkin. Statuslarni qo‘lda SQL orqali o‘zgartirish tavsiya etilmaydi.

Ariza holatini foydalanuvchi kuzatuv kodi bilan `POST /api/application-status` endpointi orqali tekshirishi mumkin. Kuzatuv kodini ommaviy joyga joylamang.

## 🛡 Website Admin Panel

Admin Panel ommaviy sayt navigatsiyasiga qo‘shilmagan. U alohida yo‘l orqali ochiladi:

```text
http://127.0.0.1:8000/admin/
```

Admin API server tomonida sessiya va rol tekshiruvlarini bajaradi. Frontendda tugmani yashirishning o‘zi xavfsizlik chorasi hisoblanmaydi.

### Paneldagi bo‘limlar

| Bo‘lim | Vazifasi | Ruxsat eslatmasi |
|---|---|---|
| Umumiy | Tizim holati, asosiy statistika va xizmat diagnostikasi | Login talab qiladi |
| Arizalar | Sayt va botdan kelgan arizalarni ko‘rish, status, tarix va eksport | Administrator roli bo‘yicha |
| Murojaatlar | Foydalanuvchi xabarlari bilan ishlash | Ruxsat tekshiriladi |
| Foydalanuvchilar | Telegram foydalanuvchilarini qidirish va holatini boshqarish | Ruxsat tekshiriladi |
| Kurslar va ustozlar | Katalog yozuvlarini ko‘rish va tegishli CRUD amallari | CEO/Senior Admin uchun yozish amallari |
| Guruhlar | Ta’lim guruhlari va ustoz tayinlovlari | CEO/Senior Admin |
| O‘quv materiallari | Materiallarni ko‘rish, moderatsiya va faollik | Admin roli va tegishli qoidalar |
| Test natijalari | Quiz natijalarini ko‘rish | CEO/Senior Admin |
| Akademik kalendar | Tadbir yaratish, tahrirlash va e’lon qilish | CEO/Senior Admin |
| Telegram xabarlari | Notification navbati, holat va retry | CEO/Senior Admin |
| Amallar tarixi | Muhim admin amallarining audit yozuvlari | CEO/Senior Admin |
| Hisobot eksporti | Qo‘llab-quvvatlangan datasetlarni CSV eksport qilish | Dataset bo‘yicha cheklovlar mavjud |
| Administratorlar | Website admin hisoblari va Telegram admin takliflari | Faqat CEO |

### Website Admin rollari

Website Admin ushbu repository snapshotida quyidagi rollardan foydalanadi:

- **CEO** — asosiy web boshqaruv roli; administrator hisoblari va muhim tizim sozlamalariga kengaytirilgan huquq.
- **Senior Admin** — ruxsat etilgan asosiy boshqaruv bo‘limlari.
- **Junior Admin** — cheklangan boshqaruv imkoniyatlari.

### Telegram Bot rollari bilan farqi

Telegram Bot ichida OWNER/CEO, administrator, ustoz va o‘quvchi kabinetlari mavjud. **Telegram Bot taklifini qabul qilish avtomatik ravishda Website Admin loginini bermaydi.** Website Admin uchun alohida parol bilan himoyalangan hisob va tasdiqlangan bog‘lanish talab qilinadi.

Telegram admin takliflari OWNER tomonidan yaratiladi. Taklif yuborilgan foydalanuvchi aynan taklifdagi Telegram ID bilan botni `/start` qilganda Bot huquqi faollashishi mumkin. Bot va Website Admin bog‘lanishi alohida tekshiriladi.

### Parol va hisob xavfsizligi

- Login/parol serverda tekshiriladi.
- Parollar PBKDF2-SHA256 xesh ko‘rinishida saqlanadi.
- Sessiya cookie `HttpOnly` va `SameSite=Strict` himoyalariga ega.
- Production HTTPS’da `ADMIN_COOKIE_SECURE=true` talab qilinadi.
- Har bir admin API so‘rovida server-side role guard ishlaydi.
- Email orqali parol tiklash xizmati sozlanmagan. CEO va administrator parolini tiklash amallari hujjatlashtirilgan server/CEO jarayoni orqali bajariladi.

## 🤖 Telegram Bot

Loyihada **bitta mavjud aiogram bot** ishlatiladi. Bitta polling session va yagona backend database bilan ishlash ko‘zda tutilgan. Ikkinchi polling jarayonini parallel ishga tushirmang.

### Foydalanuvchi uchun asosiy buyruqlar

| Buyruq | Vazifasi |
|---|---|
| `/start` | Botni boshlash, til/taklif/foydalanuvchi oqimini ochish |
| `/help` | Yordam |
| `/profile` | Profil |
| `/student` | O‘quvchi kabineti |
| `/teacher` | Ustoz kabineti |
| `/calendar` | Akademik kalendar |
| `/notifications` | Shaxsiy bildirishnomalar |
| `/owner` | OWNER uchun yopiq kabinet |
| `/admin` | Administrator kabineti |

Telegramdagi haqiqiy buyruqlar ro‘yxati foydalanuvchi roli va botning `set_my_commands` sozlamasiga qarab farq qiladi.

### OWNER va administrator buyruqlari

- `/admins` — administratorlar ro‘yxati.
- `/add_admin TELEGRAM_ID senior_admin|junior_admin` — administrator taklifini yaratish (OWNER ruxsati bilan).
- `/remove_admin TELEGRAM_ID` — administrator huquqini bekor qilish/tasdiqlash oqimi.
- `/add_teacher` — ustoz profilini yaratish oqimi.
- `/add_teacher_manager` — ustozga tegishli boshqaruv vakolatini berish.
- `/remove_teacher_manager` — shu vakolatni olib tashlash.
- `/assign_teacher` yoki OWNER uchun mos tayinlov amallari — ustozni fan/guruhga bog‘lash.
- `/share_test TEST_ID CHAT_ID` — mavjud testni guruh bilan ulashish.
- `/assign_quiz` — testni guruhga tayinlash.
- `/announce` — uch tildagi e’lonni tayyorlash va tasdiqlash oqimi.
- `/owner_backup` — OWNER uchun shaxsiy chatda database backup olish.

Buyruqlar faqat tegishli ruxsatga ega rollarda ishlashi kerak. Telegram menu’dagi buyruqni ko‘rish server-side ruxsatni almashtirmaydi.

### Ta’lim kabinetlari

**O‘quvchi kabinetida** mavjud kod yo‘nalishlariga qarab:

- Guruhlar va guruhga qo‘shilish so‘rovi.
- E’lon qilingan o‘quv materiallari.
- Uy vazifalari va javob topshirish.
- Davomat yozuvlari.
- Tayinlangan testlar va natijalar.
- Progress ma’lumotlari.
- Bildirishnomalar va sozlamalar.
- Sertifikat yozuvlari (PDF/QR berish jarayoni to‘liq emas).

**Ustoz kabinetida** mavjud kod yo‘nalishlariga qarab:

- Biriktirilgan kurslar va guruhlar.
- O‘quv materialini yuborish/moderatsiyaga jo‘natish.
- Uy vazifasi yaratish.
- O‘quvchi topshiriqlarini ko‘rib chiqish.
- Davomat belgilash.
- Testni guruhga tayinlash.

Ushbu imkoniyatlarning hammasini har bir real hisobda yoqilgan deb qabul qilmang. Biriktirilgan guruh, kurs, moderator va role guard holati natijani belgilaydi.

## 🎓 Ta’lim platformasi modullari

`backend/database/education_schema.sql` va `backend/database/education_methods.py` ta’limga oid jadvallar va amallarni saqlaydi.

| Modul | Mavjud kod imkoniyati | Hozirgi cheklov |
|---|---|---|
| Guruhlar | Guruh yaratish, a’zolik, taklif kodi/so‘rovi | To‘liq LMS boshqaruv paneli emas |
| Ustoz tayinlovi | Ustozni kurs/guruhga biriktirish va bekor qilish | Barcha lifecycle UI to‘liq emas |
| O‘quv materiallari | Fayl/material yozuvlari, publish/moderatsiya holatlari | Public endpoint faqat e’lon qilingan umumiy materiallarni chiqaradi |
| Uy vazifalari | Topshiriq yaratish, yuborish va ko‘rib chiqish oqimlari | Kengaytirilgan baholash rubrikasi to‘liq emas |
| Davomat | Dars sessiyasi va davomat yozuvlari | To‘liq oylik hisobot va tuzatish UX’i qisman |
| Test/quiz | Single-choice savollar, test sessiyasi va urinishlar | Multi-select, erkin javob va rivojlangan test generatori mavjud emas |
| Progress | Davomat/topshiriq/test ma’lumotlariga tayangan yozuvlar | To‘liq analitik trend interfeysi emas |
| Akademik kalendar | E’lon qilingan tadbirlar, admin boshqaruvi va reminder queue | Live schedule/reminder yetkazilishi productionda tekshirilishi kerak |
| Bildirishnomalar | Telegram inbox, o‘qilgan holati, preferences/outbox | Web push yoki browser notification markazi yo‘q |
| Sertifikatlar | Certificate metadata/DB yozuvlari | PDF generator, QR public verifier va digital signature to‘liq emas |

## 🎨 Til, dizayn va mobil qo‘llab-quvvatlash

### Tillar

Ommaviy sayt va botda uchta til uchun tarjima lug‘atlari mavjud:

- O‘zbek — `uz`
- Русский — `ru`
- English — `en`

Yangi UI matni qo‘shilsa, barcha uch tarjima lug‘atiga kiritilishi kerak. Aralash tilli ko‘rinishlar tarjima auditida aniqlanishi lozim.

### STARTUM brend ranglari

| Rang | HEX | Maqsad |
|---|---|---|
| Deep Teal | `#123B46` | Asosiy brend rangi |
| Mint | `#A8F0D1` | Accent va asosiy CTA |
| Soft Background | `#F2F7F3` | Yorug‘ fon |
| Teal Accent | `#4CA9A1` | Ikkinchi darajali accent |

Asosiy shriftlar: **Onest** (sarlavhalar) va **Inter** (matn/UI). Sayt Light va Dark temalarni qo‘llaydi. Birinchi kirishda Light Mode asosiy ko‘rinish sifatida sozlangan.

### Responsive va PWA

- Vanilla CSS media query’lar bilan desktop, tablet va smartphone joylashuvlari.
- Touch-friendly navigatsiya, select, forma va modal komponentlari.
- `site.webmanifest`, `sw.js`, `offline.html` mavjud.
- Service worker faqat ommaviy shell va statik assetlarni keshlashi kerak; `/api`, `/admin`, authentication, private data va upload yo‘llari cache qilinmasligi ko‘zda tutilgan.
- PWA install va to‘liq offline funksionallik production browserda alohida tekshirilishi kerak.

### SEO va public sahifalar

`frontend/` ichida title/description, canonical, Open Graph/Twitter metadata, EducationalOrganization JSON-LD, `sitemap.xml` va `robots.txt` mavjud. Alohida til URL’lari va to‘liq `hreflang` arxitekturasi joriy snapshotda yo‘q.

## 🧰 Texnologiyalar

| Qatlam | Texnologiya | Vazifasi |
|---|---|---|
| Frontend | HTML5 | Sahifa va semantik komponentlar |
| Styling | CSS3 | Design system, responsive layout, Light/Dark themes |
| Frontend logic | Vanilla JavaScript | Interaktivlik, i18n, katalog, formalar, API integratsiyasi |
| Backend | Python 3.12 | Server-side biznes logika |
| REST API | FastAPI | Public va himoyalangan admin endpointlar |
| Telegram | aiogram 3.31.0 | Bitta Telegram bot va routerlar |
| Database | SQLite + aiosqlite | Ma’lumotlarni saqlash va async DB amallari |
| ASGI server | Uvicorn | FastAPI servisini ishga tushirish |
| Config | python-dotenv | `.env` sozlamalarini o‘qish |
| Tests | pytest, unittest, Node.js | Backend/frontend regression va acceptance testlar |

Frontend uchun alohida bundler yoki framework talab qilinmaydi. React, Next.js, Vue yoki Django ishlatilmaydi.

## 📁 Loyiha tuzilishi

```text
STARTUM-Enterprise/
├── README.md
├── .gitignore
│
├── frontend/
│   ├── index.html                 # Ommaviy sayt
│   ├── privacy.html               # Maxfiylik siyosati
│   ├── offline.html               # Offline fallback sahifa
│   ├── style.css                  # Asosiy stil qatlami
│   ├── design-system.css          # Design tokenlar va umumiy komponentlar
│   ├── premium-experience.css     # Premium vizual qatlam
│   ├── lightmode-aeline.css       # Light Mode vizual qatlami
│   ├── mobile-experience.css      # Mobil responsive qoidalar
│   ├── script.js                  # Frontend logika va API integratsiyasi
│   ├── startum.config.js          # Ommaviy frontend konfiguratsiyasi
│   ├── sw.js                      # Service worker
│   ├── site.webmanifest           # PWA manifest
│   ├── robots.txt
│   ├── sitemap.xml
│   └── assets/
│       ├── images/                # Hero, ustoz va boshqa rasmlar
│       ├── video/                 # Motion/video aktivlar
│       ├── favicon.svg
│       └── icon-*.png
│
├── backend/
│   ├── main.py                    # API + bitta Telegram bot lifecycle
│   ├── startup.py                 # API port/socket xavfsiz boshqaruvi
│   ├── api.py                     # FastAPI routes, auth, validators
│   ├── config.py                  # Environment konfiguratsiyasi
│   ├── .env.example               # Maxfiy bo‘lmagan namuna
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── create_admin_hash.py        # Web-admin parol hash generatori
│   ├── backup_db.py               # SQLite online backup vositasi
│   ├── admin_authorization.py      # Telegram/Web admin role resolver
│   ├── admin_commands.py
│   ├── notifications.py           # Outbox va xabar yetkazish
│   ├── user_moderation.py
│   ├── application_statuses.py
│   ├── education_access.py
│   ├── education_i18n.py
│   ├── database/
│   │   ├── db.py                  # SQLite schema, migrations, repository
│   │   ├── education_schema.sql   # Ta’lim modullari sxemasi
│   │   ├── education_methods.py
│   │   └── fsm_storage.py         # Persistent Telegram FSM
│   ├── handlers/
│   │   ├── user.py
│   │   ├── admin.py
│   │   └── education.py
│   ├── keyboards/
│   │   ├── common.py
│   │   └── admin.py
│   ├── states/
│   │   ├── user.py
│   │   ├── admin.py
│   │   └── education.py
│   ├── admin_panel/
│   │   ├── index.html
│   │   ├── admin.css
│   │   └── admin.js
│   └── tests/
│
├── docs/
│   ├── ARCHITECTURE_AND_FEATURE_MATRIX.md
│   ├── DEPLOYMENT_CHECKLIST.md
│   ├── BACKUP_AND_RECOVERY.md
│   ├── PRIVACY_AND_DATA_PROTECTION.md
│   ├── STARTUM_PHASE03_SYSTEM_ARCHITECTURE_2026-11-08.md
│   └── ...
│
├── reports/                      # Audit, QA va release hisobotlari
└── tests/                         # Root regression/acceptance testlari
```

> Papkalardagi ayrim fayllar keyingi release’da o‘zgarishi mumkin. Yuqoridagi tuzilma repository snapshoti uchun yo‘naltiruvchi xarita.

## 🚀 Ishga tushirish

### Talablar

- Windows 10/11, Linux yoki macOS.
- Python **3.12** tavsiya etiladi.
- Git.
- Node.js — frontend regression testlarini ishga tushirish uchun.
- Telegram bot tokeni — backend va botni birgalikda ishga tushirish uchun.

### 1. Repository’ni yuklab olish

```bash
git clone https://github.com/<GITHUB-OWNER>/STARTUM-Enterprise.git
cd STARTUM-Enterprise
```

Agar repository Private bo‘lsa, GitHub hisobingizga ruxsat berilgan bo‘lishi kerak.

### 2. Python virtual muhitini yaratish

**Windows PowerShell:**

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Agar PowerShell script policy virtual muhitni faollashtirishga ruxsat bermasa, faqat joriy terminal uchun:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Environment faylini tayyorlash

Backend papkasida:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

`.env` ichidagi majburiy va xavfsizlikka oid qiymatlarni [Environment sozlamalari](#-environment-sozlamalari) bo‘yicha to‘ldiring. Haqiqiy qiymatlarni README, issue, screenshot, chat yoki GitHub commit’ga yozmang.

### 4. Backend va Telegram botni ishga tushirish

Backend papkasida virtual muhit faol bo‘lgach:

```powershell
python main.py
```

`main.py` quyidagilarni bitta boshqariladigan jarayonda ishga tushiradi:

1. API portini oldindan band qiladi va ikkinchi instance’ni aniqlaydi.
2. Database initialize/migration bajaradi.
3. FastAPI/Uvicorn serverni ishga tushiradi.
4. Mavjud yagona aiogram bot polling session’ini ishga tushiradi.
5. Notification retry worker’ni boshqaradi.
6. Shutdown vaqtida task, socket va bot session’larini yopadi.

Default manzillar:

- API health: `http://127.0.0.1:8000/api/health`
- Public catalog: `http://127.0.0.1:8000/api/catalog`
- Website Admin: `http://127.0.0.1:8000/admin/`

**Muhim:** bir vaqtning o‘zida ikkinchi `python main.py` yoki ikkinchi Telegram polling process’ni ishga tushirmang.

### 5. Frontendni lokal ko‘rish

Yangi terminal oching. Loyiha root papkasida:

```powershell
python -m http.server 5500 --directory frontend
```

Brauzerda:

```text
http://127.0.0.1:5500
```

Lokal konfiguratsiya `frontend/startum.config.js` orqali `http://127.0.0.1:8000/api` manziliga murojaat qiladi. Backend boshqa portda ishlasa, frontend local API base URL’ini ham moslang.

Production’da frontend static server orqali beriladi; `/api` va `/admin` yo‘llari FastAPI’ga reverse proxy qilinishi kerak.

## ⚙️ Environment sozlamalari

Namuna fayl: `backend/.env.example`.

| O‘zgaruvchi | Vazifasi | Izoh |
|---|---|---|
| `BOT_TOKEN` | Telegram bot tokeni | Majburiy secret; BotFather’dan olinadi |
| `DATABASE_PATH` | SQLite fayl yo‘li | Default `startum.db`; nisbiy yo‘l backend papkasiga nisbatan |
| `CEO_OWNER_ID` | Bootstrap CEO Telegram ID | Majburiy musbat son |
| `OWNER_TELEGRAM_ID` | Asosiy OWNER Telegram ID | Bo‘sh bo‘lsa backward compatibility uchun CEO ID ishlatiladi |
| `BOT_USERNAME` | Ommaviy bot username | `@` belgisiz yoziladi; optional |
| `DEFAULT_LANGUAGE` | Standart til | `uz`, `ru` yoki `en` |
| `LOG_LEVEL` | Log darajasi | Odatda `INFO` |
| `API_HOST` | API bind host | Lokal default `127.0.0.1` |
| `API_PORT` | API port | Default `8000` |
| `CORS_ORIGINS` | Ruxsatli frontend originlar | Production’da faqat haqiqiy domainlar |
| `WEB_ADMIN_USERNAME` | Dastlabki web-admin login | Default namuna `admin`; release’da egasi belgilashi kerak |
| `WEB_ADMIN_PASSWORD_HASH` | Web-admin parol hash | Xom parol emas, hash yoziladi |
| `ADMIN_SESSION_SECRET` | Admin sessiya imzo siri | Kuchli random secret |
| `ADMIN_SESSION_TTL` | Sessiya muddati | Sekundlarda; config chegaralarini ko‘ring |
| `ADMIN_COOKIE_SECURE` | Secure cookie | Production HTTPS’da `true` bo‘lishi shart |
| `ADMIN_LOGIN_WINDOW_SECONDS` | Login urinish oynasi | Default `300` |
| `ADMIN_LOGIN_MAX_FAILURES` | Ruxsat etilgan xato urinishlar | Default `8` |
| `APP_ENV` | Muhit | `development`, `test` yoki `production` |

### Secret yaratish

Admin parol hashini yaratish:

```powershell
cd backend
python create_admin_hash.py
```

Skript parolni terminalda yashirin kiritadi, takroran so‘raydi va `WEB_ADMIN_PASSWORD_HASH` uchun PBKDF2-SHA256 hash chiqaradi. Chiqqan hashni `.env` ga joylang. Xom parolni README yoki kodga yozmang.

Session secret yaratish:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Natijani `ADMIN_SESSION_SECRET` ga yozing. Bu secret bilan admin parolini aralashtirmang.

`OWNER_TELEGRAM_ID` va `CEO_OWNER_ID` haqiqiy Telegram numeric ID bo‘lishi kerak. Ularni ommaviy repositoryga yozmang.

## 🔐 Admin hisobini tayyorlash

1. `backend/.env` ichida `WEB_ADMIN_USERNAME`, `WEB_ADMIN_PASSWORD_HASH` va `ADMIN_SESSION_SECRET` sozlangan bo‘lishi kerak.
2. `CEO_OWNER_ID` va `OWNER_TELEGRAM_ID` ni egasi bilan tekshiring.
3. Backendni birinchi marta ishga tushiring.
4. `http://127.0.0.1:8000/admin/` sahifasini oching.
5. Sozlangan login va xom parol bilan kiring.
6. Keyin boshqa administratorlarni faqat CEO boshqaruv oqimi orqali yarating yoki taklif qiling.

Telegram admin taklifi va Website Admin hisobi mustaqil xavfsizlik chegaralariga ega. Botga kirish taklifi Website Admin parolini bermaydi.

## 🔌 API va integratsiya

### Public API

| Method | Endpoint | Maqsad |
|---|---|---|
| `GET` | `/api/health` | Liveness/health javobi |
| `GET` | `/api/catalog` | Faol kurs va ustoz katalogi |
| `GET` | `/api/search` | Kurslar, ustozlar va public materiallar bo‘yicha qidiruv |
| `GET` | `/api/calendar` | E’lon qilingan akademik kalendar |
| `GET` | `/api/resources` | E’lon qilingan umumiy o‘quv materiallari |
| `POST` | `/api/applications` | Yangi ariza topshirish |
| `POST` | `/api/application-status` | Kuzatuv kodi bilan public ariza holatini ko‘rish |

Global search parametrlari kodi bo‘yicha `q`, `kind`, `language`, `sort`, `limit` va `offset` maydonlarini qo‘llab-quvvatlaydi. `kind`: `all`, `courses`, `teachers`, `materials`; `language`: `uz`, `ru`, `en`; `sort`: `relevance`, `newest`, `az`.

### Himoyalangan Admin API

Asosiy route oilalari:

- `/api/admin/login`, `/api/admin/logout`, `/api/admin/session`
- `/api/admin/overview`, `/api/admin/diagnostics`
- `/api/admin/applications`, `/api/admin/messages`
- `/api/admin/users`
- `/api/admin/catalog`, `/api/admin/courses`, `/api/admin/teachers`
- `/api/admin/resources`
- `/api/admin/education/groups`, ustoz tayinlovlari
- `/api/admin/calendar`
- `/api/admin/notifications`
- `/api/admin/accounts`, `/api/admin/telegram-admins`
- `/api/admin/audit`
- `/api/admin/export/*.csv`

Barcha admin endpointlarda cookie/session va server-side role guard talab qilinadi. Endpointlar ro‘yxati kod versiyasi bo‘yicha o‘zgarishi mumkin; to‘liq kontrakt uchun `backend/api.py` ni tekshiring. Development rejimida FastAPI docs ochiq bo‘lishi mumkin; production’da docs/OpenAPI endpointlari o‘chiriladi.

### Ma’lumot oqimlari

```text
Public Website ──────┐
                     ├── FastAPI ─── SQLite
Website Admin ───────┤      │
                     │      └── Notification Outbox
Telegram Bot ────────┘                 │
                                      ▼
                                Telegram API
```

Website va bot alohida nusxadagi ma’lumotlarni yuritmasligi, bir xil backend repository/database qoidalariga tayangan holda ishlashi ko‘zda tutilgan.

## 🗄 Ma’lumotlar bazasi va migratsiyalar

- DB: SQLite.
- Asosiy schema va repository: `backend/database/db.py`.
- Ta’lim sxemasi: `backend/database/education_schema.sql`.
- Joriy source snapshotdagi `Database.CURRENT_SCHEMA_VERSION`: **10**.
- Startup eski DB aniqlasa, sxema yangilanishidan oldin `backups/` ichiga SQLite online backup olib, `PRAGMA integrity_check` bilan tekshiradi.
- Migratsiyalar mavjud yozuvlarni saqlashga qaratilgan additive/compatibility amallaridan iborat. Har bir yangi schema o‘zgarishida versiyani ko‘tarish talab qilinadi.
- FSM (conversation state) yozuvlari SQLite’da saqlanadi; eskirgan holatlar 7 kundan keyin tozalanadi.

### Backup olish

Backend virtual muhiti ichida:

```powershell
python backup_db.py
```

Aniq fayl va chiqish yo‘li bilan:

```powershell
python backup_db.py --database startum.db --output backups/manual_pre_release.sqlite3
```

Backup/recovery bo‘yicha batafsil qo‘llanma: [`docs/BACKUP_AND_RECOVERY.md`](docs/BACKUP_AND_RECOVERY.md).

**Production bazasini GitHub’ga joylamang.** `.db`, `.sqlite`, `-wal`, `-shm` va backup nusxalari `.gitignore` orqali chiqarilgan. Backupni shifrlangan va cheklangan kirishli alohida joyda saqlang.

## 🧪 Test va sifat nazorati

### Development test paketlari

Backend papkasida:

```powershell
python -m pip install -r requirements-dev.txt
```

### Python testlari

```powershell
python -m pytest -q tests ../tests
```

Yoki unittest:

```powershell
python -m unittest discover -s ../tests -p 'test_*.py' -q
```

### Compile va JavaScript syntax

```powershell
python -m compileall -q .
node --check ../frontend/script.js
node --check admin_panel/admin.js
```

### Node regression testlari

Loyiha rootidan PowerShell:

```powershell
Get-ChildItem .\tests\*.test.cjs | ForEach-Object { node $_.FullName }
```

### Browser acceptance

```powershell
python tests/browser_acceptance.py
python tests/catalog_ui_acceptance.py
python tests/application_form_e2e_acceptance.py
python tests/mobile_design_restoration_acceptance.py
```

Browser testlar Playwright/Chromium mavjudligiga va test muhiti localhost’ga ulanishga ruxsat berishiga bog‘liq. `ERR_BLOCKED_BY_ADMINISTRATOR`, missing package yoki real DB yo‘qligi yuz bersa, test natijasi `BLOCKED` yoki `NOT TESTED` deb qayd etilishi kerak; buni `PASS` deb ko‘rsatmang.

### Test talqini

- **PASS** — aynan shu test muhiti va test ma’lumotlari bilan tekshiruv o‘tdi.
- **FAIL** — tekshiruv bajarildi va xato topildi.
- **BLOCKED** — dependency, DB, credential yoki muhit sabab bajarilmadi.
- **NOT TESTED** — test umuman bajarilmadi.
- **PENDING** — release oldidan bajarilishi kerak.

Statik test yoki mocked API testi real Telegram yetkazilishi, production DB integratsiyasi yoki haqiqiy qurilma sinovining o‘rnini bosmaydi.

## 🔒 Xavfsizlik

### Repository’da saqlanmasligi kerak bo‘lgan ma’lumotlar

- `.env` va boshqa secret fayllar.
- `BOT_TOKEN` va Telegram API credentiallari.
- Xom admin parollari va session secret.
- Haqiqiy foydalanuvchi/shogird ma’lumotlari mavjud SQLite DB.
- Database backup, `-wal`, `-shm` fayllari.
- Production loglari va maxfiy eksportlar.

### Amaldagi himoya qatlamlari

- PBKDF2-SHA256 password hash.
- HttpOnly/SameSite admin session cookie; production’da Secure.
- Login urinishlarini cheklash.
- O‘zgartiruvchi Admin API uchun origin/header va server role tekshiruvlari.
- Admin audit log.
- Public material endpointida faqat faol va e’lon qilingan umumiy materiallarni ko‘rsatish.
- Private Telegram `file_id` ni public API javobiga chiqarmaslik.
- Application duplicate va rate-limit nazorati.
- Notification outbox va duplicate prevention.
- Production rejimida FastAPI docs/OpenAPI o‘chirilishi va HTTPS cookie talabi.
- Service worker orqali private/API/admin javoblarini keshlamaslik.

### Privacy

Privacy matni `frontend/privacy.html` va `docs/PRIVACY_AND_DATA_PROTECTION.md` fayllarida. Bu hujjatlar yuridik muvofiqlik sertifikati emas. Ma’lumotlarni saqlash muddati, rozilik matni, voyaga yetmaganlar ma’lumotlari va rasmiy maxfiylik siyosati markaz mas’ullari/yuristi tomonidan tasdiqlanishi kerak.

## 🚀 Deploy va saytni egasiga topshirish

Production deploy oldidan quyidagilarni bajaring:

1. Python 3.12 va dependency versiyalarini serverda tekshiring.
2. `.env` ni serverning maxfiy konfiguratsiya joyida yarating.
3. `APP_ENV=production` qiling.
4. `ADMIN_COOKIE_SECURE=true` o‘rnating.
5. HTTPS sertifikat va reverse proxy sozlang.
6. `CORS_ORIGINS` ni faqat production originlar bilan cheklang.
7. SQLite fayli, backup katalogi va `.env` uchun file permissionlarni cheklang.
8. Production DB’dan mustaqil backup oling va checksum saqlang.
9. Backup nusxasida restore rehearsal bajaring.
10. `/api/health`, `/admin/` login va real ariza oqimini staging’da tekshiring.
11. Bitta bot polling process ishlayotganini tekshiring.
12. Telegram notification outbox retry’ni test qiling.
13. Mobile/desktop, keyboard, reduced-motion va Light/Dark testlarini o‘tkazing.
14. Log rotation, monitoring, alert va rollback rejasi tayyorlang.
15. Domen, telefon, Telegram kanal/bot username va manzil ma’lumotlarini sayt egasi bilan tasdiqlang.

Deploy checklist: [`docs/DEPLOYMENT_CHECKLIST.md`](docs/DEPLOYMENT_CHECKLIST.md).

### 8000-port band bo‘lsa (Windows)

Avval portni qaysi jarayon ishlatayotganini aniqlang:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  Select-Object LocalAddress, LocalPort, OwningProcess

Get-Process -Id <PID>
```

`<PID>` o‘rniga ko‘rsatilgan raqamni yozing. Jarayon STARTUM ekanini tasdiqlamasdan uni to‘xtatmang. Kerak bo‘lsa `API_PORT` ni bo‘sh portga o‘zgartiring va lokal frontend `startum.config.js` API manzilini ham moslang.

## ⚠️ Mavjud cheklovlar va keyingi rivojlantirish

Quyidagi bandlar ushbu source snapshotida to‘liq tayyor deb da’vo qilinmaydi:

- **Production deployment** — aniq domen, TLS, reverse proxy, monitoring va real server sozlamalari egasi/hosting tomonidan bajariladi.
- **Live Telegram runtime** — real bot token bilan polling va xabar yetkazilishi production/staging’da sinovdan o‘tishi kerak.
- **Production SQLite** — real `startum.db` repository’da bo‘lmasligi kerak; migration, backup va restore alohida production nusxada tekshiriladi.
- **Certificate delivery** — certificate metadata mavjud, lekin PDF generator, QR public verifier, digital signature va revocation verification to‘liq emas.
- **Payments** — to‘liq payment provider integratsiyasi va moliyaviy reconciliation ushbu snapshotda to‘liq mavjud deb hisoblanmaydi.
- **Packages/pricing** — alohida package katalogi va tasdiqlangan price modeli yo‘q; narx bo‘yicha sorting yoqilmagan.
- **XLSX export** — CSV eksport bor; `.xlsx` eksport yo‘q.
- **News model/search** — tasdiqlangan news data model yo‘q; global news search mavjud emas.
- **Browser push** — Telegram inbox bor, universal web push markazi yo‘q.
- **Advanced tests** — hozirgi quiz oqimi asosan single-choice; murakkab test builder to‘liq emas.
- **LMS completeness** — homework, attendance, groups, materials va progress modullari mavjud yoki qisman ishlangan; to‘liq tijoriy LMS darajasidagi barcha ish jarayonlari yakunlangan deb bo‘lmaydi.
- **Individual permissions** — markaziy role guard mavjud; har bir admin uchun to‘liq granular permission matrix alohida loyiha vazifasi bo‘lishi mumkin.
- **Email password reset** — tashqi email recovery xizmati sozlanmagan.
- **PWA/Core Web Vitals** — real domen va qurilmalarda Lighthouse/Core Web Vitals o‘lchovlari talab qilinadi.
- **Privacy retention** — ma’lumotlarni saqlash/o‘chirish siyosati rasmiy mas’ul tomonidan tasdiqlanishi kerak.

Current feature assessment: [`docs/ARCHITECTURE_AND_FEATURE_MATRIX.md`](docs/ARCHITECTURE_AND_FEATURE_MATRIX.md).

## 🧯 Muammolarni bartaraf etish

### `BOT_TOKEN topilmadi`

`backend/.env` faylini tekshiring. `BOT_TOKEN` ga haqiqiy bot tokeni kiritilgan bo‘lishi kerak. Tokenni hech qachon ommaviy yubormang.

### `CEO_OWNER_ID topilmadi` yoki noto‘g‘ri ID

`CEO_OWNER_ID` va `OWNER_TELEGRAM_ID` ni musbat Telegram numeric ID sifatida tekshiring. Username emas, numeric ID ishlatiladi.

### `WEB_ADMIN_PASSWORD_HASH` bo‘sh yoki login ishlamayapti

`python create_admin_hash.py` ni ishga tushiring, hosil bo‘lgan hashni `.env` ga kiriting va to‘g‘ri username bilan login qiling. Hashni qayta yaratganda eski parol mos kelmaydi.

### `ADMIN_SESSION_SECRET` yo‘q

Yangi `secrets.token_urlsafe(48)` qiymatini yarating va `.env` ga joylang. Production session secret’ni almashtirish faol sessiyalarni bekor qilishi mumkin.

### `[WinError 10048]` / port band

Bu API portini boshqa jarayon band qilganini anglatadi. Yuqoridagi PowerShell buyruqlari bilan PID va jarayon nomini tekshiring. Ikkinchi bot yoki API instance ochmang.

### Frontend API bilan bog‘lanmayapti

- Backend `API_HOST` va `API_PORT` ni tekshiring.
- Frontendni `http://127.0.0.1:5500` kabi local server orqali oching.
- `frontend/startum.config.js` API base URL qiymatini tekshiring.
- `CORS_ORIGINS` ichida frontend origin mavjudligini tekshiring.

### Yo‘nalish/kurs katalogi bo‘sh

`GET /api/catalog` javobini tekshiring. Faol kurslar DB’da mavjud bo‘lishi kerak. Test ma’lumotlarini production bazaga qo‘shmang.

### Telegram xabar bormayapti

- Bot token va polling process holatini tekshiring.
- Qabul qiluvchi Telegram foydalanuvchi botni avval `/start` qilgan bo‘lishi kerak.
- `notification_outbox` va Admin Panel notification monitoringini tekshiring.
- Telegram vaqtincha mavjud bo‘lmasa, queued outbox yozuvlari retry uchun saqlanishi kerak.

## 🤝 Hissa qo‘shish

1. Repository’dan alohida branch yarating.
2. O‘zgarishni kichik va tushunarli commitlarga ajrating.
3. Mavjud arxitekturani o‘zgartirishdan oldin `docs/ARCHITECTURE_AND_FEATURE_MATRIX.md` va tegishli audit hujjatlarini o‘qing.
4. Backend uchun pytest/unittest, frontend uchun Node va browser acceptance testlarini bajaring.
5. Maxfiy ma’lumot yoki real shaxsiy DB’ni commit qilmang.
6. Pull request’da o‘zgarish, test natijasi va qolgan cheklovlarni yozing.

## 📄 Litsenziya

Repository’da aniq open-source litsenziya tasdiqlanmagan bo‘lsa, kodni qayta tarqatish yoki tijoriy foydalanish huquqini avtomatik taxmin qilmang. Litsenziya egasi tomonidan tanlanib, `LICENSE` fayli qo‘shilishi kerak.

## 📬 Loyiha egasi va aloqa

Public telefon, manzil, Telegram kanal/bot username va GitHub repository ownership ma’lumotlari release oldidan STARTUM mas’uli tomonidan tasdiqlanishi kerak. Maxfiy credentiallar README yoki GitHub issue orqali almashilmaydi.

---

<div align="center">

**STARTUM Enterprise**  
*One Center. Multiple Directions. One Connected Education Platform.*

</div>
