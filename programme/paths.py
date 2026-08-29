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
import os

_TRAVAIL_ENV_OVERRIDE = "OFFICEMANAGER_TRAVAIL_ROOT"


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
