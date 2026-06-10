# QualiFlow — Yüksek Seviyeli Mimari (Genel Bakış)

**Proje:** QualiFlow — Endüstriyel Kalite Belgesi (CoA / MTC) Doğrulama Sistemi  
**Tür:** Bilgisayar Mühendisliği Bitirme Projesi — Araştırma Prototipi  
**Mimari yaklaşım:** Neuro-symbolic (Yapay zeka okur + Kurallar doğrular)

---

## 1. Projenin Amacı (Tek Paragraf)

QualiFlow, fabrikalara gelen **Analiz Sertifikası (CoA)** ve **Değirmen Test Sertifikası (MTC)** PDF belgelerinden otomatik olarak veri çıkarır ve malzeme spesifikasyonlarına karşı **uyumluluk kontrolü** yapar. Sistem bir ürün değil, **denetlenebilir karar veren** bir araştırma prototipidir: emin olamadığı durumlarda yanlış onay vermek yerine **insan incelemesine** yönlendirir.

---

## 2. Sistem Bileşenleri (3 Katman)

| Katman | Klasör | Ne işe yarar? |
|--------|--------|----------------|
| **Arayüz** | `frontend/` | Kullanıcı PDF yükler, sonuçları ve inceleme nedenlerini görür |
| **Sunucu** | `app/` | Belgeyi işler: profil → yönlendirme → çıkarım → doğrulama |
| **Veri** | `data/` | Veritabanı, yüklenen PDF'ler, test veri seti ve değerlendirme sonuçları |

**Dış bağımlılık:** Anthropic Claude API (belge okuma), Poppler (PDF → görüntü dönüşümü)

---

## 3. Genel Mimari Şema

```
┌─────────────┐         ┌─────────────────────────────────────┐         ┌──────────┐
│  Kullanıcı  │ ──────► │  frontend/  (React)                 │ ──────► │  app/    │
│  (Tarayıcı) │ ◄────── │  Yükleme · Geçmiş · Sonuç ekranı    │ ◄────── │  FastAPI │
└─────────────┘   JSON  └─────────────────────────────────────┘   REST  └────┬─────┘
                                                                            │
                    ┌───────────────────────────────────────────────────────┤
                    │                                                       │
                    ▼                                                       ▼
             ┌─────────────┐                                          ┌─────────────┐
             │  data/      │                                          │  Claude API │
             │  SQLite +   │                                          │  (Okuma)    │
             │  PDF dosya  │                                          └─────────────┘
             └─────────────┘
```

**Özet:** Arayüz iş mantığı içermez; tüm kararlar sunucuda (`app/`) alınır.

---

## 4. Belge İşleme Akışı (Ana Pipeline)

Bir PDF yüklendiğinde sunucu şu adımları **sırayla** uygular:

```
  PDF Yükleme
       │
       ▼
  ① PROFİLLEME          Belge kalitesi: dijital mi, tarama mı, bozuk mu?
       │
       ▼
  ② YÖNLENDİRME         Tek bir işleme yolu seçilir (3 seçenekten biri)
       │
       ▼
  ③ ÖN İŞLEME           PDF sayfaları görüntüye çevrilir, gerekirse iyileştirilir
       │
       ▼
  ④ ÇIKARIM (Claude)    Aşama A: üst bilgi  →  Aşama B: tablo satırları
       │
       ▼
  ⑤ NORMALİZASYON       Alan adları ve satır yapısı standart forma getirilir
       │
       ▼
  ⑥ DOĞRULAMA           Grade/spec kurallarına göre uyum kontrolü
       │
       ▼
  ⑦ GÜVEN + İNCELEME    Otomatik onay mı, insan incelemesi mi?
       │
       ▼
  JSON Sonuç + (isteğe bağlı) veritabanına kayıt
```

---

## 5. Neuro-Symbolic Ayrımı

| Bölüm | Teknoloji | Görev |
|-------|-----------|--------|
| **Neural (Sinirsel)** | Claude multimodal | Belgeyi okur, alanları çıkarır |
| **Symbolic (Sembolik)** | Python kuralları | Grade eşleme, spec kontrolü, review kararı |

**Neden ayrı?** Yapay zeka layout farklılıklarına uyum sağlar; kurallar katmanı ise kararları **test edilebilir ve açıklanabilir** kılar.

---

## 6. Belge Kalitesi ve Yönlendirme

Profiler her PDF için **tek bir kalite sınıfı** atar:

| Kalite sınıfı | Anlam | Seçilen yol |
|---------------|--------|-------------|
| `digital_clean` | Dijital PDF, temiz | Doğrudan multimodal |
| `scan_clean` | Temiz tarama | Raster + multimodal |
| `noisy_scan` | Bulanık / gürültülü tarama | Ön işlemeli multimodal |
| `severe_scan` | Çok kötü tarama | Ön işlemeli + muhafazakâr inceleme |

**Önemli:** Kötü tarama tek başına red sebebi değildir; somut veri eksikliği veya düşük güven inceleme tetikler.

---

## 7. Klasör Yapısı (Özet)

```
QualiFlow/
├── app/              → Backend (API + pipeline)
│   ├── routes/       → HTTP uç noktaları
│   ├── services/     → İş mantığı (profiler, validator, …)
│   └── domain/       → Malzeme grade/spec kuralları
├── frontend/         → React arayüzü
├── data/             → DB, PDF depolama, test veri seti
├── scripts/          → Toplu test ve değerlendirme araçları
├── tests/            → pytest otomatik testler (~240 test)
└── docs/             → Teknik dokümantasyon
```

---

## 8. Veri Akışı (Kullanıcı Perspektifi)

1. Kullanıcı giriş yapar (`frontend` → `POST /auth/login`)
2. PDF yükler (`POST /api/v1/extract`)
3. Sunucu pipeline'ı çalıştırır (yukarıdaki 7 adım)
4. Sonuç ekranda gösterilir: tedarikçi, grade, mekanik değerler, uyum durumu, inceleme nedenleri
5. Giriş yapılmışsa sonuç `data/qualiflow.db` içine kaydedilir; Geçmiş sayfasından tekrar açılabilir

---

## 9. Değerlendirme Hattı (Akademik)

PDF koleksiyonu repoda değil; `scripts/` altındaki araçlarla:

```
Keşif → Profil → Manifest → Toplu çıkarım (Mode D) → Metrik raporu
```

| Mode | Açıklama |
|------|----------|
| D (önerilen) | Profiler + router ile hibrit yol |
| B / C | Karşılaştırma deneyleri (routing kapalı veya sabit ön işlem) |

Final metrikler yalnızca **insan doğrulamalı gold** veri ile raporlanır.

---

## 10. Güvenlik (Kısa)

- API anahtarları `.env` dosyasında; Git'e gönderilmez
- Kullanıcı şifreleri veritabanında bcrypt ile hash'lenir
- Claude API anahtarı yalnızca sunucuda kullanılır; tarayıcıya gitmez

---

## 11. Sınırlar ve Gelecek Çalışmalar

| Bugün | Gelecek |
|-------|---------|
| Tek sunucu, senkron işleme | Kuyruk tabanlı async işleme |
| SQLite + yerel dosya | PostgreSQL + bulut depolama (S3/Azure) |
| Monolith FastAPI | Mikroservis ayrımı (profiler, extract, validate) |
| Sınırlı spec kapsamı | Genişletilmiş malzeme ailesi registry |

---

## 12. Özet Cümle (Sunum Kapanışı)

> QualiFlow, endüstriyel kalite belgelerini **kalite farkındalıklı hibrit pipeline** ile işler; yapay zeka okuma yapar, deterministik kurallar doğrular ve belirsizlik durumunda **açık inceleme gerekçeleri** üretir.

---

*Bu belge bitirme projesi sunumu ve Word raporu için hazırlanmış sadeleştirilmiş mimari özetidir. Detaylı teknik spesifikasyon: `docs/runtime_architecture.md`*
