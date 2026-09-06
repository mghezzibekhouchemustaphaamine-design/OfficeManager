# تدقيق طبقة قاعدة البيانات — OfficeManager

> وثيقة قراءة فقط (لم يُعدَّل أي كود). المصدر: `programme/database.py`،
> `programme/auth.py`، `programme/settings.py`، `programme/case_ops.py`،
> `programme/utils.py`، ومستدعوها في `ui/`.
> المحرّك: **SQLite** عبر `sqlite3` من المكتبة القياسية فقط.
> الملف: `office_system.db` بجذر المشروع (`programme/database.py:DB_PATH`)،
> مُستثنى من git (`.gitignore`).

---

## 1. المخطط الكامل (Schema)

كل الجداول تُنشأ في `init_db()` بأمر `executescript` واحد
(`CREATE TABLE IF NOT EXISTS`)، ثم تُضاف أعمدة لاحقة بـ`ALTER TABLE`
مشروطة (انظر §2). لا فهارس (indexes) صريحة عدا ما يفرضه
`PRIMARY KEY` / `UNIQUE`. كل الاتصالات: `PRAGMA foreign_keys = ON`،
`row_factory = sqlite3.Row`.

الطوابع الزمنية نصّية بتوقيت الجهاز: `datetime('now','localtime')`.

### 1.1 الجداول الحيّة

#### `clients` — الزبائن (مشترك بين كل الخدمات)

| العمود | النوع | قيود / افتراضي | ملاحظة |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | |
| `name` | TEXT | NOT NULL | اسم العرض، قابل للتعديل |
| `phone` | TEXT | | |
| `email` | TEXT | | |
| `address` | TEXT | | |
| `notes` | TEXT | | |
| `created_at` | TEXT | DEFAULT `datetime('now','localtime')` | |
| `folder_name` | TEXT | *(ALTER)* | اسم مجلد الزبون على القرص — يُحسب مرّة في `create_client` ويبقى ثابتاً حتى لو تغيّر `name` |

#### `cd_documents` — سجلّ كل مستند CD (Change Devise) مولَّد فعلياً

| العمود | النوع | قيود / افتراضي | ملاحظة |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | مُعرّف الحالة؛ الشريط الجانبي والسجلّ يحملانه مباشرة |
| `dossier_no` | TEXT | | رقم البوردرو (`no`) — للعرض/البحث |
| `passager` | TEXT | | اسم الراكب — للعرض/البحث |
| `passport_no` | TEXT | | للبحث |
| `doc_date` | TEXT | | تاريخ المستند (ISO `YYYY-MM-DD` أو NULL) |
| `agence` | TEXT | | للعرض |
| `guichet` | TEXT | | للعرض |
| `eur_amount` | REAL | | للعرض/الفرز |
| `dzd_amount` | REAL | | للعرض/الفرز |
| `file_path` | TEXT | **NOT NULL** | مسار ملف Word المُولَّد |
| `full_data_json` | TEXT | *(في CREATE + ALTER)* | كامل `collect_data()` كـJSON — يُعيد بناء كل حقول الاستمارة للفتح/التعديل/إعادة الطباعة |
| `created_at` | TEXT | DEFAULT `datetime('now','localtime')` | |
| `pdf_path` | TEXT | *(ALTER)* | مسار PDF الدائم (فاضٍ لمستندات قديمة قبل التوليد التلقائي) |
| `client_id` | INTEGER | *(ALTER)* | ربط منطقي بـ`clients.id` — **بلا FOREIGN KEY** (انظر §1.4) |
| `updated_at` | TEXT | *(ALTER)* | يُحدَّث في كل حفظ لاحق / نقل / إعادة تسمية — مصدر «آخر تعديل» للترتيب |

#### `hr_documents` — سجلّ مستندات الموارد البشرية / الأجور

نفس فكرة `cd_documents`. `screen_key` يميّز نوع الوثيقة
(`HRDocScreen.SCREEN_KEY`: `hr_attestation_travail`, `hr_titre_conge`,
`hr_bulletin_paie`, `hr_releve_annuel`).

| العمود | النوع | قيود / افتراضي |
|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT |
| `screen_key` | TEXT | **NOT NULL** |
| `doc_label` | TEXT | |
| `employer_name` | TEXT | |
| `employee_name` | TEXT | |
| `doc_date` | TEXT | |
| `client_id` | INTEGER | ربط منطقي بلا FK |
| `file_path` | TEXT | **NOT NULL** |
| `pdf_path` | TEXT | |
| `full_data_json` | TEXT | `json.dumps` مباشر (بلا تحويل تواريخ — شاشات HR تمرّر نصوصاً) |
| `created_at` | TEXT | DEFAULT `datetime('now','localtime')` |

#### `users` — حساب الدخول الوحيد (`programme/auth.py`)

حساب واحد لكل تنصيب. `password_hash` بصيغة `"salt$hash"`
(PBKDF2‑HMAC‑SHA256، مكتبة قياسية).

| العمود | النوع | قيود / افتراضي |
|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT |
| `username` | TEXT | **UNIQUE NOT NULL** |
| `password_hash` | TEXT | **NOT NULL** |
| `created_at` | TEXT | DEFAULT `datetime('now','localtime')` |
| `recovery_code_hash` | TEXT | *(ALTER)* — تجزئة كود الاسترجاع؛ صحّته تحذف صف الحساب فقط |

#### `login_sessions` — سجلّ الدخول/الخروج

سطر جديد لكل دخول ناجح (`create_login_session`)، ويُحدَّث `logout_at`
لنفس السطر عند الإغلاق العادي.

| العمود | النوع | قيود / افتراضي |
|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT |
| `username` | TEXT | NOT NULL |
| `login_at` | TEXT | DEFAULT `datetime('now','localtime')` |
| `logout_at` | TEXT | NULL حتى الإغلاق |

#### `app_settings` — إعدادات key/value (`programme/settings.py`)

| العمود | النوع | قيود |
|---|---|---|
| `key` | TEXT | **PRIMARY KEY** |
| `value` | TEXT | (يُخزَّن دائماً كنص — `str(value)`) |

مفتاح مستخدَم حالياً: `auto_lock_minutes`.

### 1.2 جداول مُنشأة لكن **بلا مسار كود حيّ** (إرث الواجهة القديمة)

`init_db()` لا يزال يُنشئها، لكن لا يقرأها/يكتبها أي كود بعد إزالة
تبويبات (Dashboard / Clients / Invoices / Tasks / Documents) القديمة.
`programme/utils.py` (`generate_invoice_number`, `export_rows_to_csv`)
غير مُستدعى من أي مكان.

| الجدول | الأعمدة | علاقات معلَنة |
|---|---|---|
| `invoices` | `id` PK · `invoice_number` TEXT UNIQUE NOT NULL · `client_id` INTEGER · `date` TEXT NOT NULL · `due_date` TEXT · `status` TEXT NOT NULL DEFAULT `'غير مدفوعة'` · `notes` TEXT · `created_at` TEXT | `FK client_id → clients(id) ON DELETE SET NULL` |
| `invoice_items` | `id` PK · `invoice_id` INTEGER NOT NULL · `description` TEXT NOT NULL · `quantity` REAL NOT NULL DEFAULT 1 · `unit_price` REAL NOT NULL DEFAULT 0 | `FK invoice_id → invoices(id) ON DELETE CASCADE` |
| `tasks` | `id` PK · `title` TEXT NOT NULL · `description` TEXT · `due_date` TEXT · `due_time` TEXT · `priority` TEXT DEFAULT `'عادية'` · `status` TEXT NOT NULL DEFAULT `'قيد الانتظار'` · `client_id` INTEGER · `created_at` TEXT | `FK client_id → clients(id) ON DELETE SET NULL` |
| `documents` | `id` PK · `title` TEXT NOT NULL · `file_path` TEXT NOT NULL · `category` TEXT · `client_id` INTEGER · `added_at` TEXT | `FK client_id → clients(id) ON DELETE SET NULL` |

### 1.3 مخطط العلاقات

```
                         ┌─────────────┐
                         │   clients   │
                         │  id (PK)    │
                         │  folder_name│
                         └──────┬──────┘
       ربط منطقي (بلا FK)       │        FK معلَن (جداول إرثية)
   ┌───────────────┬────────────┼───────────┬──────────────┐
   ▼               ▼            ▼           ▼              ▼
cd_documents   hr_documents   invoices   tasks        documents
 client_id      client_id     client_id  client_id    client_id
 (INTEGER)      (INTEGER)     (FK SET    (FK SET       (FK SET
                              NULL)       NULL)         NULL)
                                 │
                                 ▼ FK CASCADE
                            invoice_items
                             invoice_id

users ─┐  (لا علاقة)      login_sessions   app_settings
       └── حساب واحد؛ username فقط يُنسَخ نصّياً في login_sessions
```

### 1.4 ملاحظات على التكامل المرجعي

- `PRAGMA foreign_keys = ON` مضبوط لكل اتصال — فقيود الـFK على
  `invoices` / `invoice_items` / `tasks` / `documents` **ستُطبَّق فعلاً
  لو استُخدمت تلك الجداول**.
- `cd_documents.client_id` و`hr_documents.client_id` **بلا `FOREIGN KEY`**
  (SQLite لا يسمح بإضافة قيد FK بسهولة عبر `ALTER TABLE` على جدول
  موجود). التكامل يُفرَض بالكود:
  - `delete_client(id)` يرفض الحذف إذا `client_has_documents(id)`
    (`SELECT 1 FROM cd_documents WHERE client_id=?`). **ملاحظة:** لا
    يفحص `hr_documents`.
  - الاستعلامات تربط بـ`LEFT JOIN clients ON cd.client_id = c.id`،
    فحذف/فقدان الزبون يُظهر `client_name = NULL` بلا انهيار.
- لا قيود `CHECK` ولا `TRIGGER` في المخطط.

---

## 2. الإنشاء والترقية (Migrations)

**لا يوجد نظام migrations.** لا Alembic، لا جدول `schema_version`، لا
ملفات ترقية مرقّمة، لا ترقية تنازلية (downgrade).

### الآلية الفعلية — `programme/database.py:init_db()`

يُستدعى **مرّة عند الإقلاع** من `main.py:29` (بعد بوابة الدخول).

1. **`cur.executescript(...)`** — كتلة واحدة فيها
   `CREATE TABLE IF NOT EXISTS` لكل الجداول العشرة. إذا وُجد الجدول لا
   يُلمس (وبالتالي `CREATE` لا يضيف أعمدة لجدول قديم).

2. **حراسات `ALTER TABLE` يدوية idempotent** — لكل عمود أُضيف بعد أن
   كان الجدول موجوداً بقواعد بيانات مستخدمين سابقة:

   ```python
   existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(cd_documents)")}
   if "full_data_json" not in existing_cols:
       cur.execute("ALTER TABLE cd_documents ADD COLUMN full_data_json TEXT")
   # ... وهكذا
   ```

   | الجدول | الأعمدة المُضافة بهذه الطريقة |
   |---|---|
   | `cd_documents` | `full_data_json`, `pdf_path`, `client_id`, `updated_at` |
   | `users` | `recovery_code_hash` |
   | `clients` | `folder_name` |

3. **لا backfill** للبيانات — العمود الجديد يبقى `NULL` للصفوف القديمة،
   والكود يتعامل مع `NULL` صراحةً (مثلاً `deserialize_cd_data(None) → None`
   فيُفتح المستند القديم بالنظام بدل إعادة بناء حقوله).

4. **قاعدة بيانات جديدة تماماً** = نتيجة `executescript` وحده (كل
   الأعمدة موجودة، فحراسات `ALTER` كلها تتخطّى).

### تبعات هذا النهج

- الترقية للأمام سلسة وآمنة (تشغيل البرنامج يكفي).
- لا سجلّ لإصدار المخطط ولا تحقّق من انحراف مخطط قاعدة بيانات المستخدم.
- أي تغيير مستقبلي = سطر `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`
  إضافي بنفس النمط. لا يمكن حذف/إعادة تسمية/تغيير نوع عمود بهذا النمط
  (يتطلّب إعادة إنشاء الجدول يدوياً).

> غير ذي صلة: `V10` في مواصفة الأجور («تغيير `params_*.json` دون تغيير
> رقم النسخة») تخصّ ملفات المعاملات القانونية لا مخطط قاعدة البيانات.

---

## 3. الواجهة العمومية لـ `programme/database.py`

الوحدة بلا صنف — دوال حرّة تفتح اتصالاً وتغلقه لكل نداء (لا تجميع
اتصالات، لا معاملات ممتدّة).

### ثوابت

| الاسم | القيمة |
|---|---|
| `DB_PATH` | `<جذر المشروع>/office_system.db` |
| `_PROJECT_ROOT` | `dirname(dirname(__file__))` (يخرج من `programme/` للجذر) |

### الاتصال والتهيئة

| الدالة | التوقيع | تُرجع |
|---|---|---|
| `get_connection()` | `()` | `sqlite3.Connection` — `foreign_keys=ON`، `row_factory=sqlite3.Row` |
| `init_db()` | `()` | `None` — تُنشئ الجداول وتطبّق حراسات `ALTER` (§2) |

### تسلسل بيانات استمارة CD

| الدالة | التوقيع | تُرجع / تفعل |
|---|---|---|
| `serialize_cd_data(data)` | `data: dict` | `str` JSON. تنسخ `data`، تحوّل `data["date"]` و`data["date_delivrance"]` من `date` إلى ISO، ثم `json.dumps(ensure_ascii=False)` |
| `deserialize_cd_data(full_data_json)` | `str \| None` | `dict \| None`. عكس ما سبق (ISO → `date`). تُرجع `None` إذا النص فاضٍ أو JSON تالف |

### الزبائن (`clients`)

| الدالة | التوقيع | تُرجع / تفعل |
|---|---|---|
| `list_clients(query="", limit=50)` | `query: str, limit: int` | `list[dict]` — `name LIKE %query%` (أو الكل)، مرتّبة `name COLLATE NOCASE`، محدودة بـ`limit` |
| `get_client(client_id)` | `client_id: int` | `dict \| None` — صف الزبون كامل |
| `create_client(name, phone=None, email=None, address=None, notes=None)` | كلها `str \| None` عدا `name` | `int` — `id` الجديد. تحسب `folder_name` فريداً: `_sanitize_folder_name(name)` + لاحقة `_02`, `_03`… عند التصادم (مقارنة `casefold`) |
| `client_has_documents(client_id)` | `client_id: int` | `bool` — وجود أي صف `cd_documents` بهذا `client_id` (لا يفحص `hr_documents`) |
| `delete_client(client_id)` | `client_id: int` | `bool` — `False` بلا حذف إذا `client_has_documents`؛ غير ذلك يحذف الصف ويُرجع `True` |

### مستندات CD (`cd_documents`)

`record` = dict بمفاتيح: `dossier_no`, `passager`, `passport_no`,
`doc_date`, `agence`, `guichet`, `eur_amount`, `dzd_amount`,
**`file_path` (إلزامي)**, `pdf_path`, `client_id`. البقية عبر
`.get()` (تصير `NULL`).

| الدالة | التوقيع | تُرجع / تفعل |
|---|---|---|
| `log_cd_document(record, full_data=None)` | `record: dict, full_data: dict \| None` | `int` — `INSERT` صفّاً جديداً؛ `full_data` (إن وُجد) → `serialize_cd_data` → عمود `full_data_json`. يُرجع `id` الصف (يُحفَظ كـ`loaded_from.row_id` للتبويب) |
| `update_cd_document(row_id, record, full_data=None)` | `row_id: int, record: dict, full_data` | `None` — `UPDATE` نفس الصف لكل الأعمدة + `updated_at=datetime('now','localtime')` |
| `get_cd_document(row_id)` | `row_id: int` | `dict \| None` — الصف كامل (يشمل `full_data_json`) |
| `search_cd_documents(query="", limit=200, client_id=None)` | | `list[dict]` — `cd.* + c.name AS client_name` عبر `LEFT JOIN clients`. فلترة نصّية اختيارية على `passager / dossier_no / passport_no`، وفلترة اختيارية بـ`client_id` (بالمُعرّف). ترتيب `cd.id DESC` |
| `list_cd_documents_for_tree()` | `()` | `list[dict]` — أعمدة مختارة: `id, file_path, pdf_path, client_id, doc_date, created_at, updated_at` + `client_name`, `client_folder_name` (`LEFT JOIN clients`). بلا فلترة — الشريط الجانبي يبني الشجرة كاملة ثم يفلتر بصرياً. ترتيب `cd.id DESC` |

### مستندات الموارد البشرية (`hr_documents`)

`record` = dict بمفاتيح: **`screen_key` (إلزامي)**, `doc_label`,
`employer_name`, `employee_name`, `doc_date`, `client_id`,
**`file_path` (إلزامي)**, `pdf_path`.

| الدالة | التوقيع | تُرجع / تفعل |
|---|---|---|
| `log_hr_document(record, full_data=None)` | `record: dict, full_data: dict \| None` | `int` — `INSERT`؛ `full_data` → `json.dumps(ensure_ascii=False)` مباشرة (بلا تحويل تواريخ) → `full_data_json`. يُرجع `id` |
| `list_hr_documents(screen_key=None, query="", limit=100)` | | `list[dict]` — كل الأعمدة (`SELECT *`). فلترة اختيارية بـ`screen_key` وبنص على `employee_name / employer_name`. ترتيب `id DESC` |

### دوال في وحدات أخرى تكتب مباشرة على جداول قاعدة البيانات

| الوحدة | يمسّ | العملية |
|---|---|---|
| `programme/auth.py` | `users`, `login_sessions` | `has_account()`, `create_account(username, password)`, `verify_login(username, password)`, `get_current_username()`, `update_account(current_password, new_username=None, new_password=None)`, `reset_account_with_recovery_code(code)` (يحذف صف `users`)، `record_login(username)`، `record_logout_current()`، `generate_recovery_code(groups=4, group_length=4)` |
| `programme/settings.py` | `app_settings` | `get_setting`, `set_setting` (`INSERT OR REPLACE`)، وغلافا `get/set_auto_lock_minutes` |
| `programme/case_ops.py` | `cd_documents` | `move_case(row_id, target_client_id)` و`rename_case(row_id, new_base_name)` — ينقلان الملفات فيزيائياً ثم `UPDATE cd_documents SET file_path=?, pdf_path=?, [client_id=?,] updated_at=datetime('now','localtime') WHERE id=?` |

---

## 4. حفظ واسترجاع عميل CD — مثال كامل

### 4.1 إنشاء/اختيار الزبون

`ui/common/client_picker.py` — `ClientPickerEntry` مكوّن مستقل يحمل
`client_id` داخلياً.

- **اختيار موجود:** المستخدم يكتب/ينتقي من `list_clients(query)`؛
  المكوّن يخزّن `id` المختار.
- **إنشاء جديد:** حوار `_PickClientDialog._save()`:
  ```python
  self.created_id = create_client(
      name,
      phone=... or None, email=... or None,
      address=... or None, notes=... or None,
  )
  ```
  داخل `create_client`: يُحسب `folder_name` (مثلاً الاسم
  `" Omar Ben Ali"` → `"Omar Ben Ali"`؛ ولو مستعمَل → `"Omar Ben Ali_02"`)،
  ثم `INSERT INTO clients (name, phone, email, address, notes, folder_name)`،
  ويُرجع `id`.

`get_client_id()` بالمكوّن يُرجع هذا الـ`id` (أو `None` لزبون عابر).

### 4.2 جمع بيانات الاستمارة

`ui/cd/tab.py:collect_data()` → dict (التواريخ **كائنات `date`**):

```python
{
  "no": "12345",                    # رقم البوردرو
  "date": date(2026, 9, 6),
  "time": "09:30",
  "client_id": 7,                   # ← من client_picker.get_client_id()
  "agence_no": "015", "agence": "AGENCE ALGER CENTRE",
  "devise_code": "EUR", "devise": "EURO",
  "guichet_no": "02", "guichet": "GUICHET 2",
  "caisse_no": "01", "caisse": "CAISSE 1",
  "guichetier": "34521",
  "passager": "OMAR BEN ALI",
  "passport_no": "AB1234567",
  "date_delivrance": date(2022, 1, 15),
  "taux": 145.32, "eur": 200.0, "dzd": 29064.0,
}
```

### 4.3 مسار الحفظ (`ui/cd/tab.py`، دالة الحفظ)

1. **تحديد مجلد الإخراج:**
   - تبويب «محمَّل» → نفس المسارات (إلا «حفظ في مكان آخر»).
   - جديد + زبون معروف → `get_client_dir(clients.folder_name)` =
     `…/Desktop/travail/<folder_name>/`.
   - غير ذلك → `travail/Autre/<YYYY-MM من doc_date>/`.
2. **توليد الملفات:** `generate_cd_document(data, out_path=docx_target)`
   ثم `generate_cd_pdf(data, out_path=pdf_target)` (فشل الـPDF ثانوي).
3. **بناء `record`:**
   ```python
   record = {
     "dossier_no": data["no"],                                  # "12345"
     "passager": data["passager"],                              # "OMAR BEN ALI"
     "passport_no": data["passport_no"],                        # "AB1234567"
     "doc_date": data["date"].isoformat() if data["date"] else None,  # "2026-09-06"
     "agence": data["agence"], "guichet": data["guichet"],
     "eur_amount": data["eur"], "dzd_amount": data["dzd"],       # 200.0 / 29064.0
     "file_path": path,           # …/travail/Omar Ben Ali/CD_12345.docx
     "pdf_path": pdf_path,        # …/travail/Omar Ben Ali/CD_12345.pdf
     "client_id": target_client_id,   # 7
   }
   ```
4. **الكتابة على قاعدة البيانات:**
   ```python
   row_id = loaded_from.get("row_id") if loaded_from else None
   if row_id is not None:
       update_cd_document(row_id, record, full_data=data)   # نفس الحالة
   else:
       row_id = log_cd_document(record, full_data=data)     # حالة جديدة
   ```
   - الأعمدة القياسية (`dossier_no`, `passager`, …) للعرض/البحث السريع.
   - `full_data=data` → `serialize_cd_data(data)`: `date`/`date_delivrance`
     → ISO، ثم `json.dumps(ensure_ascii=False)` → عمود `full_data_json`
     (النسخة الكاملة القابلة لإعادة البناء).
5. **الصف الناتج في `cd_documents`:**

   | العمود | القيمة |
   |---|---|
   | `id` | (تلقائي، مثلاً 41) |
   | `dossier_no` | `12345` |
   | `passager` | `OMAR BEN ALI` |
   | `passport_no` | `AB1234567` |
   | `doc_date` | `2026-09-06` |
   | `agence` / `guichet` | `AGENCE ALGER CENTRE` / `GUICHET 2` |
   | `eur_amount` / `dzd_amount` | `200.0` / `29064.0` |
   | `file_path` | `…/travail/Omar Ben Ali/CD_12345.docx` |
   | `pdf_path` | `…/travail/Omar Ben Ali/CD_12345.pdf` |
   | `client_id` | `7` |
   | `full_data_json` | `{"no":"12345","date":"2026-09-06","time":"09:30","client_id":7,"agence_no":"015",…,"date_delivrance":"2022-01-15","taux":145.32,"eur":200.0,"dzd":29064.0}` |
   | `created_at` | `2026-09-06 09:31:12` |
   | `updated_at` | `NULL` (أو طابع الحفظ اللاحق) |

6. **ربط التبويب:** بعد النجاح، التبويب يخزّن
   `loaded_from = {"row_id": 41, "file_path": …, "pdf_path": …}` — كل
   حفظ تالٍ له يستدعي `update_cd_document(41, …)` (حتى لو تغيّر رقم
   البوردرو أو الزبون).

### 4.4 مسار الاسترجاع

**أ) من الشريط الجانبي** (`ui/common/file_explorer.py` + `ui/cd/tab.py`):

1. الشجرة مبنية من `list_cd_documents_for_tree()` — كل ورقة تحمل
   `row_id`.
2. نقرة مزدوجة / «فتح» → `ui/cd/tab.py:_open_case_readonly(row_id, file_path)`:
   ```python
   row  = get_cd_document(row_id)              # dict كامل أو None
   data = deserialize_cd_data(row["full_data_json"])
   if data is None:            # صف قديم بلا full_data_json
       return False            # يُفتح الملف بالنظام بدل إعادة بناء الحقول
   self._open_data_in_new_tab(
       data,
       source_row_id=row["id"],
       source_file_path=row.get("file_path"),
       source_pdf_path=row.get("pdf_path"),
       source_client_id=row.get("client_id"),
   )
   self.set_form_readonly(True)     # حماية «عمل منتهٍ»
   ```
3. `data["date"]` و`data["date_delivrance"]` تعودان كائنات `date`؛ بقية
   الحقول تملأ الاستمارة كما كانت. `source_client_id` يُعاد ضبطه في
   `client_picker`.
4. لو نفس `row_id` مفتوح في تبويب أصلاً → يقفز إليه بدل فتح تبويب ثانٍ.

**ب) من شاشة السجلّ** (`ui/cd/history.py`): `search_cd_documents(query, limit, client_id)`
لعرض الصفوف (مع `client_name` من الـJOIN)، و`deserialize_cd_data` عند
فتح صف.

**ج) نقل/إعادة تسمية حالة**: `case_ops.move_case(row_id, target_client_id)`
/ `rename_case(row_id, new_base_name)` — ينقلان `file_path`/`pdf_path`
فيزيائياً ثم `UPDATE cd_documents` (+ `updated_at`، و`client_id` في
`move_case`).

### 4.5 خصائص الربط بالزبون

- `cd_documents.client_id` مصدره الوحيد `collect_data()["client_id"]`
  = `ClientPickerEntry.get_client_id()`.
- لا `FOREIGN KEY`؛ الحماية: `delete_client` يرفض إن كان للزبون أي
  مستند CD.
- تعديل اسم الزبون **لا** يغيّر `folder_name` ولا يحرّك ملفاته —
  مقصود (سلوك نظام ملفات حقيقي).
- زبون عابر (بلا اختيار) → `client_id = NULL` → الملف في
  `travail/Autre/<شهر>/`.
