"""
نقطة مركزية وحيدة لكل تنبيهات/نوافذ تأكيد البرنامج — بدل ما يستدعي كل
ملف tkinter.messagebox مباشرة لحاله بمنطقه الخاص (كانت مبعثرة بـ11 ملف
مختلف). أي شاشة تحتاج تنبيه تستورد من هون بس، حتى نلقى كل تنبيهات
البرنامج بمكان واحد بسهولة، ونقدر نبدّل سلوكها (نص، شكل، تعطيل وقت
التجربة...) بلا ما نبحث بعشرات الملفات.

confirm(): بديل messagebox.askyesno يحترم CONFIRM_DIALOGS_ENABLED (نعم/لا
قبل إجراء قد يفقد بيانات — خروج/مستند جديد/تنقّل ببيانات غير محفوظة،
توليد مستند بحقول أساسية فاضية...). كانت موقوفة مؤقتاً أثناء التجربة
المكثّفة للبرنامج (حتى ما تنقطع كل شوي بنافذة)، رجّعناها True بطلب
صريح بعد ما البرنامج صار جاهز للاستخدام الحقيقي — جزء أساسي من حماية
بيانات الموظف (زي أي برنامج عادي: يحذّرك قبل ما تخسر شغل ما اتحفظ).

confirm_always(): زي confirm() بس **بلا** أي تعطيل إطلاقاً — لحالات
حماية حرجة المفروض تسأل دايماً بغض النظر عن وضع التجربة (زي إغلاق
تبويب فيه تعديل غير محفوظ بـCD — نطاق ضيّق ومقصود، بطلب صريح).

info()/warning()/error(): تمرير مباشر لدالة messagebox المقابلة — بلا
أي تعطيل (رسائل معلومة/خطأ حقيقية، ما يصح نخفيها حتى وقت التجربة —
إخفاء رسالة خطأ حقيقية يعني نفوّت خللاً حقيقياً بصمت).

ملاحظة لأي كود/اختبار يبدّل CONFIRM_DIALOGS_ENABLED وقتياً: لازم تبدّله
هنا بالضبط (ui.common.alerts.CONFIRM_DIALOGS_ENABLED) عبر استيراد
الموديول (import ui.common.alerts as alerts؛ alerts.CONFIRM_DIALOGS_ENABLED
= ...) — لا `from ui.common.alerts import CONFIRM_DIALOGS_ENABLED` بملف
آخر (ينسخ القيمة وقت الاستيراد بس، وتبديلها هناك بعدها ما يوصل لـ
confirm() تحت لأنها تقرأ من هذا الملف تحديداً). confirm()/confirm_always()
نفسهم يُستوردون ويُستدعون عادي من أي مكان بلا أي مشكلة.
"""
from tkinter import messagebox

CONFIRM_DIALOGS_ENABLED = True


def confirm(title, message, **kwargs):
    """بديل messagebox.askyesno يحترم CONFIRM_DIALOGS_ENABLED أعلاه — لو
    موقوفة، يرجّع "نعم" (تكملة الإجراء) مباشرة بدون إظهار أي نافذة.
    **kwargs تُمرَّر كما هي لـmessagebox (زي parent=... لنافذة معيّنة)."""
    if not CONFIRM_DIALOGS_ENABLED:
        return True
    return messagebox.askyesno(title, message, **kwargs)


def confirm_always(title, message, **kwargs):
    """زي confirm() بس بلا أي تعطيل — راجع شرح الملف بالأعلى."""
    return messagebox.askyesno(title, message, **kwargs)


def info(title, message, **kwargs):
    return messagebox.showinfo(title, message, **kwargs)


def warning(title, message, **kwargs):
    return messagebox.showwarning(title, message, **kwargs)


def error(title, message, **kwargs):
    return messagebox.showerror(title, message, **kwargs)
