"""أنواعٌ صغيرة مشتركة لنظام الإغلاق الآمن (P2.5 §3/§4) — Enum بدل
strings مبعثرة. لا منطق هنا، فقط تعريف القيَم المسموحة.

ملفٌ منفصل (لا داخل ``work.py``/``close_controller.py``) لتفادي أي
اعتماديّة دائرية: ``work.py`` يحتاج ``SaveResult`` لعقد
``WorkSession.save()``، و``unsaved_dialog.py``/``close_controller.py``
يحتاجان الثلاثة معاً — كلاهما يستوردان من هنا بلا استيراد أحدهما الآخر."""
from enum import Enum, auto


class SaveResult(Enum):
    """نتيجة ``WorkSession.save()`` — لا استثناءات، لا bool غامض (P2.5 §3)."""

    SUCCESS = auto()      # يمكن متابعة الإغلاق
    CANCELLED = auto()    # المستخدم ألغى عملية الحفظ نفسها (حوار داخليّ لخدمة لاحقاً) — لا إغلاق
    FAILED = auto()       # فشل الحفظ (أو استثناء) — لا إغلاق، رسالة خطأ


class CloseDecision(Enum):
    """قرار المستخدم عند إغلاق عملٍ واحدٍ dirty (P2.5 §4/§5)."""

    SAVE = auto()
    DISCARD = auto()
    CANCEL = auto()


class MultiCloseDecision(Enum):
    """قرار المستخدم عند إغلاق عدّة أعمالٍ dirty معاً (P2.5 §9/§10/§11) —
    Close All أو إغلاق التطبيق."""

    SAVE_ALL = auto()
    DISCARD_ALL = auto()
    CANCEL = auto()
