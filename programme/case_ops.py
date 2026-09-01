"""عملية "نقل الحالة" الموحّدة — قلب البند 2 بمستند التصميم
(docs/cd-clients-architecture.md).

بدل التفكير بـ"حفظ" و"ربط بزبون" و"فك ربط" و"تصحيح زبون" و"سحب/إفلات
بالشريط" كعمليات منفصلة، كلهم **نفس العملية بالضبط**: خذ row_id، احسب
المجلد الهدف، انقل الملفين فعلياً (move لا copy)، حدّث file_path/pdf_path/
client_id بنفس السطر.

- move_case: نقل حالة لمجلد زبون (client_id معطى) أو لـAutre/<الشهر>
  (client_id = None). يُستخدم من: أول حفظ بزبون معروف، ربط/تغيير/فك ربط
  من السجل، سحب-وإفلات بالشريط الجانبي — **دالة واحدة تُستخدم من كل
  مكان**، لا تكرار منطق النقل بأي مكان ثاني.
- rename_case: إعادة تسمية الحالة كوحدة — الملفين (docx+pdf) ياخذوا نفس
  الاسم الجديد بنفس اللحظة، بنفس المجلد الحالي.

**تفصيل حرج**: حساب "الشهر" عند أي حساب مسار يعتمد دائماً على تاريخ
المعاملة نفسها (doc_date)، لا datetime.now() — وإلا حالة قديمة مؤرَّخة
بالماضي تترتب زمنياً غلط. لو doc_date فاضي (نادر)، نرجع لـcreated_at
كبديل، لا وقت العملية.
"""
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


def resolve_case_base(dest_dir, base):
    """أصغر لاحقة (_02، _03...) تخلي **الاثنين** `<base>.docx` و`<base>.pdf`
    فاضيين بـdest_dir — فحص مزدوج مرة وحدة للحالة كلها، فـdocx وpdf
    ياخذان نفس اللاحقة أو ولا وحدة (أبداً واحد بلاحقة والثاني بدونها —
    مبدأ صريح بالبند 3 بمستند التصميم). `base` بلا امتداد. الفحص محصور
    بـdest_dir بس (نفس رقم البوردرو بمجلدين مختلفين لا يتصادم).

    مصدر واحد لمنطق التصادم يستورده كل من هذا الملف (move_case) و
    ui/cd/document.py (توليد ملف جديد) — بلا تكرار."""
    name = base
    n = 2
    while (
        os.path.exists(os.path.join(dest_dir, name + ".docx"))
        or os.path.exists(os.path.join(dest_dir, name + ".pdf"))
    ):
        name = f"{base}_{n:02d}"
        n += 1
    return name


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

    # الاسم الأساسي النهائي (بعد فحص التصادم) يُحسب **مرة وحدة للحالة**
    # ثم يُطبَّق على docx وpdf معاً — فياخذان نفس اللاحقة أو ولا وحدة.
    # (نفترض docx وpdf متجاورين بنفس المجلد بنفس الجذر، وهو الحال دائماً.)
    src_present = [p for p in (row.get("file_path"), row.get("pdf_path")) if p and os.path.exists(p)]
    needs_move = any(
        os.path.abspath(os.path.dirname(p)) != os.path.abspath(dest_dir) for p in src_present
    )
    resolved_base = None
    if needs_move and src_present:
        cur_base = os.path.splitext(os.path.basename(src_present[0]))[0]
        resolved_base = resolve_case_base(dest_dir, cur_base)

    new_paths = {}
    for path_field in ("file_path", "pdf_path"):
        old_path = row.get(path_field)
        if not old_path or not os.path.exists(old_path):
            new_paths[path_field] = old_path
            continue
        # بنفس مكانه أصلاً؟ ما فيه شي نسويه (نفس منطق _move_path الحالي
        # بالشريط لحالة "أفلت بنفس مكانه").
        if os.path.abspath(os.path.dirname(old_path)) == os.path.abspath(dest_dir):
            new_paths[path_field] = old_path
            continue
        ext = os.path.splitext(old_path)[1]  # يشمل النقطة
        new_path = os.path.join(dest_dir, resolved_base + ext)
        shutil.move(old_path, new_path)
        new_paths[path_field] = new_path

    # نحدّث updated_at بردو: نقل الحالة تعديل حقيقي عليها، ومستند
    # التصميم (بند 6) يبي updated_at يعكس "آخر تعديل" لترتيب الشريط.
    conn.execute(
        "UPDATE cd_documents SET file_path=?, pdf_path=?, client_id=?, "
        "updated_at=datetime('now','localtime') WHERE id=?",
        (new_paths.get("file_path"), new_paths.get("pdf_path"), target_client_id, row_id),
    )
    conn.commit()
    conn.close()
    return new_paths.get("file_path"), new_paths.get("pdf_path")


_INVALID_NAME_CHARS = '\\/:*?"<>|'


def rename_case(row_id, new_base_name):
    """إعادة تسمية كوحدة: الملفين (docx+pdf) ياخذوا new_base_name نفسه
    (بلا امتداد)، بنفس المجلد الحالي، بنفس لحظة. new_base_name **بلا**
    بادئة CD_ (الاستدعاء يلصقها هو — البادئة محمية دائماً خارج خانة
    الكتابة). يرفع ValueError لاسم غير صالح أو متصادم."""
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
        # الملف مو موجود فعلياً على القرص (نُقل/انمسح برّة البرنامج —
        # الصف يبان بعلامة ⚠️ بالشريط) → ما نحسبله اسم جديد ولا نلمس
        # عموده بقاعدة البيانات إطلاقاً، يضل زي ما هو (بالضبط نفس منطق
        # move_case فوق). لو حسبناله مساراً جديداً هون بلا فحص وجوده،
        # كنا نكتب بالقاعدة مساراً "وهمي" ما انخلق فعلياً — وأخطر من
        # هيك: لو الملف الثاني (docx أو pdf) موجود فعلاً وانسمّى، هذا
        # المفقود يضل مرتبط باسمه القديم بالقرص لكن القاعدة تفقد مساره
        # الحقيقي نهائياً لو حسبناه هون.
        if not os.path.exists(old_path):
            new_paths[path_field] = old_path
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
        "UPDATE cd_documents SET file_path=?, pdf_path=?, "
        "updated_at=datetime('now','localtime') WHERE id=?",
        (new_paths.get("file_path"), new_paths.get("pdf_path"), row_id),
    )
    conn.commit()
    conn.close()
    return new_paths.get("file_path"), new_paths.get("pdf_path")
