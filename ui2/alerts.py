"""أدوات عرض مشتركة لكل شاشات ``ui2/`` (ليست خاصة بالأجور): صناديق رسائل
موحّدة، تنظيف قيم النماذج، وسمات عرض صغيرة. لا SQL ولا حساب.

تنسيق المبالغ **ليس هنا**: المصدر الوحيد هو
:func:`programme.payroll.calc.fmt_montant` (تستعمله شاشات ``ui2/`` والطبقة
القديمة ``ui/hr/paie`` معاً)."""
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List

from PySide6.QtWidgets import QLabel, QMessageBox

from ui2 import theme


def fmt_rate(value) -> str:
    """نسبة (0..1 أو معامل س.إضافية) بأربع خانات كحدّ أقصى بلا أصفار زائدة."""
    if value in (None, ""):
        return ""
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return format(d.normalize(), "f")


def clean(values: Dict) -> Dict:
    """يحذف المفاتيح ذات القيمة النصّية الفارغة — فتُخزَّن ``NULL`` بدل
    ``""`` في الأعمدة الاختيارية."""
    return {k: v for k, v in values.items()
            if not (isinstance(v, str) and v.strip() == "")}


def info_label(text: str) -> QLabel:
    """سطر توضيحي خافت (عنوان قسم / ملاحظة). ليس مكوّناً — لا بديل له
    في ``ui2/``."""
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{theme.TEXT_DIM};")
    return lbl


def warn(parent, title: str, lines: Iterable[str]) -> None:
    """صندوق تحذير موحّد (V15، V2…) — رسالة واضحة، لا ابتلاع صامت."""
    QMessageBox.warning(parent, title,
                        "\n".join("• " + str(x) for x in lines))


def confirm(parent, title: str, question: str) -> bool:
    box = QMessageBox(QMessageBox.Question, title, question,
                      QMessageBox.Yes | QMessageBox.No, parent)
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


ACTIF_CHOICES: List[str] = ["نشطة", "موقوفة"]


def actif_to_text(value) -> str:
    return ACTIF_CHOICES[0] if int(value or 0) == 1 else ACTIF_CHOICES[1]


def text_to_actif(text: str) -> int:
    return 1 if text == ACTIF_CHOICES[0] else 0
