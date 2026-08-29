"""
النسخ الاحتياطي التلقائي/اليدوي لقاعدة البيانات (office_system.db) ومجلد
الشغل (travail) — نظام "3-2-1" الشهير بحماية البيانات (نسخة رئيسية +
نسخة ثانية بوسيط تخزين مختلف + نسخة ثالثة خارج الجهاز)، بطلب صريح:

- **الرئيسية**: مكان الشغل الحالي (office_system.db بجانب البرنامج،
  travail بسطح المكتب — راجع paths.py) — بلا أي تغيير، هذا الملف ما
  يلمسها إطلاقاً، بس يقرأ منها لينسخ.
- **"ثانوية" (role="secondary")**: قرص أو فلاشة مختلفة **فعلياً** عن
  قرص الرئيسية — نتحقق من حرف القرص وقت الإعداد ونرفض لو نفس القرص
  (وإلا عطل قرص وحيد يمسح الرئيسية والثانوية معاً، بلا أي فائدة حقيقية
  من وجود "نسخة ثانية"). تحمي من عطل القرص الأساسي بالكامل.
- **"سحابة" (role="cloud")**: أي مجلد يتزامن أوتوماتيكياً لخدمة سحابة
  (OneDrive افتراضياً لو مكتشَف على الجهاز، أو أي مجلد مزامنة آخر
  يختاره المستخدم يدوياً — Google Drive، Dropbox...). بلا حاجة لربط
  حساب فعلي من جهتنا: نكتب لمجلد عادي بس، وخدمة المزامنة المثبَّتة على
  الجهاز تتكفّل بالرفع بالخلفية بلا أي تدخّل إضافي منّا. بلا قيد على
  القرص (عادة نفس قرص الرئيسية أصلاً — الحماية هون مصدرها الرفع
  للإنترنت لا موقع القرص محلياً).

كل وجهة (ثانوية أو سحابة) تاخذ نسختين معاً بكل تشغيل:
  1. **مرآة حية**: نسخة تطابق الرئيسية بالضبط بالاسم والهيكل
     (office_system.db بنفس الاسم، ومجلد travail بكامل محتواه) — سهلة
     التصفح، تبين بالضبط زي الأصل (بطلب صريح، تجنّباً لأي لخبطة). مرآة
     "تراكمية" فقط (تنسخ كل جديد/متغيّر) — ما تحذف من الوجهة أي ملف
     زال من الرئيسية، حتى ما يصير خلل بالمصدر (حذف بالغلط، فيروس...)
     سبب لمسح النسخة الاحتياطية السليمة كمان.
  2. **نسخ قاعدة البيانات بتواريخ** محفوظة بمجلد فرعي (_snapshots)، آخر
     RETENTION_DAYS يوم — تحمي من حالة "تلف بالبيانات نفسها وهي حية"
     (فيروس فدية، خطأ برمجي يكتب بيانات غلط...) قبل ما ننتبه، شي ما
     توفّره المرآة الخالصة لحالها (لأنها كانت رح تنسخ النسخة التالفة
     فوق السليمة). لا نحتفظ بتاريخ لمجلد travail نفسه (حجمه أكبر بكثير
     من قاعدة بيانات وحيدة، ومستنداته أصلاً قابلة لإعادة التوليد من
     قاعدة البيانات — راجع full_data_json بـcd_documents).

كل وجهة غير متاحة وقت النسخ (فلاشة مو موصولة، OneDrive مو مركّب...)
تُتجاوز بصمت (بلا خطأ يوقف الباقي)، ويُبلَّغ عنه بس بالتشغيل اليدوي.

نستخدم Connection.backup() الرسمية من sqlite3 (مو نسخ ملف خام) — تتعامل
صح مع قاعدة مفتوحة/قيد الاستخدام وقت النسخ، بعكس نسخ الملف مباشرة اللي
ممكن يلتقط حالة نص مكتوبة (تلف الملف الناسخ).
"""
import json
import os
import shutil
import sqlite3
import threading
from datetime import date, datetime

from programme.database import DB_PATH
from programme.paths import get_travail_root

# ملف الإعدادات الحقيقي يبقى بجذر المشروع (بلا أي تغيير بمكانه رغم نقل
# هذا الملف نفسه لمجلد programme/) — لازم مستوى إضافي (dirname مرتين).
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# قابل للتجاوز عبر متغيّر بيئة (اختبارات آلية بس) — حتى ما تلمس ملف
# الإعدادات الحقيقي ولا وجهات النسخ الحقيقية المُعدّة فعلياً على الجهاز.
BACKUP_SETTINGS_PATH = os.environ.get("OFFICEMANAGER_BACKUP_SETTINGS_PATH") or os.path.join(
    _APP_ROOT, "backup_settings.json"
)

# الوجهة الافتراضية المقترحة لدور "سحابة" بمعالج الإعداد الأول — نقترحها
# تلقائياً لو مكتشَفة (مجلد OneDrive موجود)، والمستخدم حر يغيّرها لأي
# مجلد مزامنة آخر (Google Drive، Dropbox...) يدوياً بنفس الحقل.
ONEDRIVE_SUGGESTED_PATH = os.path.join(os.path.expanduser("~"), "OneDrive")

# نحتفظ بنسخ قاعدة البيانات بتواريخ آخر شهر بس بكل وجهة (راجع الشرح
# بالأعلى) — قاعدة بياناتنا صغيرة، بس ولا داعي للتراكم الأبدي.
RETENTION_DAYS = 30

_SNAPSHOTS_SUBDIR = "_snapshots"
_TRAVAIL_MIRROR_SUBDIR = "travail"
_DB_FILENAME = "office_system.db"


def _load_settings():
    try:
        with open(BACKUP_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_settings(data):
    try:
        with open(BACKUP_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # حفظ ثانوي — فشل الكتابة ما يوقف النسخ نفسه


def get_destinations():
    """يرجّع قائمة الوجهات المُعدّة فعلياً (فاضية لو المستخدم ما أكمل
    الإعداد بعد) — كل وجهة {"label", "path", "role"}؛ role يكون
    "secondary" أو "cloud" (وجهة وحيدة بكل دور، راجع set_role_destination)
    أو "other" (عدة وجهات ممكنة، تُضاف يدوياً لاحقاً عبر add_destination
    — فلاشة إضافية مثلاً)."""
    settings = _load_settings()
    return settings.get("destinations", [])


def _primary_drives():
    """أحرف الأقراص اللي عليها بيانات الشغل الرئيسية الآن (قاعدة
    البيانات ومجلد travail) — أي وجهة "ثانوية" لازم تكون بقرص مختلف عن
    كل هذي، وإلا عطل قرص وحيد يقدر يمسح الرئيسية والثانوية معاً."""
    drives = set()
    for p in (DB_PATH, get_travail_root()):
        drive = os.path.splitdrive(os.path.abspath(p))[0].upper()
        if drive:
            drives.add(drive)
    return drives


def is_same_drive_as_primary(path):
    """True لو path بنفس قرص الرئيسية (أو بلا حرف قرص أصلاً — مسار
    شبكة UNC مثلاً، نعتبره "مختلف" بتفاؤل: مو نفس القرص المحلي على
    الأقل)."""
    drive = os.path.splitdrive(os.path.abspath(path))[0].upper()
    return bool(drive) and drive in _primary_drives()


def set_role_destination(role, label, path):
    """يعيّن (أو يستبدل) الوجهة الوحيدة بدور معيّن ("secondary" أو
    "cloud") — كل دور وجهة وحيدة بس (بعكس "other" اللي تدعم عدة وجهات
    عبر add_destination). يرفع ValueError لو role="secondary" وطلب نفس
    قرص الرئيسية (القيد الوحيد؛ "cloud" بلا أي قيد على القرص)."""
    if role not in ("secondary", "cloud"):
        raise ValueError(f"دور غير معروف: {role!r}")
    if role == "secondary" and is_same_drive_as_primary(path):
        raise ValueError(
            "لازم تختار قرص مختلف فعلياً عن قرص الشغل الرئيسي (فلاشة USB أو قرص ثاني)، "
            "وإلا عطل بهالقرص يمسح الرئيسية والنسخة الثانية معاً."
        )
    settings = _load_settings()
    destinations = [d for d in settings.get("destinations", []) if d.get("role") != role]
    destinations.append({"label": label, "path": path, "role": role})
    settings["destinations"] = destinations
    _save_settings(settings)


def get_role_destination(role):
    return next((d for d in get_destinations() if d.get("role") == role), None)


def resilience_setup_needed():
    """المعالج الأول (أول فتح للبرنامج) لازم يظهر لو ماكو وجهة "ثانوية"
    ولا "سحابة" معيّنة بعد — بلا أي حماية حقيقية خارج الرئيسية."""
    roles = {d.get("role") for d in get_destinations()}
    return not ({"secondary", "cloud"} <= roles)


def mark_resilience_setup_skipped():
    """المستخدم أجّل الإعداد (زر "لاحقاً" بالمعالج) — ما نزعجه كل فتح
    برنامج، بس يبقى يقدر يكمّله يدوياً من شاشة النسخ الاحتياطي أي وقت."""
    settings = _load_settings()
    settings["resilience_setup_skipped"] = True
    _save_settings(settings)


def resilience_setup_was_skipped():
    return bool(_load_settings().get("resilience_setup_skipped"))


def add_destination(label, path, role="other"):
    """يضيف وجهة نسخ إضافية (فلاشة ثانية مثلاً) — بلا أي تعديل كود،
    تشتغل فوراً بالمرة الجاية. يرجّع False لو موجودة أصلاً بنفس المسار."""
    settings = _load_settings()
    destinations = settings.get("destinations", [])
    if any(d["path"] == path for d in destinations):
        return False
    destinations.append({"label": label, "path": path, "role": role})
    settings["destinations"] = destinations
    _save_settings(settings)
    return True


def remove_destination(path):
    settings = _load_settings()
    destinations = settings.get("destinations", [])
    new_destinations = [d for d in destinations if d["path"] != path]
    settings["destinations"] = new_destinations
    _save_settings(settings)
    return len(new_destinations) != len(destinations)


def is_destination_reachable(path):
    """وجهة "متاحة الآن" لو مجلدها الأب موجود فعلياً — يميّز "OneDrive مو
    مركّب" أو "الفلاشة مو موصولة" (نتجاوزها بهدوء) عن مشكلة حقيقية، بدون
    محاولة إنشاء أي شي هنا (فحص بس)."""
    normalized = os.path.normpath(path)
    parent = os.path.dirname(normalized) or normalized
    return os.path.exists(parent) or os.path.exists(normalized)


def _backup_db_to(dest_dir):
    """ينسخ قاعدة البيانات لوجهة معيّنة: مرآة (اسم ثابت، تُستبدَل كل
    مرة) + نسخة بتاريخ بمجلد _snapshots (للرجوع لنقطة قبل أي تلف)."""
    os.makedirs(dest_dir, exist_ok=True)
    src_conn = sqlite3.connect(DB_PATH)
    try:
        mirror_path = os.path.join(dest_dir, _DB_FILENAME)
        mirror_conn = sqlite3.connect(mirror_path)
        try:
            src_conn.backup(mirror_conn)
        finally:
            mirror_conn.close()

        snapshots_dir = os.path.join(dest_dir, _SNAPSHOTS_SUBDIR)
        os.makedirs(snapshots_dir, exist_ok=True)
        snapshot_name = f"office_system_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        snapshot_conn = sqlite3.connect(os.path.join(snapshots_dir, snapshot_name))
        try:
            src_conn.backup(snapshot_conn)
        finally:
            snapshot_conn.close()
    finally:
        src_conn.close()
    _cleanup_old_snapshots(os.path.join(dest_dir, _SNAPSHOTS_SUBDIR))


def _cleanup_old_snapshots(snapshots_dir):
    """يمسح نسخ أقدم من RETENTION_DAYS بمجلد _snapshots."""
    cutoff = datetime.now().timestamp() - RETENTION_DAYS * 86400
    try:
        for name in os.listdir(snapshots_dir):
            if not (name.startswith("office_system_") and name.endswith(".db")):
                continue
            full = os.path.join(snapshots_dir, name)
            try:
                if os.path.getmtime(full) < cutoff:
                    os.remove(full)
            except OSError:
                pass
    except OSError:
        pass


def _mirror_travail_to(dest_dir):
    """يرآة مجلد travail الحقيقي لوجهة معيّنة: ينسخ كل ملف جديد أو
    اتغيّر (بالحجم أو تاريخ التعديل) — بلا حذف أي ملف موجود بالوجهة
    وزال من المصدر (مرآة "تراكمية" بس، راجع شرح الملف بالأعلى)."""
    src_root = get_travail_root()
    if not os.path.isdir(src_root):
        return  # ماكو شغل حقيقي بعد (تبويب أول فتح، ما تولّد أي مستند)
    dest_root = os.path.join(dest_dir, _TRAVAIL_MIRROR_SUBDIR)
    for dirpath, _dirnames, filenames in os.walk(src_root):
        rel = os.path.relpath(dirpath, src_root)
        dest_dirpath = os.path.join(dest_root, rel) if rel != "." else dest_root
        os.makedirs(dest_dirpath, exist_ok=True)
        for name in filenames:
            src_file = os.path.join(dirpath, name)
            dest_file = os.path.join(dest_dirpath, name)
            if _needs_copy(src_file, dest_file):
                try:
                    shutil.copy2(src_file, dest_file)
                except OSError:
                    pass  # ملف واحد فشل (مقفول من برنامج آخر مثلاً) ما يوقف الباقي


def _needs_copy(src_file, dest_file):
    if not os.path.exists(dest_file):
        return True
    try:
        src_stat, dest_stat = os.stat(src_file), os.stat(dest_file)
    except OSError:
        return True
    return src_stat.st_size != dest_stat.st_size or src_stat.st_mtime > dest_stat.st_mtime + 1


def run_backup():
    """ينسخ (مرآة + نسخة بتاريخ لقاعدة البيانات، ومرآة لـtravail) لكل
    وجهة متاحة الآن — يرجّع (نجحت: [تسميات], متجاوَزة/فشلت: [تسميات])."""
    destinations = get_destinations()
    if not destinations:
        return [], []  # ماكو وجهات معدَّة بعد — بلا أي أثر جانبي (ولا حتى كتابة ملف إعدادات)
    succeeded, skipped = [], []

    for dest in destinations:
        label, path = dest["label"], dest["path"]
        if not is_destination_reachable(path):
            skipped.append(label)
            continue
        try:
            _backup_db_to(path)
            _mirror_travail_to(path)
            succeeded.append(label)
        except (OSError, sqlite3.Error):
            skipped.append(label)

    settings = _load_settings()
    settings["last_backup_at"] = datetime.now().isoformat()
    settings["last_backup_succeeded"] = succeeded
    _save_settings(settings)
    return succeeded, skipped


def run_backup_async():
    """نفس run_backup() بس بخيط منفصل (daemon) — تُستدعى بعد كل حفظ
    مستند حقيقي (راجع ui/cd/tab.py)، حتى ما تعلّق الواجهة لو فلاشة بطيئة
    أو مجلد سحابة غير متاح لحظتها. sqlite3 آمنة هون: كل استدعاء يفتح
    اتصالاته الخاصة، بلا أي اتصال مشترك مع الخيط الرئيسي."""
    if not get_destinations():
        return  # ماكو وجهات معدَّة بعد — ما نحتاج نفتح خيط أصلاً
    threading.Thread(target=run_backup, daemon=True).start()


def maybe_run_daily_backup():
    """يُستدعى عند فتح البرنامج — ينسخ تلقائياً مرة وحدة بس باليوم (أول
    فتح لليوم)، بصمت (بلا أي نافذة) — لا نزعج المستخدم كل فتح، ولا نكرر
    النسخ لو فتح البرنامج عدة مرات بنفس اليوم. هذا "الشبكة الاحتياطية"
    اليومية بغض النظر عن النسخ الفورية بعد كل حفظ (run_backup_async)."""
    settings = _load_settings()
    today = date.today().isoformat()
    if settings.get("last_auto_backup_date") == today:
        return
    run_backup()
    settings = _load_settings()  # run_backup فوق حفظ last_backup_at/succeeded أصلاً
    settings["last_auto_backup_date"] = today
    _save_settings(settings)


def last_backup_info():
    settings = _load_settings()
    return settings.get("last_backup_at"), settings.get("last_backup_succeeded", [])


_ONEDRIVE_ACCOUNT_FOLDER = ONEDRIVE_SUGGESTED_PATH  # = %USERPROFILE%\OneDrive


def _read_onedrive_account_emails():
    """يرجّع قائمة بريد كل حساب OneDrive مربوط فعلاً بالتسجيل (فاضية لو
    ماكو ولا حساب، None لو تعذّر الفحص أصلاً — نظام غير ويندوز مثلاً).
    دالة منفصلة (بدل تضمينها بـonedrive_status) حتى يسهل استبدالها
    بالاختبارات — التسجيل حقيقي بجهاز المستخدم، ما نقدر نخترع بيانات
    وهمية بداخله."""
    try:
        import winreg
    except ImportError:
        return None
    emails = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\OneDrive\Accounts") as accounts_key:
            i = 0
            while True:
                try:
                    account_name = winreg.EnumKey(accounts_key, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(accounts_key, account_name) as account_key:
                        email, _ = winreg.QueryValueEx(account_key, "UserEmail")
                        if email:
                            emails.append(email)
                except OSError:
                    continue
    except OSError:
        pass
    return emails


def onedrive_status():
    """يفحص حالة حساب OneDrive الحقيقية (مسجَّل دخول فعلاً ولا لأ) — بمعزل
    تماماً عن وجود مجلد OneDrive نفسه. المجلد ممكن يكون موجود (حتى لو
    البرنامج مثبَّت بس الإعداد ما اكتمل) بينما الحساب مو مربوط إطلاقاً —
    وقتها أي ملف نكتبه بمجلده يبقى محلي بس، بلا أي رفع فعلي للسحابة،
    فحص وجود المجلد وحده (is_destination_reachable) ما يكفي لتأكيد هذا.

    يرجّع (الحالة, التفصيل):
      "not_installed"   — مجلد OneDrive نفسه مو موجود إطلاقاً.
      "not_signed_in"   — المجلد موجود، بس ماكو حساب مربوط (بريد فاضي بكل الحسابات).
      "signed_in"       — حساب حقيقي مربوط؛ التفصيل = بريده الإلكتروني.
      "unknown"         — تعذّر الفحص (نظام غير ويندوز مثلاً) — لا نجزم بشي.
    """
    if not os.path.exists(_ONEDRIVE_ACCOUNT_FOLDER):
        return "not_installed", None
    emails = _read_onedrive_account_emails()
    if emails is None:
        return "unknown", None
    if emails:
        return "signed_in", emails[0]
    return "not_signed_in", None
