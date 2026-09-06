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
_LTR_KINDS = {"number", "amount", "date", "ssn"}
KINDS = {"text", "multiline", "choice"} | _LTR_KINDS


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

        if f.kind == "date":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("yyyy-MM-dd")
            d = QDate.fromString(str(f.default), "yyyy-MM-dd")
            w.setDate(d if d.isValid() else QDate.currentDate())
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
            elif isinstance(w, QDateEdit):
                out[f.key] = w.date().toString("yyyy-MM-dd")
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
            elif isinstance(w, QDateEdit):
                d = QDate.fromString(str(val), "yyyy-MM-dd")
                if d.isValid():
                    w.setDate(d)
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
            elif f.kind == "date" and not QDate.fromString(val, "yyyy-MM-dd").isValid():
                errs.append(f"«{f.label}» تاريخ غير صالح (YYYY-MM-DD).")
        return errs

    def widget(self, key: str) -> QWidget:
        return self._widgets[key]
