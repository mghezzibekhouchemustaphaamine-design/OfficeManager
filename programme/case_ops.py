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
    for _key, path_field in (("file_path", "file_path"), ("pdf_path", "pdf_path")):
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
