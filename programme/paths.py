"""
مكان "الشغل" الأساسي المشترك بين كل شاشات البرنامج: مجلد travail بسطح
المكتب الحقيقي — مو جوا مجلد البرنامج نفسه (بطلب صريح: أسهل يوصله أي
عامل عادي بلا ما يدوّر جوا مجلدات البرنامج، وأسلم لو مجلد البرنامج نفسه
انحذف/انقل بالغلط لاحقاً، إعادة تنصيب...). كل شاشة تولّد مستندات (CD
حالياً، وأي خدمة ثانية لاحقاً) تاخذ مجلدها الفرعي الخاص منه
(travail/CD، travail/<اسم آخر>...) — نفس اصطلاح output/<اسم> القديم، بس
بمكان جديد.

ملاحظة تصميم: الدوال هون ترجع المسار بس (بلا os.makedirs) — إنشاء
المجلد فعلياً يبقى مسؤولية أول شي يحتاجه فعلاً (توليد أول مستند،
فتح شريط الملفات...)، بنفس الاصطلاح القديم بالضبط (تجنّب إنشاء مجلدات
حقيقية بسطح المكتب لمجرد استيراد module، قبل أي استخدام حقيقي)."""
import logging
import os
import shutil
from datetime import date

logger = logging.getLogger(__name__)

_TRAVAIL_ENV_OVERRIDE = "OFFICEMANAGER_TRAVAIL_ROOT"
_LOCAL_STATE_ENV_OVERRIDE = "OFFICEMANAGER_LOCAL_STATE_DIR"
_DATA_DIR_ENV_OVERRIDE = "OFFICEMANAGER_DATA_DIR"

# جذر حزمة "المحرّك" (programme/) — يُشتق منه مسار البيانات المشحونة مع
# الكود (data/)، لا يُكتب حرفياً في أي وحدة أخرى.
_PROGRAMME_DIR = os.path.dirname(os.path.abspath(__file__))
# جذر المشروع (مستوى فوق programme/).
_PROJECT_ROOT = os.path.dirname(_PROGRAMME_DIR)

_DB_FILENAME = "office_system.db"
_PARAMS_DIRNAME = "params_paie"
_MIGRATION_MARKER = ".data_migrated_v1"
_SHIPPED_PARAMS_DIR = os.path.join(_PROGRAMME_DIR, "data", _PARAMS_DIRNAME)


def get_real_desktop_dir():
    """يرجّع مسار سطح المكتب الحقيقي — يتعامل صح مع حالة كون سطح المكتب
    محوَّل (Redirected) لمجلد OneDrive (شائع بمكاتب كثيرة اليوم)، عبر
    قراءة القيمة الحقيقية من سجل ويندوز (User Shell Folders) بدل افتراض
    ساذج إنه دايماً %USERPROFILE%\\Desktop. يرجع للافتراض العادي لو
    الفحص فشل لأي سبب (نظام غير ويندوز، تعذّر قراءة السجل...)."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "Desktop")
            expanded = os.path.expandvars(value)
            if expanded:
                return expanded
    except (ImportError, OSError):
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def get_travail_root():
    """جذر مجلد الشغل المشترك (travail). قابل للتجاوز عبر متغيّر بيئة
    (OFFICEMANAGER_TRAVAIL_ROOT) — يستخدمه الاختبارات الآلية فقط، حتى ما
    تكتب فعلياً على سطح مكتب المستخدم الحقيقي أثناء التجربة."""
    override = os.environ.get(_TRAVAIL_ENV_OVERRIDE)
    if override:
        return override
    return os.path.join(get_real_desktop_dir(), "travail")


def get_screen_dir(name):
    """مجلد شاشة معيّنة جوا travail (زي travail/CD)."""
    return os.path.join(get_travail_root(), name)


def get_local_state_dir():
    """مجلد الحالة المحلية الخاصة بالجهاز — مسوّدات الشاشات وتفضيلات
    العرض (ملفات JSON صغيرة، مستثناة من git، ليست "شغل مستخدم" ولا مرجعاً
    قانونياً). اليوم = جذر المشروع (حيث ``cd_draft.json`` / ``cd_settings.json``
    تاريخياً). قابل للتجاوز بمتغيّر بيئة (OFFICEMANAGER_LOCAL_STATE_DIR) —
    للاختبارات الآلية حتى لا تكتب في جذر المستودع.

    يرجّع المسار فقط (بلا os.makedirs) — نفس اصطلاح باقي دوال هذا الملف.

    TODO (المهمة د / التحزيم بـPyInstaller): تنتقل إلى
    %APPDATA%\\OfficeManager\\ مع ترحيل تلقائي من المكان القديم، حتى تعمل
    الكتابة بعد التثبيت في Program Files (مجلد للقراءة فقط)."""
    override = os.environ.get(_LOCAL_STATE_ENV_OVERRIDE)
    if override:
        return override
    return _PROJECT_ROOT


# --- تصميم "قاعدة البيانات كمصدر الحقيقة" (راجع
# docs/cd-clients-architecture.md بند 3) ---
# مجلدات الزبائن و"Autre" مباشرة جوّا travail (لا جوّا مجلد خدمة فرعي
# زي travail/CD) — لأنها مشتركة بين كل الخدمات بطبيعتها: زبون واحد ممكن
# يكون عنده شغل CD وشغل خدمة ثانية لاحقاً، كلهم بنفس مجلده. التمييز بين
# الخدمات يكون بكود الخدمة على اسم الملف نفسه (CD_...)، لا بموقع المجلد.

def get_autre_dir():
    """travail/Autre — مكان الشغل بلا زبون معروف، مشترك بين كل الخدمات.
    جوّاه يبقى تقسيم الأشهر (Autre/2026-09/...) — نفس اصطلاح الأرشفة
    اليدوية القديم، بس منقول من travail/<خدمة> لـtravail/Autre مباشرة."""
    return os.path.join(get_travail_root(), "Autre")


def get_client_dir(folder_name):
    """travail/<folder_name> — مجلد زبون (مسطّح، بلا تقسيم شهور جوّاه)،
    مشترك بين كل الخدمات. folder_name يجي من clients.folder_name (محسوب
    مرة وحدة بـcreate_client)، لا من اسم الزبون الحي مباشرة — راجع
    مستند التصميم بند 3."""
    return os.path.join(get_travail_root(), folder_name)


# =====================================================================
#  مجلد بيانات المستخدم الدائم (%APPDATA%\OfficeManager) + الترحيل
# =====================================================================
#  السبب: بعد التحزيم بـPyInstaller في Program Files يصير مجلد البرنامج
#  للقراءة فقط، فقاعدة البيانات وملفات المعاملات (اللتان تُكتَب فيهما)
#  لا يمكن أن تبقيا بجانب الكود. الحلّ: %APPDATA%\OfficeManager\ — قابل
#  للكتابة دائماً وخاصّ بالمستخدم — مع ترحيل تلقائي لمرّة واحدة (نسخ لا
#  نقل) من المكان القديم، وتدرّج آمن لو تعذّر الترحيل.

def get_data_dir():
    """مجلد بيانات المستخدم الدائم: ``%APPDATA%\\OfficeManager\\`` على
    ويندوز (``~/.local/share/OfficeManager`` على غيره). قابل للتجاوز
    بمتغيّر البيئة ``OFFICEMANAGER_DATA_DIR`` (اختبارات + تجاوز يدوي).
    يرجّع المسار فقط (بلا إنشاء)."""
    override = os.environ.get(_DATA_DIR_ENV_OVERRIDE)
    if override:
        return override
    base = os.environ.get("APPDATA")                    # ويندوز
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "OfficeManager")


def _legacy_db_path():
    """المكان القديم لقاعدة البيانات (بجذر المشروع) — قبل الترحيل."""
    return os.path.join(_PROJECT_ROOT, _DB_FILENAME)


def get_db_path():
    """مسار قاعدة البيانات الفعلي، بتدرّج آمن:

      1. نسخة ``get_data_dir()`` إن وُجدت (بعد ترحيل ناجح، أو تثبيت جديد).
      2. وإلا النسخة القديمة بجذر المشروع إن وُجدت (ترحيل لم يقع / فشل).
      3. وإلا مسار ``get_data_dir()`` (تثبيت جديد تماماً) إن أمكن إنشاء
         مجلده، وإلا المكان القديم (احتياط أخير — لا نتعطّل أبداً)."""
    new = os.path.join(get_data_dir(), _DB_FILENAME)
    if os.path.exists(new):
        return new
    old = _legacy_db_path()
    if os.path.exists(old):
        return old
    try:
        os.makedirs(get_data_dir(), exist_ok=True)
        return new
    except OSError:
        return old


# --- معاملات حساب الأجور المؤرَّخة (programme/payroll) ---

def get_params_paie_dir():
    """مجلد ملفات معاملات الأجور المؤرَّخة (``params_<سنة>.json`` — SNMG،
    شرائح IRG، النسب، معاملات التنعيم...).

    بعد الترحيل: ``get_data_dir()\\params_paie`` — فتبقى قابلة للتحيين بعد
    كل قانون مالية بلا إعادة تثبيت. إن لم يوجد هناك ملف معاملات (ترحيل لم
    يقع أو فشل): المجلد المشحون مع الكود (``programme/data/params_paie``).

    يرجّع المسار فقط (بلا os.makedirs)."""
    new = os.path.join(get_data_dir(), _PARAMS_DIRNAME)
    try:
        has_params = os.path.isdir(new) and any(
            n.startswith("params_") and n.endswith(".json")
            for n in os.listdir(new))
    except OSError:
        has_params = False
    return new if has_params else _SHIPPED_PARAMS_DIR


def _copy_atomic(src, dst):
    """نسخ عبر ملف ``.partial`` مؤقّت ثم ``os.replace`` — لا يُترَك ``dst``
    نصف مكتوب لو انقطع النسخ."""
    tmp = dst + ".partial"
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def ensure_user_data_migrated(log=None):
    """ترحيل لمرّة واحدة من المكان القديم إلى :func:`get_data_dir`.
    **ينسخ لا ينقل**، ويُبقي القديم كما هو حتى يتأكّد النجاح.

    idempotent بصرامة عبر ملف علامة (``.data_migrated_v1``): تشغيلان
    متتاليان لا يكرّران النسخ ولا يكتبان فوق نسخة ``get_data_dir()``
    بالقديمة.

    فشل الكتابة إلى ``get_data_dir()`` (صلاحيات، قرص ممتلئ...) →
    **تحذير في السجلّ فقط، بلا علامة، ولا يتعطّل الإقلاع** — البرنامج
    يستمرّ من المكان القديم (:func:`get_db_path` يتدرّج).

    يُستدعى من ``main()`` قبل ``init_db()``."""
    log = log or logger
    data_dir = get_data_dir()
    marker = os.path.join(data_dir, _MIGRATION_MARKER)
    if os.path.exists(marker):
        return                                         # تمّ سابقاً — لا تكرار

    try:
        os.makedirs(data_dir, exist_ok=True)

        # 1) قاعدة البيانات — نسخة واحدة فقط، لا تدهس نسخة get_data_dir موجودة
        new_db = os.path.join(data_dir, _DB_FILENAME)
        old_db = _legacy_db_path()
        if os.path.exists(new_db):
            log.info("ترحيل البيانات: نسخة %s من قاعدة البيانات موجودة "
                     "أصلاً — تُترَك كما هي.", data_dir)
        elif os.path.exists(old_db):
            _copy_atomic(old_db, new_db)
            log.info("ترحيل البيانات: نُسخت قاعدة البيانات إلى %s "
                     "(القديمة باقية).", new_db)
        # لا قديمة ولا جديدة = تثبيت جديد تماماً — init_db ينشئها في new_db.

        # 2) params_paie — انسخ أيّ ملف مشحون غير موجود هناك (يغطّي أيضاً
        #    ملفّات سنوات لاحقة تصل مع تحديث الكود). لا يدهس ملفاً موجوداً
        #    (قد يكون المستخدم حيّنه يدوياً).
        new_params = os.path.join(data_dir, _PARAMS_DIRNAME)
        os.makedirs(new_params, exist_ok=True)
        copied = 0
        for name in sorted(os.listdir(_SHIPPED_PARAMS_DIR)):
            if not (name.startswith("params_") and name.endswith(".json")):
                continue
            dst = os.path.join(new_params, name)
            if not os.path.exists(dst):
                _copy_atomic(os.path.join(_SHIPPED_PARAMS_DIR, name), dst)
                copied += 1
        if copied:
            log.info("ترحيل البيانات: نُسخ %d ملف معاملات إلى %s.",
                     copied, new_params)

        # 3) العلامة — تُكتب فقط بعد نجاح كل ما سبق
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(date.today().isoformat())
        log.info("ترحيل البيانات: اكتمل — المكان الجديد %s.", data_dir)
    except OSError as exc:
        log.warning("ترحيل البيانات إلى %s تعذّر (%s) — يستمرّ البرنامج "
                    "من المكان القديم.", data_dir, exc)
