"""
ثوابت وأدوات مشتركة بين كل ملفات خدمة CD (entries.py، history.py،
tab.py — document.py مستقل، عنده ثوابته الخاصة بالمستند نفسه) — مسارات
الملفات المحلية، أسماء حقول المسودة/إعدادات المكتب، وثوابت العرض (خط،
ألوان، زوم). نوافذ التأكيد (raise/confirm) انتقلت لملف مشترك لكل
البرنامج — راجع ui/common/alerts.py.

ملف واحد بلا أي اعتماد على باقي ملفات cd/ الثانية (حتى ما يصير استيراد
دائري) — كل ملف بالحزمة يستورد منه اللي يحتاجه بس.
"""
import json
import os

from ui.common.widgets import EMPTY_BG_COLOR, FILLED_BG_COLOR  # noqa: F401 (يُعاد تصديرها لـentries.py/tab.py)

# ملفات حالة محلية (مو مرتبطة بمشروع Git — راجع .gitignore): إعدادات
# المكتب الثابتة (تُتذكَّر بين الجلسات) ومسودة العمل الجاري (استرجاع
# بعد إغلاق غير متوقع). بجذر المشروع، جنب قاعدة البيانات — هذا الملف
# بـui/cd/constants.py (3 مستويات تحت الجذر)، فلازم 3 dirname بالضبط.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CD_SETTINGS_PATH = os.path.join(_APP_ROOT, "cd_settings.json")
CD_DRAFT_PATH = os.path.join(_APP_ROOT, "cd_draft.json")
# تفضيلات واجهة بس (زي مستوى الزوم) — منفصلة عمداً عن إعدادات المكتب
# والمسودة، حتى ما نخلط اهتمامات مختلفة بملف واحد.
CD_UI_PREFS_PATH = os.path.join(_APP_ROOT, "cd_ui_prefs.json")

# حقول "المكتب" الثابتة — نفس الموظف/الشباك عادةً كل يوم، تُتذكَّر
# تلقائياً بين الجلسات (بعكس بيانات الراكب الشخصية، تتغيّر كل مرة).
# agence_no ورقم/اسم الوكالة سطر واحد بالمستند، هوية المكتب نفسها — نفس
# منطق agence بالضبط.
OFFICE_FIELD_KEYS = ["agence_no", "agence", "guichet_no", "guichet", "caisse_no", "caisse", "guichetier"]

# حقول المسودة القابلة للاسترجاع أوتوماتيكياً لو البرنامج انقفل بالغلط
# وسط التعبئة — التاريخ والوقت مستثنيان عمداً (تفضّل تكتبهما يدوياً
# دائماً)، وكذا لأن استرجاع حالتهما الداخلية (مو بس النص المعروض) أعقد
# وأخطر لو انحرف. الحقول الفاضية بالأصل ما تُحفظ ولا تُستعاد بمشكلة.
DRAFT_FIELD_KEYS = [
    "no", "agence_no", "agence", "devise_code", "devise",
    "guichet_no", "guichet", "caisse_no", "caisse", "guichetier",
    "passager", "passport_no", "date_delivrance", "taux", "eur", "dzd",
]

# الحقول اللي فعلاً تدل على "معاملة جارية تستاهل حفظ مسودة" — بدون
# حقول المكتب (Agence/Guichet/Caisse/Guichetier): هذي محفوظة أصلاً
# بإعدادات المكتب وتُتذكَّر لحالها، فتعبئتها وحدها (بدون أي بيانات
# شخصية) ما تعتبر "عمل جاري" يستاهل مسودة أو تنبيه قبل المغادرة. نفس
# النطاق يُستخدم أيضاً لحدود التبويبات (كل تبويب مستقل بهذي الحقول بس —
# راجع tab.py) وتاريخ التراجع/الإعادة.
_TRANSACTIONAL_DRAFT_KEYS = [k for k in DRAFT_FIELD_KEYS if k not in OFFICE_FIELD_KEYS]


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass  # حفظ ثانوي (إعدادات/مسودة) — فشل الكتابة ما يوقف الشاشة


TARGET_W = 750  # عرض الصورة الأساسي (زوم 100%)
CANVAS_MARGIN = 20  # أقل مسافة بين الورقة وحواف منطقة العرض
# 9 كانت تعطي عرض حرف أضيق فعلياً (7px) من عرض الحرف الحقيقي بالمستند
# بنفس التكبير (8.3px تقريباً، محسوبة من نفس صيغة field_layout_px) —
# فرق كان يبين كفجوة بيضاء زايدة قبل أي نص "يُكتب أوتوماتيكياً" مباشرة
# بعد خانة كتابة (زي اسم الراكب المكرر بعد Guichet). 10 أقرب قياس ممكن
# (الأحجام صحيحة أرقام كاملة بس بـTk، ما فيها كسور) لعرض الحرف الحقيقي.
BASE_FONT_SIZE = 10
# هامش داخلي ثابت (بالبكسل) تفرضه Tk على أي Entry حتى مع bd=0 و
# highlightthickness=1 (حلقة التركيز + حواف الودجت الداخلية) — قسناها
# مباشرة (Entry بنفس الإعدادات، مقارنة winfo_reqwidth() بعرض النص
# المحسوب من الخط نفسه)، وتأكدنا إنها ثابتة 4px بالضبط بغض النظر عن حجم
# الخط أو عدد الأحرف. عادة تُمتص ضمن الهامش الطبيعي بين عدد الأحرف
# الصحيح وعرضه بالبكسل (field_layout_px) بالحقول العريضة، لكن بالحقول
# الضيقة جداً (زي رمز العملة 3 أحرف) الهامش الطبيعي أقل من 4px، فآخر حرف
# مكتوب ينقص بصرياً (يُقص) بدونها — راجع _relayout() بـtab.py.
ENTRY_CHROME_PX = 4
HOVER_IDLE_COLOR = "white"   # بلا إطار ظاهر (يندمج مع خلفية الورقة البيضاء) — لخانة معبّأة
HOVER_ON_COLOR = "#4a90d9"   # لون الإطار وقت التحويم
# EMPTY_BG_COLOR/FILLED_BG_COLOR (تمييز الحقول الفاضية بلون خلفية الخانة
# نفسها) معرَّفة ومستوردة من ui.common.widgets فوق — نفس اللون بالضبط
# يستخدمه CD وخانات التاريخ/الوقت المركّبة معاً (SplitDateEntry/
# MaskedDateEntry)، فمصدر واحد يمنع أي اختلاف بينهم لاحقاً.
ZOOM_LEVELS = [50, 75, 100, 125, 150, 175, 200]  # نسب مئوية نظيفة (كسور بسيطة)
DEFAULT_ZOOM_INDEX = ZOOM_LEVELS.index(100)

# نوافذ التأكيد (نعم/لا) انتقلت لملف مركزي واحد لكل البرنامج — راجع
# ui/common/alerts.py (CONFIRM_DIALOGS_ENABLED وconfirm()) بدل ما تبقى
# خاصة بـCD بس.


def _safe_float_or_none(text):
    text = (text or "").strip()
    if not text:
        return None
    if "." in text and "," in text:
        # صيغة فرنسية مُنسَّقة (زي "1.000,00"): النقطة فاصل آلاف، الفاصلة
        # فاصل عشري — نشيل النقاط أولاً ثم نبدّل الفاصلة بنقطة عشرية.
        text = text.replace(".", "").replace(",", ".")
    else:
        # صيغة بسيطة (زي taux "151.11" أو فاصلة عشرية وحيدة بلا فواصل آلاف).
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _fmt_amount(value, decimals=2):
    """يحوّل رقم عائم لنص بصيغة فرنسية (فاصل آلاف "." وفاصلة عشرية ",")
    — عكس _safe_float_or_none، لتعبية حقول المبالغ عند تحميل مستند سابق
    (نفس التنسيق اللي ياخذوه لما تُكتبان يدوياً)."""
    return f"{value:,.{decimals}f}".translate(str.maketrans(",.", ".,"))
