"""Work Commands — معرّفات ثابتة + Metadata مركزية (P2 §1/§2).

مجموعةٌ صغيرة متعمَّدة من الأوامر العامّة لأيّ Work مستقبليّ (Paie/CD/
Attestation...). **ليست** Work Commands: تنقّل الصفحات/التكبير (مكانهما
``WorkStatusBar``، يُربَطان لاحقاً بعملٍ حقيقيّ) ولا القفل العامّ
للتطبيق (ليس أمر عمل، بل حالة تطبيق كاملة).

هذا الملف Metadata فقط — لا تنفيذ هنا إطلاقاً. التنفيذ الفعليّ يأتي من
``WorkSession`` النشِط (راجع ``WorkCommandBinding`` في ``ui2.shell.work``)؛
هذه القائمة عامّة للبرنامج بأكمله ولا تعرف شيئاً عن أيّ خدمة (P2 §14)."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandId(str, Enum):
    SAVE = "save"
    PRINT = "print"
    UNDO = "undo"
    REDO = "redo"
    FINALIZE = "finalize"
    DUPLICATE = "duplicate"


class CommandGroup(str, Enum):
    FILE = "file"
    EDIT = "edit"
    WORKFLOW = "workflow"


@dataclass(frozen=True)
class CommandSpec:
    """Metadata ثابتة لأمرٍ واحد — لا حالة، لا handler هنا (ذاك من
    ``WorkSession``، P2 §2)."""

    id: CommandId
    group: CommandGroup
    label: str
    shortcut: Optional[str] = None
    tooltip: str = ""


#  ‏ترتيبٌ ثابت (P2 §8/§15): CommandManager/CommandBar يعتمدان عليه
#  حرفياً لعرض الأوامر — لا على ترتيب dict الخاصّ بأيّ Work. القائمة
#  مرتَّبة أصلاً حسب المجموعة (FILE ثم EDIT ثم WORKFLOW).
COMMAND_REGISTRY = (
    CommandSpec(CommandId.SAVE, CommandGroup.FILE,
                "حفظ", "Ctrl+S", "حفظ العمل الحالي"),
    #  ‏P3.2 §17: التلميح "معاينة / طباعة" — بعض الأعمال (Paie حالياً)
    #  تربط PRINT بمعاينةٍ فعلية (فتح PDF/DOCX الموجود) لا طباعةً
    #  مباشرة؛ لا CommandId جديد (خيار A) — التسمية العامّة صادقة لكلا
    #  الحالتين بدل الادّعاء بطباعة حقيقية دائماً.
    CommandSpec(CommandId.PRINT, CommandGroup.FILE,
                "طباعة", "Ctrl+P", "معاينة / طباعة العمل الحالي"),
    CommandSpec(CommandId.UNDO, CommandGroup.EDIT,
                "تراجع", "Ctrl+Z", "تراجع عن آخر تعديل"),
    CommandSpec(CommandId.REDO, CommandGroup.EDIT,
                "إعادة", "Ctrl+Y", "إعادة آخر تراجع"),
    CommandSpec(CommandId.FINALIZE, CommandGroup.WORKFLOW,
                "إنهاء", None, "إنهاء/اعتماد العمل"),
    CommandSpec(CommandId.DUPLICATE, CommandGroup.WORKFLOW,
                "تكرار", None, "تكرار العمل الحالي"),
)

#  ‏ترتيب المجموعات نفسها — يُستعمَل لوضع الفواصل بين مجموعاتٍ لديها
#  أوامر ظاهرة فقط (P2 §15: لا فاصل فارغ).
GROUP_ORDER = (CommandGroup.FILE, CommandGroup.EDIT, CommandGroup.WORKFLOW)
