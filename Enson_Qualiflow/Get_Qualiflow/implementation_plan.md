# QualiFlow — 20 PDF'de Doğru Extraction Sonucu Alma Planı

Gemini Chat'e aynı bulanık PDF verildiğinde doğru sonuç çıkarabilirken, QualiFlow pipeline'ımız `heat_number`, `grade` gibi kritik alanları `null` bırakıyor ve `NEEDS_REVIEW` veriyor. Amaç: 20 PDF'in tamamından ground truth'a yakın doğru sonuç çıkarmak.

## Kök Neden Analizi

Sorun tek bir yerde değil, **5 katmanda** birbirine eklenerek büyüyor:

| # | Katman | Sorun | Etki |
|---|--------|-------|------|
| 1 | **Prompt (Extraction Pipeline)** | `ITEM_PROMPT` Claude'a "tahmin etme, null yap" diyor | Claude okunabilen metni bile `null` bırakıyor |
| 2 | **Görüntü Kalitesi (Preprocessing)** | 400 DPI → dev görüntü → 1600px'e küçültme + JPEG sıkıştırma | Çift dönüşüm bulanıklığı artırıyor |
| 3 | **Confidence Penalty (confidence.py)** | `blur < 80` → anında `-0.18` ve `cap 0.45` | Ne kadar iyi okusa da skor çıkamıyor |
| 4 | **Review Policy (review_policy.py)** | `severe_scan` → otomatik `NEEDS_REVIEW` | Doğru okumuş olsa bile "insan baksın" diyor |
| 5 | **Document Type Matching** | Claude `"MTC - INSPECTION CERTIFICATE (3.1)"` döndürüyor ama `SUPPORTED_DOCUMENT_TYPES` listesinde sadece `"mill test certificate"` var | `unsupported_document_type` tetikleniyor |

---

## Proposed Changes

### 1. Prompt Güncelleme — Claude'u Cesaretlendir

#### [MODIFY] [extraction_pipeline.py](file:///c:/Users/DELL/OneDrive%20-%20Istanbul%20Kultur%20Universitesi/Masaüstü/Academic/Graduation_Project_Qualiflow/Enson_Qualiflow/Get_Qualiflow/app/services/extraction_pipeline.py)

**`METADATA_PROMPT` (satır 77-85):**
- `"Do not guess unreadable text."` → `"Extract all visible text even if slightly blurry. Only use null when text is completely illegible."`
- Ekle: `"For document_type, use a concise standard label such as 'Mill Test Certificate'."`

**`ITEM_PROMPT` (satır 87-98):**
- `"Priority is precision over recall"` → `"Extract all values that are visually distinguishable, even from degraded scans."`
- `"Do not infer, repair, or guess..."` → `"Read all visible cell values. If a character is ambiguous but most likely readable, include your best reading and set row_confidence accordingly."`
- `"If no reliable rows are visible, return total_items_detected as 0"` → `"Only return empty results when the table is completely illegible."`
- Ekle: `"For blurry or low-contrast documents, try harder to read values. Use row_confidence between 0.3-0.6 for uncertain readings rather than returning null."`

> [!IMPORTANT]
> Bu en kritik değişiklik. Gemini'nin başardığı şey budur: bulanık ama okunabilir metni okumak. Claude da bunu yapabilir, ama mevcut prompt onu engelliyor.

---

### 2. Görüntü Kalitesini Artır — Claude'a Daha Net Görüntü Gönder

#### [MODIFY] [.env](file:///c:/Users/DELL/OneDrive%20-%20Istanbul%20Kultur%20Universitesi/Masaüstü/Academic/Graduation_Project_Qualiflow/Enson_Qualiflow/Get_Qualiflow/.env)

```env
ANTHROPIC_API_KEY=sk-ant-...
PDF_DPI=300
LLM_IMAGE_MAX_EDGE=2400
LLM_IMAGE_TARGET_BYTES=5500000
LLM_JPEG_QUALITY=88
```

**Neden:** 
- DPI 400→300: Dev görüntüyü durdurur (DecompressionBomb uyarısını çözer)
- Max edge 1600→2400: Claude'a giden resim daha büyük ve net olur
- JPEG kalitesi 82→88: Sıkıştırma daha az agresif olur, detay korunur
- Target bytes 4.5MB→5.5MB: Daha büyük resim gönderilebilir

---

### 3. Confidence Cezalarını Yumuşat — Doğru Okunan Sonuca Hak Ettiği Skoru Ver

#### [MODIFY] [confidence.py](file:///c:/Users/DELL/OneDrive%20-%20Istanbul%20Kultur%20Universitesi/Masaüstü/Academic/Graduation_Project_Qualiflow/Enson_Qualiflow/Get_Qualiflow/app/services/confidence.py)

Satır 134-141 — Blur penalty'yi yumuşat:

```python
# ÖNCE:
if avg_blur < 80:
    adjusted -= 0.18
    caps.append(0.45)
    review_reasons.append("blurry/noisy document")

# SONRA:
if avg_blur < 30:         # Sadece aşırı bulanıkta sert ceza
    adjusted -= 0.15
    caps.append(0.50)
    review_reasons.append("blurry/noisy document")
elif avg_blur < 80:       # Orta bulanıklık → hafif ceza
    adjusted -= 0.08
    caps.append(0.70)
```

Satır 161-167 — Missing fields penalty'yi yumuşat:

```python
# ÖNCE:
if missing_rate >= 0.7:
    adjusted -= 0.16
    caps.append(0.4)
elif missing_rate >= 0.4:
    adjusted -= 0.08
    caps.append(0.65)

# SONRA:
if missing_rate >= 0.8:
    adjusted -= 0.12
    caps.append(0.50)
elif missing_rate >= 0.5:
    adjusted -= 0.06
    caps.append(0.70)
```

---

### 4. Review Policy — `severe_scan` Otomatik Review'ı Kaldır

#### [MODIFY] [review_policy.py](file:///c:/Users/DELL/OneDrive%20-%20Istanbul%20Kultur%20Universitesi/Masaüstü/Academic/Graduation_Project_Qualiflow/Enson_Qualiflow/Get_Qualiflow/app/services/review_policy.py)

Satır 534-537 — Kalite sınıfı artık tek başına review tetiklemesin:

```python
# ÖNCE:
if profile_bucket == "severe_scan":
    structured.append("document_quality:severe_scan")
elif profile is not None and profile.quality_class == "scan_degraded":
    structured.append("document_quality:scan_degraded")

# SONRA:
# Kalite sınıfı tek başına review tetiklemez.
# Sadece "confidence_below_threshold" veya "missing_critical_field" 
# gibi somut kanıtlar review tetikler.
# Kalite bilgisi metadata'da saklanır ama blocker değildir.
```

> [!WARNING]
> Bu değişiklik, `severe_scan` etiketli dökümanların artık sadece "kötü kalite" oldukları için değil, gerçekten eksik/hatalı veri içerdikleri zaman `NEEDS_REVIEW` olmasını sağlar.

---

### 5. Document Type Matching — Daha Geniş Tanıma

#### [MODIFY] [review_policy.py](file:///c:/Users/DELL/OneDrive%20-%20Istanbul%20Kultur%20Universitesi/Masaüstü/Academic/Graduation_Project_Qualiflow/Enson_Qualiflow/Get_Qualiflow/app/services/review_policy.py)

Satır 54-61 — `SUPPORTED_DOCUMENT_TYPES` setine ek terimler ekle:

```python
SUPPORTED_DOCUMENT_TYPES = {
    "certificate of analysis",
    "coa",
    "mill test certificate",
    "mill test report",
    "material test certificate",
    "mtc",
    # Yeni eklemeler — Claude'un döndürdüğü varyasyonlar
    "inspection certificate",
    "test report",
    "test certificate",
    "certificate of quality",
    "certificate of conformity",
    "material certificate",
    "3.1 certificate",
    "en 10204",
}
```

---

### 6. Profiler Eşik Değerleri — Daha Az Dökümanı `severe_scan` Yapma

#### [MODIFY] [document_profiler.py](file:///c:/Users/DELL/OneDrive%20-%20Istanbul%20Kultur%20Universitesi/Masaüstü/Academic/Graduation_Project_Qualiflow/Enson_Qualiflow/Get_Qualiflow/app/services/document_profiler.py)

Satır 48-49 — `severe_scan` eşiklerini daralt (sadece gerçekten okunamaz dökümanlar severe olsun):

```python
# ÖNCE:
BLUR_SEVERE_THRESHOLD = 45.0
NOISE_SEVERE_THRESHOLD = 38.0

# SONRA:
BLUR_SEVERE_THRESHOLD = 25.0    # Sadece çok kötü taramalar
NOISE_SEVERE_THRESHOLD = 45.0   # Sadece çok gürültülü taramalar
```

**Etki:** `doc001.pdf` (blur=2.8) hâlâ `severe_scan` kalır ama diğer orta kalite dökümanlar artık `scan_degraded` olarak sınıflanır — bu da daha iyi preprocessing stratejisi seçilmesini sağlar.

---

## Open Questions

> [!IMPORTANT]
> **Anthropic API bütçen ne kadar?** Bu 20 PDF'i yeniden çalıştırmak yaklaşık 20 × ~12K input token = ~240K token tüketecek (yaklaşık $0.75-1.00). Sorun var mı?

> [!IMPORTANT]
> **Ground Truth JSON'lardaki dosya adı tutarsızlığı:** `doc0010.json` → `doc010.json` olarak düzeltilmeli mi? Bu, eval scriptlerinin çalışması için gerekli.

---

## Verification Plan

### Automated Tests
1. Backend'i yeniden başlat
2. Tek bir temiz PDF test et (örn. `doc014.pdf` - `digital_pdf`)
3. Tek bir bulanık PDF test et (örn. `doc001.pdf` - `severe_scan`)
4. Her ikisinde de `heat_number`, `grade`, `mechanical_properties` alanlarının dolu geldiğini kontrol et
5. Frontend'de sonucu görsel olarak doğrula

### Manual Verification
- Tüm 20 PDF'i frontend üzerinden sırayla test edip ground truth JSON'lar ile karşılaştır
- Eval script'i çalıştırarak metrik tablosu oluştur

---

## Uygulama Sırası

| Adım | Dosya | Tahmini Süre |
|------|-------|------|
| 1 | `.env` (görüntü kalitesi ayarları) | 1 dk |
| 2 | `extraction_pipeline.py` (prompt'lar) | 5 dk |
| 3 | `review_policy.py` (document types + severe_scan politikası) | 5 dk |
| 4 | `confidence.py` (ceza yumuşatma) | 3 dk |
| 5 | `document_profiler.py` (eşik daraltma) | 2 dk |
| 6 | Test: 1 temiz + 1 bulanık PDF | 5 dk |
| **Toplam** | | **~20 dk** |
