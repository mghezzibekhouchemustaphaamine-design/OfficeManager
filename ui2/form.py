"""بنّاء نماذج: وصف حقول (:class:`Field`) → ``QFormLayout`` بتسميات
ومحاذاة صحيحة.

**سلوك المكتبة:** الحقول اللاتينية (``number`` / ``amount`` / ``date`` /
``ssn``) تأخذ ``LeftToRight`` تلقائياً حسب نوع الحقل — لا تكرار لهذا
الالتفاف في كل شاشة.

التحقّق شكليّ فقط (إلزاميّ + صيغة) — لا SQL ولا منطق حساب.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFormLayout, QLineEdit, QPlainTextEdit, QWidget,
)

# الأنواع اللاتينية: تُجبَر على LTR على مستوى الحقل
_LTR_KINDS = {"number", "amount", "date", "month", "ssn"}
KINDS = {"text", "multiline", "choice"} | _LTR_KINDS

_DATE_FMT = {"date": "yyyy-MM-dd", "month": "yyyy-MM"}


class _DateEdit(QDateEdit):
    """``QDateEdit`` بصيغة ISO (``yyyy-MM-dd`` أو ``yyyy-MM``). إن كان
    الحقل غير إجباري فهو **يقبل «لا تاريخ»**: عند التاريخ الأدنى يعرض
    نصّاً خاصاً ويردّ ``""``؛ ``Delete`` / ``Backspace`` يعيده إلى «لا
    تاريخ». يمنع إدخال صيغ حرّة خاطئة (سبب قبول «13/01/2016» صامتاً سابقاً)."""

    def __init__(self, fmt: str, *, nullable: bool, parent=None):
        super().__init__(parent)
        self._fmt = fmt
        self._nullable = nullable
        self.setCalendarPopup(True)
        self.setDisplayFormat(fmt)
        if nullable:
            self.setMinimumDate(QDate(1900, 1, 1))
            self.setSpecialValueText("—")

    def keyPressEvent(self, event):                       # noqa: N802 (Qt)
        if self._nullable and event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.setDate(self.minimumDate())
            return
        super().keyPressEvent(event)

    def iso(self) -> str:
        if self._nullable and self.date() == self.minimumDate():
            return ""
        return self.date().toString(self._fmt)

    def set_iso(self, value) -> None:
        d = QDate.fromString(str(value or ""), self._fmt)
        if d.isValid():
            self.setDate(d)
        elif self._nullable:
            self.setDate(self.minimumDate())


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"
    required: bool = False
    placeholder: str = ""
    choices: Optional[List[str]] = None
    default: Any = ""
    max_len: Optional[int] = None


class Form(QWidget):
    def __init__(self, fields: List[Field], parent=None):
        super().__init__(parent)
        self._fields = list(fields)
        self._widgets: Dict[str, QWidget] = {}

        lay = QFormLayout(self)
        lay.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        for f in self._fields:
            w = self._make_widget(f)
            if f.kind in _LTR_KINDS:
                w.setLayoutDirection(Qt.LeftToRight)      # ← سلوك المكتبة
            self._widgets[f.key] = w
            lay.addRow(f.label + (" *" if f.required else ""), w)

    # -------------------- بناء الودجت حسب النوع --------------------
    def _make_widget(self, f: Field) -> QWidget:
        if f.kind == "multiline":
            w = QPlainTextEdit()
            w.setPlainText(str(f.default or ""))
            if f.placeholder:
                w.setPlaceholderText(f.placeholder)
            w.setFixedHeight(72)
            return w

        if f.kind == "choice":
            w = QComboBox()
            w.addItems(f.choices or [])
            if f.default:
                w.setCurrentText(str(f.default))
            return w

        if f.kind in ("date", "month"):
            fmt = _DATE_FMT[f.kind]
            # حقل غير إجباري = يقبل «لا تاريخ»؛ إجباري = دائماً بقيمة.
            w = _DateEdit(fmt, nullable=not f.required)
            d = QDate.fromString(str(f.default or ""), fmt)
            if d.isValid():
                w.setDate(d)
            elif not f.required:
                w.setDate(w.minimumDate())               # يبدأ «غير محدَّد»
            else:
                w.setDate(QDate.currentDate())
            return w

        w = QLineEdit(str(f.default or ""))
        if f.placeholder:
            w.setPlaceholderText(f.placeholder)
        if f.max_len:
            w.setMaxLength(f.max_len)
        if f.kind == "number":
            w.setValidator(QIntValidator())
        elif f.kind == "amount":
            v = QDoubleValidator()
            v.setBottom(0.0)
            v.setDecimals(2)
            v.setNotation(QDoubleValidator.StandardNotation)
            w.setValidator(v)
        elif f.kind == "ssn":
            w.setValidator(QIntValidator())
            w.setMaxLength(f.max_len or 15)
        return w

    # -------------------- الواجهة العمومية --------------------
    def values(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for f in self._fields:
            w = self._widgets[f.key]
            if isinstance(w, QPlainTextEdit):
                out[f.key] = w.toPlainText().strip()
            elif isinstance(w, QComboBox):
                out[f.key] = w.currentText()
            elif isinstance(w, _DateEdit):
                out[f.key] = w.iso()
            else:
                out[f.key] = w.text().strip()
        return out

    def set_values(self, data: Dict[str, Any]):
        for key, val in data.items():
            w = self._widgets.get(key)
            if w is None:
                continue
            if isinstance(w, QPlainTextEdit):
                w.setPlainText(str(val or ""))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(val or ""))
            elif isinstance(w, _DateEdit):
                w.set_iso(val)
            else:
                w.setText("" if val is None else str(val))

    def errors(self) -> List[str]:
        """قائمة رسائل الأخطاء (فارغة = صالح). تحقّق شكليّ فقط."""
        errs: List[str] = []
        vals = self.values()
        for f in self._fields:
            val = vals.get(f.key, "")
            if f.required and not val:
                errs.append(f"«{f.label}» إجباري.")
                continue
            if not val:
                continue
            if f.kind == "amount":
                try:
                    if float(val.replace(",", ".")) < 0:
                        errs.append(f"«{f.label}» يجب ألا يكون سالباً.")
                except ValueError:
                    errs.append(f"«{f.label}» ليس مبلغاً صالحاً.")
            elif f.kind == "number" and not val.lstrip("-").isdigit():
                errs.append(f"«{f.label}» يجب أن يكون رقماً صحيحاً.")
            elif f.kind in ("date", "month") and not QDate.fromString(
                    val, _DATE_FMT[f.kind]).isValid():
                errs.append(f"«{f.label}» تاريخ غير صالح.")
        return errs

    def widget(self, key: str) -> QWidget:
        return self._widgets[key]
