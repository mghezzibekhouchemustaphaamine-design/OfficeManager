# خطة تنفيذ: الزبائن + الشريط الجانبي المبني على قاعدة البيانات

**اقرأ `docs/cd-clients-architecture.md` كاملاً أولاً — هذا الملف خطة
تنفيذ مرحلية بأسماء دوال/ملفات حقيقية من الكود الحالي، مبنية عليه. لا
تبدأ أي تعديل قبل قراءة الاثنين.**

هذا تنفيذ لتصميم مقرَّر بالكامل — مو نقاش. وين ما فيه تفصيل تنفيذي دقيق
لسا مفتوح (نادر، ومُعلَّم صراحة تحت بـ"⚠️ قرار تنفيذي")، خذ القرار
الأنسب تقنياً وثبّته بتعليق بالكود يشرح ليش — لا توقف التنفيذ لتسأل.

نفّذ **مرحلة-مرحلة بالترتيب المذكور**، وكل مرحلة (أو مجموعة مراحل
مترابطة) بكوميت مستقل خاص فيها — بنفس اصطلاح المشروع (`مرجع سابع عشر:
...`، تكملة للترقيم الحالي بـ`git log`)، مع سطر بـ`docs/CHANGELOG.md`
يشرح "وش تغيّر وليش" بنفس أسلوب المراجع السابقة هناك. شغّل البرنامج
يدوياً (`python main.py`) وجرّب السيناريوهات المذكورة بآخر كل مرحلة قبل
ما تنتقل للي بعدها — ماكو اختبارات آلية بالمشروع حالياً (لا `pytest` ولا
مجلد `tests/`)، فالتجربة اليدوية هي طريقة التحقق الوحيدة المتاحة.

---

## مرحلة 1 — قاعدة البيانات (`programme/database.py`)

### 1.1 تعديل `init_db()`
أضف بنفس نمط `full_data_json`/`pdf_path`/`recovery_code_hash` الموجود
أصلاً (فحص `PRAGMA table_info` ثم `ALTER TABLE` لو العمود غير موجود —
حتى قواعد بيانات موجودة أصلاً بأجهزة المستخدمين تترقّى بسلاسة بلا فقدان
بيانات):

- `cd_documents.client_id INTEGER` (بلا `FOREIGN KEY` صريح بـ`ALTER
  TABLE` — SQLite ما يدعمها بسهولة على جدول موجود؛ الربط منطقي بالكود
  بس، زي باقي الجدول).
- `cd_documents.updated_at TEXT` — يتحدّث بـ`update_cd_document` (تحت).
- `clients.folder_name TEXT` — اسم مجلد الزبون الفعلي على القرص، يُحسب
  **مرة وحدة** عند إنشاء الزبون (`create_client`، تحت) ويبقى ثابت بعدها
  حتى لو تغيّر اسم الزبون لاحقاً (⚠️ قرار تنفيذي: تعديل اسم زبون **لا**
  يغيّر اسم مجلده — يفادي إعادة نقل ملفات كل مرة يتعدّل فيها اسم، وسلوك
  متوقَّع بأي نظام ملفات حقيقي. وثّق هذا بتعليق بجانب العمود).

### 1.2 دوال عملاء جديدة
```python
def list_clients(query="", limit=50):
    """بحث بالاسم (LIKE) — يرجّع [{id, name, phone, ...}]. query فاضي
    يرجّع الكل (بحد limit)، الأحدث أولاً أو أبجدي (اختر أبجدي — أنسب
    لمكوّن اختيار)."""

def get_client(client_id):
    """صف واحد أو None."""

def create_client(name, phone=None, email=None, address=None, notes=None):
    """يحسب folder_name (sanitize نفس أسلوب _named_path بـdocument.py:
    أحرف/أرقام/مسافة/شرطة فقط)، يفحص تصادم مع folder_name موجود أصلاً
    (يضيف _02.. تلقائياً — نفس اصطلاح تصادم اسم ملف CD)، يُدرج الصف،
    يرجّع id."""

def client_has_documents(client_id):
    """True لو فيه أي سطر cd_documents.client_id == client_id."""

def delete_client(client_id):
    """يرفض (يرجّع False، ما يحذف) لو client_has_documents. غير هيك
    يحذف ويرجّع True."""
```

### 1.3 تعديل `log_cd_document`/`update_cd_document`
أضف `client_id` كباراميتر اختياري بـ`record` (زي باقي المفاتيح — يُقرأ
بـ`record.get("client_id")`)، أضفه لعمود INSERT/UPDATE. بـ
`update_cd_document`: أضف `updated_at=datetime('now','localtime')`
لجملة الـUPDATE (عمود إضافي بالـSET).

### 1.4 تعديل `search_cd_documents`
أضف باراميتر `client_id=None` — لو انعطى، `WHERE client_id = ?` إضافي
(مع شرط النص الموجود بـAND لو query معطى بردو). أضف `LEFT JOIN clients
ON cd_documents.client_id = clients.id` وأرجع `clients.name AS
client_name` بعمود إضافي بكل صف (يحتاجه عمود "الزبون" بالسجل — راجع
مرحلة 4).

### 1.5 دالة جديدة: بيانات الشريط الجانبي
```python
def list_cd_documents_for_tree():
    """يرجّع كل صفوف cd_documents (id, file_path, pdf_path, client_id,
    doc_date, created_at, updated_at) + client_name (LEFT JOIN clients)
    — المصدر الوحيد اللي يبني منه الشريط الجانبي شجرته (راجع مرحلة 6).
    بلا أي فلترة نصية — الشريط يبني الشجرة كاملة ثم يفلتر بصرياً وقت
    البحث."""
```

---

## مرحلة 2 — المسارات (`programme/paths.py`)

أضف (بلا لمس أي دالة موجودة):

```python
def get_autre_dir():
    """travail/Autre — مكان الشغل بلا زبون معروف، مشترك بين كل الخدمات."""
    return os.path.join(get_travail_root(), "Autre")


def get_client_dir(folder_name):
    """travail/<folder_name> — مجلد زبون، مشترك بين كل الخدمات. folder_name
    يجي من clients.folder_name (محسوب مرة وحدة بـcreate_client)، لا من
    اسم الزبون الحي مباشرة."""
    return os.path.join(get_travail_root(), folder_name)
```

---

## مرحلة 3 — عملية "نقل الحالة" الموحّدة (ملف جديد `programme/case_ops.py`)

هذا قلب البند 2 بمستند التصميم — **دالة واحدة تُستخدم من كل مكان** (أول
حفظ بزبون معروف، ربط/تغيير/فك ربط من السجل، سحب-وإفلات بالشريط). لا
تكرّر منطق النقل بأي مكان ثاني.

```python
import os
import shutil
from datetime import date

from programme.database import get_connection, get_client
from programme.paths import get_autre_dir, get_client_dir


def _target_dir_for(client_id, doc_date_iso, created_at_str):
    """المجلد الهدف: مجلد الزبون (مسطّح) لو client_id معطى، وإلا
    Autre/<YYYY-MM> — الشهر من doc_date لو متوفر، وإلا من created_at
    (أبداً datetime.now() — راجع البند 2 بمستند التصميم)."""
    if client_id is not None:
        client = get_client(client_id)
        return get_client_dir(client["folder_name"])
    month_source = doc_date_iso or (created_at_str or "")[:10]
    month = month_source[:7] if month_source else date.today().isoformat()[:7]
    return os.path.join(get_autre_dir(), month)


def _resolve_collision(dest_dir, base_name, ext):
    """نفس منطق التصادم الموجود أصلاً بـ_named_path/رقم البوردرو
    (يضيف _02، _03... لحد ما يلقى اسم فاضي بنفس المجلد الهدف بس)."""
    candidate = f"{base_name}.{ext}"
    n = 2
    while os.path.exists(os.path.join(dest_dir, candidate)):
        candidate = f"{base_name}_{n:02d}.{ext}"
        n += 1
    return candidate


def move_case(row_id, target_client_id):
    """"نقل الحالة": يقرأ صف row_id، يحسب المجلد الهدف، ينقل الملفين
    فعلياً (move)، يحدّث file_path/pdf_path/client_id بنفس السطر. يرجّع
    (new_file_path, new_pdf_path)."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM cd_documents WHERE id=?", (row_id,)).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"cd_documents row {row_id} غير موجود")
    row = dict(row)

    dest_dir = _target_dir_for(target_client_id, row.get("doc_date"), row.get("created_at"))
    os.makedirs(dest_dir, exist_ok=True)

    new_paths = {}
    for key, path_field in (("file_path", "file_path"), ("pdf_path", "pdf_path")):
        old_path = row.get(path_field)
        if not old_path or not os.path.exists(old_path):
            new_paths[path_field] = old_path
            continue
        base_name = os.path.splitext(os.path.basename(old_path))[0]
        ext = os.path.splitext(old_path)[1].lstrip(".")
        # بنفس مكانه أصلاً؟ ما فيه شي نسويه (نفس منطق _move_path الحالي
        # بالشريط لحالة "أفلت بنفس مكانه").
        if os.path.abspath(os.path.dirname(old_path)) == os.path.abspath(dest_dir):
            new_paths[path_field] = old_path
            continue
        new_name = _resolve_collision(dest_dir, base_name, ext)
        new_path = os.path.join(dest_dir, new_name)
        shutil.move(old_path, new_path)
        new_paths[path_field] = new_path

    conn.execute(
        "UPDATE cd_documents SET file_path=?, pdf_path=?, client_id=? WHERE id=?",
        (new_paths.get("file_path"), new_paths.get("pdf_path"), target_client_id, row_id),
    )
    conn.commit()
    conn.close()
    return new_paths.get("file_path"), new_paths.get("pdf_path")


_INVALID_NAME_CHARS = '\\/:*?"<>|'


def rename_case(row_id, new_base_name):
    """إعادة تسمية كوحدة: الملفين (docx+pdf) ياخذوا new_base_name نفسه
    (بلا امتداد)، بنفس المجلد الحالي، بنفس لحظة. new_base_name **بلا**
    بادئة CD_ (الاستدعاء يلصقها هو، راجع مرحلة 6 — البادئة محمية دائماً
    خارج خانة الكتابة). يرفع ValueError لاسم غير صالح أو متصادم."""
    if not new_base_name or any(c in new_base_name for c in _INVALID_NAME_CHARS):
        raise ValueError("اسم غير صالح")

    conn = get_connection()
    row = conn.execute("SELECT * FROM cd_documents WHERE id=?", (row_id,)).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"cd_documents row {row_id} غير موجود")
    row = dict(row)

    new_paths = {}
    for path_field in ("file_path", "pdf_path"):
        old_path = row.get(path_field)
        if not old_path:
            new_paths[path_field] = None
            continue
        folder = os.path.dirname(old_path)
        ext = os.path.splitext(old_path)[1]
        candidate = os.path.join(folder, f"{new_base_name}{ext}")
        if os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(old_path):
            conn.close()
            raise ValueError("فيه ملف بنفس الاسم أصلاً بهذا المجلد")
        new_paths[path_field] = candidate

    for path_field in ("file_path", "pdf_path"):
        old_path = row.get(path_field)
        new_path = new_paths[path_field]
        if old_path and new_path and old_path != new_path and os.path.exists(old_path):
            os.rename(old_path, new_path)

    conn.execute(
        "UPDATE cd_documents SET file_path=?, pdf_path=? WHERE id=?",
        (new_paths.get("file_path"), new_paths.get("pdf_path"), row_id),
    )
    conn.commit()
    conn.close()
    return new_paths.get("file_path"), new_paths.get("pdf_path")
```

جرّب يدوياً: زبون جديد، أول حفظ بلا زبون (يروح Autre/الشهر الصحيح حسب
doc_date لا تاريخ اليوم)، `move_case` لزبون، `move_case(row_id, None)`
(فك ربط، يرجع Autre)، `rename_case` بتصادم اسم متعمَّد (يرفع الخطأ صح).

---

## مرحلة 4 — استمارة CD: خانة الزبون + الحفظ الفوري

### 4.1 مكوّن اختيار مشترك جديد (`ui/common/client_picker.py`)
ودجت واحد (`ClientPickerEntry` أو مشابه) يُستخدم بمكانين (استمارة CD،
ونافذة السجل لكل من الفلتر وزر الربط) — بلا تكرار بناءه:

- خانة بحث بالاسم (`ttk.Entry` + قائمة نتائج منسدلة حية، `list_clients`
  كل `<KeyRelease>`، Debounce بسيط زي `_on_search_change` بالشريط
  الجانبي مو ضروري لعدد الزبائن المتوقَّع).
- زر "+ زبون جديد" يفتح `simpledialog`-مثل صغير (اسم إجباري، باقي
  الحقول اختيارية) → `create_client` → يختاره تلقائياً.
- خاصية `get_client_id()` (None لو ما فيه اختيار) و`set_client_id(id_or_none)`
  (لتحميل حالة محفوظة).
- **بلا أي اعتماد على tab.py** — عام تماماً، نفس فلسفة `FileExplorerPanel`.

### 4.2 خانة بالاستمارة (`ui/cd/tab.py`)
أضف `ClientPickerEntry` بمكانها المناسب بالاستمارة (بيانات المعاملة، لا
حقول المكتب — راجع البند 4-أ بمستند التصميم). أضف `client_id` لـ
`collect_data()` (من `self.client_picker.get_client_id()`). حمّلها
بـ`_apply_state_to_widgets`/`_load_data_into_form` (فتح حالة من السجل —
`data.get("client_id")`)، وامسحها بـ`new_document()`/`_new_tab_state`
(تبويب جديد فاضٍ).

### 4.3 الحفظ الفوري (`_do_generate` بـ`tab.py`)
حالياً (`ui/cd/document.py:_month_output_path`) الحفظ التلقائي (`dest_dir
is None`, `old_docx` فاضي) يستخدم `_month_output_path(passager, ext)`
دايماً. عدّلها:

- لو `data.get("client_id")` معطى **و** هذا أول حفظ لهذا التبويب
  (`old_docx` فاضي): استخدم `move_case`-نمط مباشرة — احسب `get_client_dir`
  للزبون، ابنِ الاسم فيه مباشرة (بلا مرور بـAutre أصلاً — راجع "الحفظ
  الفوري" بالبند 2).
- غير هيك: `_month_output_path` **لازم تتغيّر** لتاخذ `doc_date` كباراميتر
  وتبني المسار من `get_autre_dir()/<شهر doc_date>` بدل `OUTPUT_DIR/<شهر
  اليوم>` (راجع تنبيه ⚠️ بمرحلة 5 تحت — `OUTPUT_DIR` يبقى للكاش بس).
- أضف `client_id` لـ`record` (تمريره لـ`log_cd_document`/`update_cd_document`،
  راجع 1.3).

⚠️ **قرار تنفيذي**: لو زبون التبويب **تغيّر** (بدّل اختياره بخانة
الاستمارة) بعد أول حفظ ناجح لنفس التبويب (`loaded_from` معبّى)، حفظة
لاحقة تحدّث فوق نفس السطر — استخدم `move_case(row_id, new_client_id)`
صراحة بـ`_do_generate` (لو `data["client_id"] != old client_id المخزَّن`)
بدل حساب مسار من الصفر، حتى الملفات تنتقل فعلياً بدل ما تتكرر بمكان
جديد. قارن بـ`row.get("client_id")` (اقرأه من DB قبل التحديث، أو خزّنه
بـ`loaded_from` وقت التحميل الأول).

---

## مرحلة 5 — `ui/cd/document.py`: فصل الكاش عن مكان الحفظ الافتراضي

⚠️ **هذا التصحيح الأهم تقنياً بكل الخطة — لا تفوّته.**

`OUTPUT_DIR = get_screen_dir("CD")` مستخدَم اليوم بثلاث أغراض مختلفة:
مكان الحفظ الافتراضي (`_month_output_path`)، وملف كاش المعاينة
(`PREVIEW_PNG`)، وكاش صور الخلفية الفاضية (`get_blank_background`).
الأخيرين **داخليان تماماً** (المستخدم ما يشوفهم كـ"مستندات" — لو نقلناهم
لـ`Autre` يلوّثون مجلد شغل حقيقي بملفات PNG داخلية بلا معنى للمستخدم).

- **أبقِ `OUTPUT_DIR` كما هو** (`travail/CD`) — بس **حصراً** لـ
  `PREVIEW_PNG`/`get_blank_background`/`_blank_bg_*.png`. أضف تعليق واضح
  فوقها يوضح إنها "كاش داخلي بس، مو مكان حفظ مستندات — راجع
  docs/cd-clients-architecture.md بند 3".
- غيّر `_month_output_path(passager, ext)` → `_month_output_path(passager,
  ext, doc_date=None)`: تحسب المجلد من `get_autre_dir()` + شهر `doc_date`
  (أو `date.today()` لو `doc_date` فاضي — نادر، الحقل مو إجباري تماماً
  بالاستمارة). استورد `get_autre_dir` من `programme.paths` (بدل
  `get_screen_dir`).
- عدّل `generate_cd_document`/`generate_cd_pdf` (أو النداءات لهم بـ
  `tab.py`) لتمرير `data.get("date")` لـ`_month_output_path` — راجع
  مرحلة 4.3.
- بما إن `travail/CD` صار بلا أي محتوى يشوفه الشريط الجانبي (كاش بس)،
  **ما راح يبان أصلاً بالشجرة الجديدة** (مبنية من DB، بند 1) — سلوك
  صحيح ومقصود، بلا حاجة لأي إخفاء إضافي.

---

## مرحلة 6 — الشريط الجانبي: التحويل لمصدره DB (`ui/common/file_explorer.py`)

أكبر مرحلة تقنياً. المبدأ: كل عملية بناء/تحديث شجرة تعتمد على
`list_cd_documents_for_tree()` (مرحلة 1.5) بدل `os.listdir`/`os.walk`،
وكل عقدة ملف بالشجرة تحمل `row_id` (لا مسار بس) — راجع `self._paths`
الحالية، تصير عملياً `self._rows: {iid: {"row_id", "file_path",
"pdf_path", "client_id", ...}}`.

### 6.1 بناء الشجرة (`_populate_root`/`_expand_node`/`_list_dir_sorted`)
استبدلهم بمنطق يبني هيكل شجري بالذاكرة من نتيجة
`list_cd_documents_for_tree()`:
- المستوى الجذر: كل `client_id` مختلف موجود بالنتيجة (بترتيب أبجدي
  بالاسم) + عقدة "Autre" (لو فيه صفوف `client_id IS NULL`) — كل وحدة
  **بس لو عندها ≥ صف واحد** (⚠️ قرار تنفيذي: زبون بلا أي مستند لسا ما
  يبان بالشريط إطلاقاً، بما إن الشجرة انعكاس لـ"شنو موجود فعلياً" —
  يتوافق مع البند 1 بمستند التصميم).
- جوّا مجلد زبون: قائمة مسطّحة من صفوفه (بند 3: بلا تقسيم شهور).
- جوّا Autre: مجلدات فرعية بالشهر (`doc_date[:7]` أو `created_at[:7]`
  لو `doc_date` فاضي — نفس منطق `_target_dir_for`)، وجوّا كل شهر صفوفه.
- كل عقدة ملف (leaf) تبني اسمها المعروض من `os.path.basename(pdf_path
  or file_path)` — **مو من مسح قرص** (الملف قد يكون انمسح فيزيائياً
  بالغلط برّه البرنامج؛ لو كذا، اعرضه بردو لكن علّمه بصرياً — زي أيقونة
  ⚠️ صغيرة — بدل ما يختفي بصمت. `_open_file`/`📂 فتح` عليه يفشل برسالة
  خطأ عادية زي اليوم).

### 6.2 تمرير `row_id` عبر الـcallbacks
غيّر توقيع `is_path_active`/`on_open_file`/`on_toggle_lock` بـ
`FileExplorerPanel.__init__` من `(path) -> ...` لـ `(row_id, path) -> ...`
(أبسط وأسرع من إعادة البحث بـpath بكل استدعاء — الشجرة أصلاً بنتها من
DB وعندها row_id جاهز). حدّث المستدعين الثلاثة بـ`ui/cd/tab.py`:

- `_is_case_path_active(row_id, path)`: بدل حلقة `_norm_path` مقارنة
  بالمسارات، قارن `tab.get("loaded_from", {}).get("row_id") == row_id`
  مباشرة عبر `self._tabs` — أبسط وأدق (يزيل الحاجة لـ`_norm_path` هون
  كلياً).
- `_open_case_readonly(row_id, path)`: بدل `find_cd_document_by_path`
  (ممكن تُحذف من `database.py` بعد هالتغيير لو ما بقي أي مستدعٍ لها —
  تحقق بـ`grep` قبل الحذف)، اقرأ الصف مباشرة (`get_connection` + `SELECT
  * FROM cd_documents WHERE id=?`، أو دالة `get_cd_document(row_id)`
  جديدة بـ`database.py` — أنظف من استيراد `get_connection` مباشرة
  بـ`tab.py`).
- `_toggle_lock_for_path(row_id, path)`: نفس التحويل، قارن `row_id` بدل
  المسار بحلقة `self._tabs`.

### 6.3 إعادة التسمية (`_apply_rename`/`_begin_inline_rename`)
- خانة التعديل المباشر تعرض/تعدّل **الاسم بدون بادئة `CD_`** (استخرجها
  قبل عرض الخانة، ألصقها تلقائياً عند الحفظ) — ميزة جديدة، مو موجودة
  اليوم (اليوم الاسم كامل قابل للتعديل بلا حماية).
- عند التأكيد (`_commit_inline_rename`): نادِ `case_ops.rename_case(row_id,
  new_name)` بدل `os.rename()` مباشر. أظهر خطأ `alerts.error` لو رفعت
  `ValueError`. `refresh()` بعدها (زي اليوم).
- امنع إعادة التسمية كلياً لعقد المجلدات (زبون/Autre/شهر) — مو ملفات
  حالات — `_rename_selected`/`_begin_inline_rename` يتجاهلوها بصمت (زي
  التعامل الحالي مع `path == self.root_dir`).

### 6.4 السحب والإفلات (`_on_drag_release`/`_move_path`)
استبدل `_move_path` بمنطق القرار (بند 4-د بمستند التصميم):
- الهدف عقدة زبون → `case_ops.move_case(row_id, target_client_id)`.
- الهدف عقدة Autre (أو أي عقدة شهر جوّاها) → `case_ops.move_case(row_id,
  None)`.
- أي هدف ثاني (بما فيه ملف ثاني، أو نفس مكانه) → لا شي (زي اليوم).
- بعد نجاح النقل: `refresh()` + `reveal_path`/`reveal_row` (راجع 6.6).
- امنع سحب عقدة مجلد (زبون/Autre) نفسها بالكامل — بس ملفات الحالات
  قابلة للسحب.

### 6.5 القفل الصارم (حاجز، لا تأكيد)
بـ`_apply_rename`/`_move_path` (الجديدين، 6.3/6.4) وبـ
`_maybe_schedule_rename`/`_on_drag_start`: افحص `is_path_active(row_id,
path)` **قبل** أي محاولة، وارفض بصمت (أو `alerts.info("مقفول", "افتح
القفل أولاً (🔓 فتح للتعديل) قبل التعديل.")`) لو `False` — احذف استدعاءات
`confirm_always("إعادة تسمية شغل منتهي"...)`/`confirm_always("نقل شغل
منتهي"...)` الحاليتين (يصيران غير ضروريتين، الحاجز يمنع قبل ما توصل
لهنا أصلاً).

### 6.6 حذف، بحث، قفزة للشهر، الأخيرة
- `_delete_selected`: **عطّلها لعقد الملفات كلياً** (بند 4-ز — مؤجَّل).
  اترك "🗑️ حذف" برّه قائمة كليك يمين تماماً لهذا الإصدار (لا للملفات ولا
  للمجلدات).
- `_new_folder`/"📁+ مجلد جديد": احذفها من `_show_context_menu` كلياً
  (بند 4-ح).
- `_on_search_change`: استبدل `os.walk` بفلترة `list_cd_documents_for_tree()`
  محلياً بذاكرة (بحث بـ`dossier_no`/`passager`/`passport_no`/`client_name`،
  حالة أحرف غير حساسة) — أو استخدم `search_cd_documents(query)` مباشرة
  (أبسط، بما إنها صارت تدعم `client_name` بمرحلة 1.4).
- `_jump_to_current_month`: ابحث عن عقدة الشهر الحالي **جوّا Autre بس**
  (لا `os.walk` بكل الجذر).
- `record_recent`/`_refresh_recent_list`: خزّن `row_id` مع المسار
  (`{"row_id": ..., "path": ...}` بدل نص مسار خام)، وقت الفتح من القائمة
  اقرأ المسار **الحالي** من DB (`get_cd_document(row_id)`) بدل النص
  المخزَّن القديم — يحمي من مسارات قديمة بعد أي نقل/إعادة تسمية.

### 6.7 التبني بـ`tab.py`
`self.explorer_panel = FileExplorerPanel(...)` بـ`_build_canvas_area`:
حدّث تمرير `is_path_active`/`on_open_file`/`on_toggle_lock` للتواقيع
الجديدة (row_id-based). `_do_generate` بنهايته (`self.explorer_panel.reveal_path(...)`)
والدوال المشابهة (`_sync_explorer_to_active_tab`, `history.py:_reveal_in_sidebar`)
تحتاج تتحول لـ`reveal_row(row_id)` جديدة بـ`FileExplorerPanel` (تلقى
المسار الحالي من `row_id` مباشرة بدل الاعتماد على مسار مخزَّن مسبقاً قد
يكون تغيّر).

---

## مرحلة 7 — السجل (`ui/cd/history.py`)

- عمود جديد "الزبون" بـ`columns`/`headers`/`self.tree.insert(...)` —
  مصدره `row.get("client_name") or "—"` (من `search_cd_documents` بعد
  مرحلة 1.4).
- فوق شريط البحث: `ClientPickerEntry` (مرحلة 4.1) كفلتر — تغييره يعيد
  `_refresh()` بتمرير `client_id` لـ`search_cd_documents`.
- زر/عنصر قائمة كليك يمين جديد: "🔗 اربط بزبون" (لو `client_id` فاضي)
  أو "↔️ غيّر الزبون" + "🔓 فك الربط" (لو معبّى) — "اربط"/"غيّر" يفتح
  `ClientPickerEntry` بنافذة صغيرة (`simpledialog`-مثل)، وينادي
  `case_ops.move_case(row["id"], client_id)` ثم `self._refresh()`. "فك
  ربط" ينادي `case_ops.move_case(row["id"], None)` مباشرة (بتأكيد بسيط
  `_confirm`).
- (اختياري، أولوية أقل): كليك على رأس عمود "الزبون" يفرز الصفوف محلياً
  بالذاكرة (`self._rows.sort(key=...)` ثم إعادة بناء `self.tree`) — لو
  الوقت يسمح؛ الفلترة (فوق) هي الأساسية.
- نافذة صغيرة جديدة "👥 إدارة الزبائن" (زر بالشريط السفلي أو قائمة كليك
  يمين) — قائمة بسيطة (`list_clients` بلا query) + زر حذف لكل صف يستدعي
  `delete_client` (رسالة واضحة لو رفضته `client_has_documents`، تأكيد
  عادي لو نجح). ⚠️ قرار تنفيذي: خليها بسيطة (قائمة + حذف بس، بلا تعديل
  بيانات الزبون بهذا الإصدار) — كافية لسد بند 4-و بمستند التصميم بلا
  استثمار وقت زايد بواجهة كاملة.

---

## ترتيب موصى به للتنفيذ والتحقق

1. مرحلة 1+2 (DB + مسارات) — تحقق: `python -c "from programme.database
   import init_db; init_db()"` يشتغل بلا خطأ على قاعدة بيانات موجودة
   أصلاً بالمشروع (ترقية، لا إعادة إنشاء).
2. مرحلة 3 (`case_ops.py`) — تحقق بسكربت يدوي صغير (زبون تجريبي، صف CD
   تجريبي، `move_case`/`rename_case`) قبل أي ربط بالواجهة.
3. مرحلة 5 (فصل الكاش) — تحقق: توليد مستند جديد بلا زبون يروح فعلاً
   لـ`travail/Autre/<شهر doc_date>` لا `travail/CD/<شهر اليوم>`، وملفات
   الكاش (`_preview.png`, `_blank_bg_*.png`) تبقى تتولّد طبيعي بـ
   `travail/CD`.
4. مرحلة 4 (الاستمارة) — تحقق: زبون جديد من الاستمارة، حفظ فوري يروح
   مباشرة لمجلده، تغيير الزبون بحفظة لاحقة ينقل الملفات فعلاً.
5. مرحلة 6 (الشريط) — أكبر مرحلة، جرّبها بعناية: تصفّح شجرة زبائن/Autre،
   فتح ملف، سحب-وإفلات (كل الحالات: على زبون، على Autre، على مكان
   مرفوض)، إعادة تسمية (بادئة محمية)، قفل صارم (جرّب تعديل ملف مقفول —
   يُرفض بلا تأكيد قابل للتجاوز)، بحث، الأخيرة.
6. مرحلة 7 (السجل) — عمود الزبون، الفلترة، أزرار الربط/فك الربط، إدارة
   الزبائن (حذف مباشر يُرفض، حذف زبون فاضٍ ينجح).

بعد كل مرحلة: كوميت بترقيم "مرجع" التالي (تحقق برقم آخر مرجع بـ`git log
--oneline -1`) + سطر بـ`docs/CHANGELOG.md`.

---

## مرحلة 8 (تكميلية — بعد المراجعة الأولى للمراحل 1-7)

هذي 3 إصلاحات منفصلة منطقياً عن بعض (رتّبهم كوميتات مستقلة، أي ترتيب
بينهم مقبول). تحقق برقم آخر "مرجع" مستخدَم فعلياً بـ`git log` قبل ما
تبدأ (المفروض بعد مراجع 15-21 من المراحل 1-7).

### 8.1 اسم الملف: `CD_<رقم البوردرو>` بدل `CD_<الراكب>_<الوقت>`

`ui/cd/document.py:_named_path(dir_path, passager, ext)` → غيّرها لـ
`_named_path(dir_path, dossier_no, ext)`:

- الاسم الأساسي يصير `CD_<رقم البوردرو>` (نفس أسلوب التنظيف الحالي —
  أحرف/أرقام/مسافة/شرطة بس، بديل زي `sans_no` لو فاضي تماماً).
- ⚠️ **مهم**: شيل الاعتماد على `datetime.now()` بالاسم كان يمنع أي
  تصادم عملياً (كل ملف يحمل توقيت مختلف). بدونها، **لازم** فحص تصادم
  فعلي (`_02`, `_03`...) بنفس مجلد الهدف — بالضبط زي الموصوف بالبند 3
  بمستند التصميم. أضف هالفحص لـ`_named_path` نفسها، أو انقل
  `_resolve_collision` من `programme/case_ops.py` لمكان مشترك يقدر
  `document.py` يستورده منه — بلا تكرار نفس منطق التصادم بمكانين.
- ⚠️ **حرج أكثر**: docx وpdf لازم ياخذوا **نفس الاسم الأساسي بالضبط**
  (يختلفوا بالامتداد بس — مبدأ صريح بالبند 3). حالياً `_month_output_path`/
  `_named_path` تُستدعى **منفصلة** لكل امتداد (مرة docx ومرة pdf) — لو
  فحص التصادم يشتغل لكل استدعاء لحاله، ممكن docx تاخذ `_02` وpdf تضل
  بلا لاحقة (أو العكس). **الحل**: احسب الاسم الأساسي النهائي (بعد فحص
  التصادم) **مرة وحدة** لكل حالة، ثم ابنِ مساري docx/pdf من نفس الاسم —
  لا نداءين منفصلين لكل واحد لحاله. راجع كل نداءات `_named_path`/
  `_month_output_path` بـ`document.py` (`generate_cd_document`،
  `generate_cd_pdf`) وبـ`tab.py` (`_do_generate`، `_save_to_other_location`).
- تحقق يدوياً: ولّد مستندين بنفس رقم البوردرو بنفس المجلد (نفس الزبون
  مثلاً) — الثاني لازم ياخذ `_02` بالاسمين (docx وpdf) مع بعض، لا بواحد بس.

### 8.2 إصلاح `new_document()` — فك الربط الفعلي بحالة قديمة

`ui/cd/tab.py:new_document()`: أضف `tab["loaded_from"] = None` (بعد
تصفير `saved_snapshot`) — بدونها، حفظ لاحق بنفس التبويب يحدّث فوق سطر/
ملفات حالة قديمة كان محمَّلاً منها (فتحتها من السجل)، بدل ما يسجّل حالة
جديدة مستقلة. نادِ `self.explorer_panel.refresh()` بنهايتها بردو (نفس
نمط `_close_tab` — حالة القفل بالشريط لأي ملف كانت "محمَّلة" بهالتبويب
لازم تتحدّث بصرياً فوراً). لو حقل الزبون (`ClientPickerEntry`) مو ضمن
مجموعة الحقول الممسوحة تلقائياً بأول حلقة بالدالة، امسحه صراحة هنا كمان
(تبويب فاضٍ جديد يبلش بلا زبون، بلا وراثة اختيار الحالة القديمة).

### 8.3 قائمة "↕️ ترتيب حسب" بالشريط الجانبي

راجع البند 6 بـ`docs/cd-clients-architecture.md` — لسا ما اتنفّذت.
بـ`ui/common/file_explorer.py`:

- عنصر جديد بقائمة كليك يمين (`_show_context_menu`): "↕️ ترتيب حسب" ←
  قائمة فرعية (`tk.Menu`) بثلاث خيارات راديو: 🔤 الاسم / 🕐 تاريخ الإنشاء /
  🕑 آخر تعديل — علامة راديو تبيّن الاختيار الحالي.
- يُحفظ الاختيار بـ`file_explorer_prefs.json` (نفس `PREFS_PATH`
  الموجود، مفتاح جديد زي `"sort_by"`).
- يطبَّق على **ترتيب ملفات الحالات (leaves) جوّا كل مجلد** (مجلد زبون،
  أو مجلد شهر جوّا Autre) — **لا** على ترتيب مجلدات الزبائن/Autre
  بالمستوى الجذري (هذي تبقى أبجدية دائماً، ثابتة، بلا تأثّر بهالتفضيل —
  "المجلدات دايماً فوق الملفات" بالبند 6). "الاسم" هون يعني اسم الملف
  المعروض (`CD_<رقم البوردرو>` بعد إصلاح 8.1)، "الإنشاء"/"آخر تعديل" من
  `cd_documents.created_at`/`updated_at` (لا وقت الملف الفيزيائي — متوفرين
  أصلاً بنتيجة `list_cd_documents_for_tree()` من مرحلة 1.5).
- يطبَّق بردو على نتائج البحث — نفس التفضيل المحفوظ، لا ترتيب منفصل للبحث.
