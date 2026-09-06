# مخطّط قاعدة بيانات الأجور — SCHEMA_PAIE

> **حالة الوثيقة:** نهائية بعد تطبيق القرارات السبعة (المهمة 11).
> المرجع الوظيفي: `docs/specs/SPEC_PAIE_DZ.md`. اصطلاحات القاعدة القائمة:
> `docs/AUDIT_DB.md`.
>
> ست جداول جديدة على نفس ملف `office_system.db`، تُنشَأ عبر **هجرة رقم 2**
> في `programme/payroll/repository.py` (لائحة `_MIGRATIONS` + جدول تتبّع
> `schema_migrations` — راجع §11). `repository.py` لا يعتمد على `tkinter`
> ولا `ui/` (يستورد `get_connection` محلياً فقط عند الحاجة)، فيبقى شرط
> فصل `programme/payroll` قائماً.
>
> جداول الأجور **مستقلّة تماماً** عن جداول CD/الزبائن — لا `FOREIGN KEY`
> بينها وبين `clients` أو غيرها.

---

## 0. قواعد عامة متّفق عليها

### 0.1 المال والنِّسب = `TEXT` (نصّ عشري قانوني)

كل مبلغ أو نسبة يُخزَّن **نصّاً** بصيغة `str(Decimal(x))` القانونية:
نقطة عشرية `.`، بلا فاصل آلاف، بلا `+` بادئة، `'0'` للصفر
(مثل `'27472.53'`, `'0.09'`, `'1.50'`). يُقرأ: `Decimal(row["col"] or "0")`.

السبب: المحرّك «Decimal حصراً، ممنوع float» (SPEC §5.4). `REAL` في
SQLite = float ⇒ يُفسد التمثيل. (`cd_documents.eur_amount` تبقى `REAL`
لأن خدمة CD غير صارمة — الأجور صارمة.)

### 0.2 المفاتيح الأجنبية

`PRAGMA foreign_keys = ON` مضبوط أصلاً لكل اتصال (`get_connection`).
هذه جداول تُنشأ دفعة واحدة، فالـ`FOREIGN KEY` مباشرة (بعكس
`cd_documents`/`hr_documents` التي أُضيف ربطها بـ`ALTER` فبقي منطقياً).

| العلاقة | `ON DELETE` | السبب |
|---|---|---|
| `convention.entreprise_id → entreprise.id` | **RESTRICT** | لا تُحذف شركة لها اتفاقيات |
| `rubrique_catalogue.entreprise_id → entreprise.id` | **CASCADE** | الكتالوج إعداد تابع للشركة بحتاً |
| `employe.entreprise_id → entreprise.id` | **RESTRICT** | حماية سجلّ العمّال |
| `bulletin.employe_id → employe.id` | **RESTRICT** | حماية السجلّ المالي |
| `bulletin.remplace_bulletin_id → bulletin.id` | **RESTRICT** | لا يُحذف كشف يُصحِّحه آخر |
| `bulletin_ligne.bulletin_id → bulletin.id` | **CASCADE** | الأسطر جزء من الكشف |

العلاقة `bulletin → convention` **لقطة لا FK**: الكشف يُجمِّد
`convention_version` (عدد صحيح)، والوصول للاتفاقية استعلامٌ عبر
`employe.entreprise_id + bulletin.convention_version` — يطابق فلسفة
تجميد الاتفاقية في الكشف (SPEC §1.2.2 القاعدة 2).

### 0.3 القوائم = `TEXT` JSON

`rubrique_catalogue.base_calcul`, `rubrique_catalogue.depend_de`,
`bulletin.avertissements_json` — نصّ JSON (`'["SAL_BASE","IEP"]'`,
`'[]'`)، نفس نمط `full_data_json` القائم.

### 0.4 الطوابع الزمنية

`created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))` و
`updated_at TEXT` على **كل الجداول**، ما عدا `convention` (سطر واحد
غير قابل للتعديل — `updated_at` سيبقى فارغاً أبداً، فحُذف؛ راجع §2).
`updated_at` يُضبط **يدوياً بالكود** في كل `UPDATE` (نمط
`update_cd_document` القائم) — **بلا أي `trigger` تلقائي** (قرار نهائي).

### 0.5 المنطقيات (Booleans)

`INTEGER` مع `CHECK (col IN (0, 1))` — نفس اصطلاح القاعدة القائمة.

### 0.6 المشتقّات لا تُخزَّن

`zone` و`ordre_calcul` للرُبريكة **لا تُخزَّنان** في
`rubrique_catalogue` (SPEC §2.1 — يُشتقّان آلياً). القيمة المشتقّة
تُجمَّد في `bulletin_ligne.zone` وقت التوليد فقط.

---

## 1. `entreprise`

```sql
CREATE TABLE IF NOT EXISTS entreprise (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    raison_sociale      TEXT    NOT NULL,
    forme_juridique     TEXT,
    nif                 TEXT,
    nis                 TEXT,
    rc                  TEXT,
    art_imposition      TEXT,
    num_employeur_cnas  TEXT,
    adresse             TEXT,
    gerant_nom          TEXT,
    gerant_qualite      TEXT,
    tel                 TEXT,
    actif               INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT
);

-- NIF فريد حين يُدخَل (فهرس جزئي — يقبل تعدّد NULL أثناء الإدخال)
CREATE UNIQUE INDEX IF NOT EXISTS ux_entreprise_nif
    ON entreprise (nif) WHERE nif IS NOT NULL;
```

- `forme_juridique … tel`: حقول هوية صاحب العمل الإجبارية على الكشف
  (المادة 34 من ق.90‑11 — SPEC §7)، مطابقة لـ`ui/hr/constants.py:EMPLOYER_FIELDS`.
- جدول **مستقلّ** عن `clients` (طبقة CD): لا رابط.

---

## 2. `convention` — طبقة الاتفاقية (SPEC §1.2)

**سطر واحد لكل (شركة، نسخة). لا يُعدَّل أبداً — كل تغيير = `INSERT`
بنسخة أعلى.** لا عمود `updated_at` (بلا معنى مع منع التعديل).

```sql
CREATE TABLE IF NOT EXISTS convention (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id                 INTEGER NOT NULL
                                    REFERENCES entreprise(id) ON DELETE RESTRICT,
    version                       INTEGER NOT NULL,
    confirme                      INTEGER NOT NULL DEFAULT 0
                                    CHECK (confirme IN (0, 1)),
    base_iep                      TEXT NOT NULL DEFAULT 'SAL_BASE_BRUT'
                                    CHECK (base_iep IN ('SAL_BASE_BRUT',
                                                        'SAL_BASE_APRES_ABSENCES')),
    base_pri                      TEXT NOT NULL DEFAULT 'SAL_BASE_BRUT'
                                    CHECK (base_pri IN ('SAL_BASE_BRUT',
                                                        'SAL_BASE_APRES_ABSENCES')),
    prorata_panier_transport      TEXT NOT NULL DEFAULT 'PRORATA_HEURES'
                                    CHECK (prorata_panier_transport IN ('AUCUN',
                                           'PRORATA_HEURES', 'PRORATA_JOURS')),
    retard_reduit_heures_presence INTEGER NOT NULL DEFAULT 0
                                    CHECK (retard_reduit_heures_presence IN (0, 1)),
    taux_hs_jour                  TEXT NOT NULL DEFAULT '1.50'
                                    CHECK (CAST(taux_hs_jour  AS REAL) >= 1.5),
    taux_hs_nuit                  TEXT NOT NULL DEFAULT '2.00'
                                    CHECK (CAST(taux_hs_nuit  AS REAL) >= 1.5),
    taux_hs_ferie                 TEXT NOT NULL DEFAULT '2.00'
                                    CHECK (CAST(taux_hs_ferie AS REAL) >= 1.5),
    created_at                    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (entreprise_id, version)
);

-- منع أي تعديل: الاتفاقية غير قابلة للتغيير (SPEC §1.2)
CREATE TRIGGER IF NOT EXISTS convention_no_update
BEFORE UPDATE ON convention
BEGIN
    SELECT RAISE(ABORT,
        'convention immuable — chaque changement = nouvelle ligne (version +1)');
END;
```

- `confirme` = `confirme_par_utilisateur` (SPEC §1.2.1). توليد **أول
  كشف** للشركة ممنوع حتى `confirme = 1` (V15، فحص بالكود).
- `CHECK (CAST(taux_hs_* AS REAL) >= 1.5)`: حارس قاعديّ يقابل V5
  («معامل س.إضافية < 1,50 → منع»). القيمة تُقرأ `Decimal`؛ الـ`CAST`
  للمقارنة الحدّية فقط لا للحساب.
- الحذف مسموح لاتفاقية غير مرجَعة (يحميها `bulletin.convention_id
  … RESTRICT`)؛ الـ`TRIGGER` يمنع `UPDATE` فقط.

---

## 3. `rubrique_catalogue` — كتالوج الرُبريكات لكل شركة (SPEC §2.1)

```sql
CREATE TABLE IF NOT EXISTS rubrique_catalogue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id   INTEGER NOT NULL
                      REFERENCES entreprise(id) ON DELETE CASCADE,
    code            TEXT    NOT NULL,
    libelle_fr      TEXT    NOT NULL,
    libelle_ar      TEXT    NOT NULL,
    sens            TEXT    NOT NULL CHECK (sens IN ('GAIN', 'RETENUE')),
    mode            TEXT    NOT NULL CHECK (mode IN ('MONTANT', 'TAUX_SUR_BASE',
                                                    'QUANTITE_X_PU', 'FORMULE')),
    base_calcul     TEXT    NOT NULL DEFAULT '[]',       -- JSON list[str]
    cotisable       INTEGER NOT NULL CHECK (cotisable IN (0, 1)),   -- بلا DEFAULT: إلزامي
    imposable       INTEGER NOT NULL CHECK (imposable IN (0, 1)),   -- بلا DEFAULT: إلزامي
    regime_irg      TEXT    NOT NULL DEFAULT 'BAREME'
                      CHECK (regime_irg IN ('BAREME', 'TAUX_10')),
    proratisable    INTEGER NOT NULL DEFAULT 0 CHECK (proratisable IN (0, 1)),
    depend_de       TEXT    NOT NULL DEFAULT '[]',       -- JSON list[str]
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    actif           INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT,
    UNIQUE (entreprise_id, code)
);
```

- `cotisable` و`imposable` **`NOT NULL` بلا `DEFAULT`**: يفشل الإدراج
  على مستوى القاعدة لو لم يُحدَّدا صراحةً (V7 — SPEC §2.1).
- `regime_irg`: يقبل `'TAUX_10'` تخزيناً (موجود في النموذج — SPEC §2.4)،
  لكن المحرّك يرفضه عند التوليد برسالة صريحة.
- `zone`/`ordre_calcul` غير موجودين (§0.6).
- الكتالوج الافتراضي (SPEC §2.2، ~24 رُبريكة) يُبذَر بدالة
  `seed_default_catalogue(entreprise_id)` عند إنشاء الشركة — منطق كود،
  خارج المخطّط.

---

## 4. `employe`

```sql
CREATE TABLE IF NOT EXISTS employe (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id        INTEGER NOT NULL
                           REFERENCES entreprise(id) ON DELETE RESTRICT,
    nom                  TEXT    NOT NULL,
    prenom               TEXT,
    num_ss               TEXT,
    date_entree          TEXT,        -- ISO 'YYYY-MM-DD' ; الأقدمية تُحسب آلياً
    poste                TEXT,
    classe_indice        TEXT,        -- القطاع العمومي
    type_contrat         TEXT    CHECK (type_contrat IN ('CDI', 'CDD')),  -- NULL مسموح
    rib                  TEXT,
    salaire_base         TEXT    NOT NULL DEFAULT '0',   -- Decimal
    taux_iep             TEXT,                            -- Decimal ; تجاوز اختياري
    nb_enfants           INTEGER NOT NULL DEFAULT 0 CHECK (nb_enfants >= 0),
    temps_partiel_ratio  TEXT    NOT NULL DEFAULT '1',   -- Decimal (1 = دوام كامل)
    date_sortie          TEXT,        -- ISO 'YYYY-MM-DD' ؛ عند انتهاء العقد
    actif                INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at           TEXT
);
```

- `date_entree` فقط للدخول — الأقدمية بالسنوات تُحسب وقت الكشف (SPEC §7).
  `date_sortie` للعامل المنتهي عقده (مع `actif = 0`).
- **لا عمود `convention_id`**: العامل غير مربوط باتفاقية بعينها؛ الكشف
  يختار الاتفاقية المؤكَّدة الحالية للشركة وقت التوليد ويُجمِّد نسختها.
- `taux_iep`: **تجاوز اختياري**. `NULL` ⇒ المحرّك يستعمل
  `أقدمية_بالسنوات × params.iep.taux_par_annee` (SPEC §3 [4]). قيمة
  مضبوطة ⇒ نسبة IEP ثابتة متفاوَض عليها.
- `temps_partiel_ratio` → `SequenceInput.prorata_jours` (نسبة العقد
  لأرضية SNMG — SPEC §3 [7]).
- `type_contrat IN ('CDI','CDD')`: `NULL` يمرّ (تعبير `IN` يعطي `NULL`
  لا `0`، فالـ`CHECK` يقبله).

---

## 5. `bulletin`

```sql
CREATE TABLE IF NOT EXISTS bulletin (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    employe_id           INTEGER NOT NULL
                           REFERENCES employe(id) ON DELETE RESTRICT,
    periode              TEXT    NOT NULL,               -- 'YYYY-MM'
    type                 TEXT    NOT NULL DEFAULT 'NORMAL'
                           CHECK (type IN ('NORMAL', 'CORRECTIF')),
    remplace_bulletin_id INTEGER REFERENCES bulletin(id) ON DELETE RESTRICT,
    etat                 TEXT    NOT NULL DEFAULT 'BROUILLON'
                           CHECK (etat IN ('BROUILLON', 'CALCULE', 'FIGE')),
    numero_serie         TEXT    UNIQUE,                 -- يُملأ عند FIGE فقط
    fige_at              TEXT,                           -- طابع التثبيت
    params_version       TEXT    NOT NULL,               -- ex: '2026.1'
    convention_version   INTEGER NOT NULL,               -- لقطة (SPEC §1.2.2) — لا FK
    total_a              TEXT    NOT NULL DEFAULT '0',   -- [A] SALAIRE DE POSTE
    total_b              TEXT    NOT NULL DEFAULT '0',   -- [B] RETENUE CNAS
    total_c              TEXT    NOT NULL DEFAULT '0',   -- [C] BRUT IMPOSABLE
    total_d              TEXT    NOT NULL DEFAULT '0',   -- [D] IRG
    net_e                TEXT    NOT NULL DEFAULT '0',   -- [E] NET À PAYER
    avertissements_json  TEXT    NOT NULL DEFAULT '[]',  -- JSON list[str] (V2…)
    pdf_path             TEXT,                           -- PDF المثبَّت
    date_generation      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at           TEXT,

    -- كشف عادي بلا مُصحَّح ؛ كشف تصحيحي يشير إلى الأصل إلزامياً
    CHECK ((type = 'NORMAL'    AND remplace_bulletin_id IS NULL)
        OR (type = 'CORRECTIF' AND remplace_bulletin_id IS NOT NULL)),
    -- التثبيت (FIGE) يتطلّب رقماً متسلسلاً وطابعاً (V16 جزئياً)
    CHECK (etat != 'FIGE'
        OR (numero_serie IS NOT NULL AND fige_at IS NOT NULL))
);

-- كشف NORMAL واحد فقط لكل (عامل، شهر) ؛ التصحيحيات متعددة → فهرس جزئي
CREATE UNIQUE INDEX IF NOT EXISTS ux_bulletin_normal_periode
    ON bulletin (employe_id, periode)
    WHERE type = 'NORMAL';
```

- **`pdf_path` بدل `hr_document_id`**: الكشف يحمل مسار PDF المثبَّت
  مباشرةً، بلا ربط بجدول `hr_documents`.
- `convention_version` (لقطة رقمية) و`params_version` (وسم نصّي —
  المعاملات ملفات JSON لا جدول) — كلاهما `NOT NULL` (V16). **لا FK
  لـ`convention`** (لقطة مجمَّدة، لا انتماء حيّ).
- `numero_serie UNIQUE` — يقبل `NULL` متعدّداً (كشوف غير مثبَّتة).
- `type` + `remplace_bulletin_id` + الفهرس الجزئي: يسمح بكشف تصحيحي
  لنفس (عامل، شهر) دون كسر تفرّد الكشف العادي.
- **لا تُخزَّن** `[6]` TOTAL_GAINS ولا `[11]` TOTAL_RETENUES ولا `[13]`
  COUT_EMPLOYEUR (قرار نهائي) — تُعاد حوسبتها من `bulletin_ligne` +
  المعاملات عند اللزوم.

---

## 6. `bulletin_ligne` — أسطر الكشف (لقطة كاملة)

كل سطر يُجمِّد خصائص الرُبريكة وقت التوليد، فتعديل الكتالوج لاحقاً لا
يُفسد كشفاً قديماً.

```sql
CREATE TABLE IF NOT EXISTS bulletin_ligne (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bulletin_id         INTEGER NOT NULL
                          REFERENCES bulletin(id) ON DELETE CASCADE,
    ordre_affichage     INTEGER NOT NULL DEFAULT 0,
    zone                TEXT    NOT NULL
                          CHECK (zone IN ('Z1', 'Z2', 'Z3', 'Z4', 'SYSTEME')),
    ligne_systeme       TEXT    CHECK (ligne_systeme IN ('A', 'B', 'C', 'D', 'E')),
    code_snapshot       TEXT    NOT NULL,
    libelle_snapshot    TEXT    NOT NULL,
    sens_snapshot       TEXT    NOT NULL
                          CHECK (sens_snapshot IN ('GAIN', 'RETENUE')),
    cotisable_snapshot  INTEGER CHECK (cotisable_snapshot IN (0, 1)),   -- NULL لأسطر النظام
    imposable_snapshot  INTEGER CHECK (imposable_snapshot IN (0, 1)),
    regime_irg_snapshot TEXT    CHECK (regime_irg_snapshot IN ('BAREME', 'TAUX_10')),
    base                TEXT,                            -- Decimal ؛ N/BASE (قد يكون NULL)
    taux                TEXT,                            -- Decimal ؛ TAUX (قد يكون NULL)
    montant             TEXT    NOT NULL DEFAULT '0',    -- Decimal موقَّع (+ مكسب / − اقتطاع)
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT,

    -- 'SYSTEME' ⇔ ligne_systeme محدَّد ؛ باقي المناطق ⇔ ligne_systeme = NULL
    CHECK ((zone = 'SYSTEME') = (ligne_systeme IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_ligne_bulletin
    ON bulletin_ligne (bulletin_id, ordre_affichage);
```

- `zone`: `Z1…Z4` للرُبريكات، `'SYSTEME'` للأسطر المقفلة الخمسة
  `[A]…[E]` (SPEC §2.3.1)، و`ligne_systeme` يسمّي أيّها.
- `sens_snapshot` **`NOT NULL`** — لازم لإعادة الطباعة ولإشارة المبلغ.
- `montant` **موقَّع**: موجب للمكاسب، سالب للاقتطاعات وأسطر الغياب
  (كما تُعرَض — SPEC §2.3.3). `mode` لا يُلقَط (غير لازم بعد التوليد).
- عند إعادة الحساب (`BROUILLON → CALCULE`) تُحذَف أسطر الكشف وتُدرَج من
  جديد؛ فـ`updated_at` هنا يبقى فارغاً عملياً (مضاف للاتّساق فقط).

---

## 7. مخطّط العلاقات

```
                        entreprise
          ┌────────────────┼────────────────┐
          │RESTRICT        │CASCADE         │RESTRICT
          ▼                ▼                ▼
     convention      rubrique_catalogue   employe
   (immuable, TRIGGER)                      │RESTRICT
          ┊ لقطة رقمية                       ▼
   (convention_version,                  bulletin ──┐ self, RESTRICT
    لا FK)  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈► bulletin ◄─┘ (remplace_bulletin_id,
                                          │CASCADE      type='CORRECTIF')
                                          ▼
                                    bulletin_ligne
```

Cardinalités : `entreprise 1–∞ {convention, rubrique_catalogue, employe}` ;
`employe 1–∞ bulletin` ; `bulletin 1–∞ bulletin_ligne` ;
`bulletin 0..1–∞ bulletin` (auto‑lien correctif).
`bulletin → convention` : لقطة `convention_version` فقط (لا FK).

---

## 8. الفهارس

| الفهرس | الجدول | الغرض |
|---|---|---|
| `ux_entreprise_nif` (UNIQUE جزئي، `WHERE nif IS NOT NULL`) | `entreprise` | NIF فريد حين يُدخَل |
| `ux_bulletin_normal_periode` (UNIQUE جزئي، `WHERE type='NORMAL'`) | `bulletin` | كشف عادي واحد لكل (عامل، شهر) |
| `idx_ligne_bulletin` (`bulletin_id, ordre_affichage`) | `bulletin_ligne` | جلب/ترتيب أسطر كشف |
| `idx_convention_entreprise` (`entreprise_id, version DESC`) | `convention` | أحدث اتفاقية لشركة |
| `idx_rubrique_entreprise` (`entreprise_id`) | `rubrique_catalogue` | كتالوج شركة |
| `idx_employe_entreprise` (`entreprise_id`) | `employe` | عمّال شركة |
| `idx_bulletin_employe` (`employe_id, periode`) | `bulletin` | كشوف عامل |

القاعدة القائمة بلا فهارس صريحة؛ هذه الجداول تُبرّرها أنماط
الاستعلام (شركة → عمّال → كشوف → أسطر).

---

## 9. تعيين قواعد التحقّق (SPEC §6) على مستوى الإنفاذ

| القاعدة | الإنفاذ |
|---|---|
| V7 (رُبريكة بلا cotisable/imposable) | **قاعدة**: `NOT NULL` بلا `DEFAULT` |
| V16 (كشف مثبَّت بلا params/convention version) | **قاعدة**: `NOT NULL` + `CHECK` التثبيت |
| كشف تصحيحي بلا أصل / عادي بأصل | **قاعدة**: `CHECK` type/remplace |
| كشف عادي مكرَّر لنفس (عامل، شهر) | **قاعدة**: الفهرس الجزئي الفريد |
| تعديل اتفاقية | **قاعدة**: `TRIGGER convention_no_update` |
| V5 (معامل س.إضافية < 1,50) | **قاعدة**: `CHECK (CAST(...) >= 1.5)` + فحص كود |
| V2 (وعاء CNAS دون الأرضية بسبب غياب) | **كود**: `bulletin.avertissements_json` |
| V11 (إدراج رُبريكة بين [C] و[D]) · V12 (تعديل سطر نظامي) | **كود** (منطق المناطق) |
| V13 (اعتماد دائري) · V14 (`depend_de` لرمز غير موجود) | **كود** (ترتيب طوبولوجي) |
| V15 (كشف لشركة اتفاقيتها غير مؤكَّدة) | **كود**: فحص `convention.confirme` |
| V9 (تاريخ الكشف خارج صلاحية params) · V10 (params بلا تغيير نسخة) | **كود**: `config_loader` / بصمة الملف |
| V1/V2/V3/V4/V6/V8 | **كود** (مقارنات على النتيجة) |

---

## 10. قرارات المهمة 11 (مطبَّقة)

| # | القرار | الأثر |
|---|---|---|
| 1 | `nif` فريد جزئي | `CREATE UNIQUE INDEX ux_entreprise_nif … WHERE nif IS NOT NULL` |
| 2 | `date_sortie` في `employe` | عمود `date_sortie TEXT` مضاف |
| 3 | لا `convention_id` (لا في `employe` ولا في `bulletin`) | `bulletin → convention` لقطة `convention_version` فقط، بلا FK |
| 4 | لا `triggers` لـ`updated_at` | يُضبط بالكود فقط |
| 5 | لا تخزين لـ`[6]`/`[11]`/`[13]` | `bulletin` يحمل `[A]…[E]` فقط؛ الباقي يُعاد حوسبته |

### مؤجَّل (خارج نطاق المهمة 11)

- ربط `entreprise` بـ`clients` (عمود `client_id` اختياري) — يبقى
  مستقلاً حالياً.
- مواءمة `convention.taux_hs_*` مع `compute_sequence` (الاتفاقية تعطي
  المعامل، والإدخال يعطي «س نهار/ليل/عطلة» بدل `HeureSupp.coef`).
- بذرة الكتالوج الافتراضي (SPEC §2.2) — `seed_default_catalogue`.
- الواجهة.

---

## 11. لائحة الهجرات — `programme/payroll/repository.py`

`repository.py` يملك لائحة هجرات مرقّمة وجدول تتبّع، **مستقلاً** عن
`programme/database.py:init_db()` (الذي يبقى مسؤولاً عن جداول CD/الزبائن
/الدخول — «الحالة الأساسية» قبل نظام الهجرات).

```python
_MIGRATIONS = [
    (1, _m1_baseline),   # علامة نسخة فقط — لا DDL (الجداول المشتركة يُنشئها init_db)
    (2, _m2_payroll),    # جداول الأجور الست + الفهارس + trigger convention
]
```

### جدول التتبّع

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

### `run_migrations(conn=None)`

1. يُنشئ `schema_migrations` إن غاب.
2. **تمييز قاعدة موجودة**: إن غابت الهجرة 1 من التتبّع **وكان جدول
   `cd_documents` موجوداً** (قاعدة سبقت نظام الهجرات) → تُسجَّل الهجرة 1
   كـ«حالة أساسية» بلا تنفيذ.
3. يشغّل كل `(v, fn)` حيث `v` غير مسجَّلة، بالترتيب: `fn(cur)` ثم
   `INSERT INTO schema_migrations(version)`، ثم `commit`.
4. يُستدعى من **بداية** `init_db()` (قبل إنشاء الجداول المشتركة، حتى
   يكون تمييز «موجودة/جديدة» صحيحاً) عبر استيراد محلّي (تفادي دور
   استيراد دائري). لا تغيير في `main.py`.

### السلوك المضمون

| الحالة | النتيجة |
|---|---|
| قاعدة **موجودة** (فيها `cd_documents` وبيانات CD) | الهجرة 1 «حالة أساسية»، **تُنفَّذ الهجرة 2 وحدها**؛ بيانات CD سليمة (الهجرة 2 تُنشئ جداول جديدة فقط) |
| قاعدة **جديدة** | `schema_migrations` ثم الهجرة 1 (علامة) ثم الهجرة 2 — بالترتيب |
| إعادة التشغيل | `applied` يحوي 1 و2 → لا شيء يُنفَّذ (idempotent) |
