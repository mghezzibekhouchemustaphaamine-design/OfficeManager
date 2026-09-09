"""بنّاء نماذج: وصف حقول (:class:`Field`) → ``QFormLayout`` بتسميات
ومحاذاة صحيحة.

**سلوك المكتبة:** الحقول اللاتينية (``number`` / ``amount`` / ``date`` /
``ssn``) تأخذ ``LeftToRight`` تلقائياً حسب نوع الحقل — لا تكرار لهذا
الالتفاف في كل شاشة.

التحقّق شكليّ فقط (إلزاميّ + صيغة) — لا SQL ولا منطق حساب.
"""
import re
from dataclasses import dataclass
from datetime import date as _pydate, datetime as _pydatetime
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QDate, QEvent, Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QCalendarWidget, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from ui2 import theme

# الأنواع اللاتينية: تُجبَر على LTR على مستوى الحقل
_LTR_KINDS = {"number", "amount", "date", "month", "ssn"}
KINDS = {"text", "multiline", "choice"} | _LTR_KINDS

_DATE_FMT = {"date": "yyyy-MM-dd", "month": "yyyy-MM"}

# نائبات العرض (فرنسية) وصيَغ اللصق المقبولة (تُطبَّع إلى display_format)
_PLACEHOLDER = {"date": "JJ/MM/AAAA", "month": "AAAA-MM"}
_PASTE_DATE = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")
_PASTE_MONTH = ("%Y-%m", "%m/%Y", "%Y/%m", "%m-%Y")


def _parse_display_format(fmt: str):
    """يفكّك صيغة العرض إلى ``(kind, sep, segments)`` — ``segments`` قائمة
    ``(name, width)`` بترتيب العرض (``name`` ∈ ``d`` / ``m`` / ``y``)."""
    toks = re.findall(r"[A-Za-z]+", fmt)
    seps = re.findall(r"[^A-Za-z]", fmt)
    sep = seps[0] if seps else "/"
    seg = []
    for t in toks:
        head = t[0].lower()
        if head == "d":
            seg.append(("d", 2))
        elif head == "m":
            seg.append(("m", 2))
        elif head == "y":
            seg.append(("y", 4))
    kind = "date" if any(n == "d" for n, _w in seg) else "month"
    return kind, sep, seg


class _MaskLineEdit(QLineEdit):
    """``QLineEdit`` يوجّه اللصق إلى :class:`DateField` (تطبيع تاريخ صالح
    بأي فاصل معقول، ورفض صامت لغير الصالح)."""

    def __init__(self, owner: "DateField"):
        super().__init__(owner)
        self._owner = owner

    def insertFromMimeData(self, source):                 # noqa: N802 (Qt)
        txt = (source.text() if source is not None and source.hasText()
               else "").strip()
        if not self._owner._try_paste(txt):
            pass                                          # لصق غير صالح → تجاهُل


class DateField(QWidget):
    """حقل التاريخ الموحّد لـ ``ui2`` — إدخال نصّي مُقنَّع + زرّ تقويم.

    * **التخزين/القراءة البرمجية = ISO حصراً**: :meth:`iso` تُعيد
      ``YYYY-MM-DD`` (أو ``YYYY-MM``) لتاريخ كامل صالح، وإلا ``""``؛
      :meth:`set_iso` تقبل ISO فقط (غير ذلك ⇒ يُفرَّغ الحقل).
    * **العرض مستقلّ** عبر ``display_format`` (افتراضه ``dd/MM/yyyy``).
    * **أربع حالات**: ``neutral`` (فارغ) · ``incomplete`` · ``valid`` ·
      ``error`` — تلوين الحقل + رسالة سطرية (بلا صناديق حوار).
    * إدخال أرقام فقط؛ ``/`` ``-`` ``.`` والمسافة تُوحَّد إلى فاصل العرض؛
      الحروف تُتجاهَل بصمت؛ الإدخال الجزئي مسموح.
    * التحقّق: أثناء الكتابة (صيغة) · عند المغادرة/‏Tab (صلاحية تقويمية) ·
      وقواعد إضافية اختيارية (:meth:`set_extra_check`، ``min_date`` /
      ``max_date``). ``Tab`` لا ينتقل ما دام الحقل ``incomplete`` / ``error``.

    ``_DateEdit`` اسمٌ بديل تاريخي لهذا الصنف (توافق خلفي مع الاستيرادات
    القائمة و :class:`Form`)."""

    dateChanged = Signal(QDate)
    errorChanged = Signal(str)                            # "" = لا خطأ
    stateChanged = Signal(str)

    NEUTRAL, INCOMPLETE, VALID, ERROR = (
        "neutral", "incomplete", "valid", "error")

    def __init__(self, display_format: str = "dd/MM/yyyy", *,
                 nullable: bool = True, placeholder: Optional[str] = None,
                 min_date=None, max_date=None, flat: bool = False,
                 inline_error: bool = True, parent=None):
        super().__init__(parent)
        self._kind, self._sep, self._segs = _parse_display_format(display_format)
        self._display_format = display_format
        self._nullable = nullable
        self._flat = flat
        self._inline_error = inline_error
        self._total_digits = sum(w for _n, w in self._segs)
        self._min = self._to_pydate(min_date)
        self._max = self._to_pydate(max_date)
        self._extra_check: Optional[Callable[[_pydate], Optional[str]]] = None
        self._state = self.NEUTRAL
        self._error = ""
        self._cal_popup: Optional[QFrame] = None

        self._edit = _MaskLineEdit(self)
        self._edit.setPlaceholderText(
            placeholder or _PLACEHOLDER.get(self._kind, "JJ/MM/AAAA"))
        self._edit.setFrame(False)
        self._edit.setLayoutDirection(Qt.LeftToRight)
        self._edit.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._edit.textEdited.connect(self._on_text_edited)
        self._edit.editingFinished.connect(lambda: self._apply_state())
        self._edit.installEventFilter(self)

        self._btn = QToolButton(self)
        self._btn.setText("📅")
        self._btn.setToolTip("تقويم")
        self._btn.setFocusPolicy(Qt.NoFocus)
        self._btn.setAutoRaise(True)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFixedWidth(22)
        self._btn.clicked.connect(self._open_calendar)

        self._err_lbl = QLabel("", self)
        self._err_lbl.setWordWrap(True)
        self._err_lbl.setStyleSheet(
            f"color:{theme.DANGER}; font-size:11px; background:transparent;")
        self._err_lbl.hide()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._edit, 1)
        row.addWidget(self._btn, 0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(1)
        outer.addLayout(row)
        if inline_error:
            outer.addWidget(self._err_lbl)

        self.setLayoutDirection(Qt.LeftToRight)
        self._refresh_style()

    # ----------------------- أدوات -----------------------
    @staticmethod
    def _to_pydate(v):
        if v is None:
            return None
        if isinstance(v, _pydate):
            return v
        if isinstance(v, QDate):
            return _pydate(v.year(), v.month(), v.day()) if v.isValid() else None
        try:
            return _pydate.fromisoformat(str(v)[:10])
        except ValueError:
            return None

    def _iso_fmt(self) -> str:
        return "%Y-%m-%d" if self._kind == "date" else "%Y-%m"

    def _cur_digits(self) -> str:
        return re.sub(r"\D", "", self._edit.text())[:self._total_digits]

    def _format_digits(self, digits: str) -> str:
        digits = re.sub(r"\D", "", digits)[:self._total_digits]
        out, i = [], 0
        for _name, w in self._segs:
            if i >= len(digits):
                break
            out.append(digits[i:i + w])
            i += w
        return self._sep.join(out)

    def _parsed(self):
        """``(pydate|None, complete)`` — ``complete`` إذا كل الأرقام موجودة."""
        digits = self._cur_digits()
        if len(digits) < self._total_digits:
            return None, False
        vals, i = {}, 0
        for name, w in self._segs:
            vals[name] = int(digits[i:i + w])
            i += w
        try:
            return _pydate(vals.get("y", 1), vals.get("m", 1),
                           vals.get("d", 1)), True
        except ValueError:
            return None, True

    def _compute_state(self):
        digits = self._cur_digits()
        if not digits:
            return self.NEUTRAL, ""
        d, complete = self._parsed()
        if not complete:
            return self.INCOMPLETE, ""
        if d is None:
            return self.ERROR, "تاريخ مستحيل."
        if self._max is not None and d > self._max:
            return self.ERROR, "لا يُقبل تاريخ في المستقبل."
        if self._min is not None and d < self._min:
            return self.ERROR, "تاريخ أقدم من الحدّ المسموح."
        if self._extra_check is not None:
            msg = self._extra_check(d)
            if msg:
                return self.ERROR, msg
        return self.VALID, ""

    # ----------------------- الحالة والنمط -----------------------
    def _apply_state(self, *, silent: bool = False) -> None:
        st, msg = self._compute_state()
        changed = (st != self._state) or (msg != self._error)
        self._state, self._error = st, msg
        self._refresh_style()
        self._err_lbl.setText(msg)
        self._err_lbl.setVisible(bool(msg) and self._inline_error)
        if changed and not silent:
            self.stateChanged.emit(st)
            self.errorChanged.emit(msg)

    def _refresh_style(self) -> None:
        if self._state == self.NEUTRAL:
            bg = theme.FIELD_EMPTY
        elif self._state == self.ERROR:
            bg = theme.FIELD_INVALID
        else:
            bg = theme.SURFACE
        border = (theme.DANGER if self._state == self.ERROR
                  else ("#ffffff" if self._flat else theme.BORDER))
        self._edit.setStyleSheet(
            f"QLineEdit{{background:{bg}; color:{theme.TEXT}; "
            f"border:1px solid {border}; border-radius:0; padding:0 1px; "
            f"selection-background-color:{bg}; selection-color:{theme.TEXT};}}")
        self._btn.setStyleSheet(
            "QToolButton{border:none; background:transparent;}")

    def refresh_style(self) -> None:                      # للمستدعي الخارجي
        self._refresh_style()

    def revalidate(self) -> None:
        """يعيد فحص الحالة (بعد تغيّر قاعدة خارجية — مثل تاريخ مرتبط)."""
        self._apply_state()

    # ----------------------- إدخال المستخدم -----------------------
    def _on_text_edited(self, _txt: str) -> None:
        le = self._edit
        raw = le.text()
        pos = le.cursorPosition()
        digits_before = len(re.sub(r"\D", "", raw[:pos]))
        new = self._format_digits(raw)
        if new != raw:
            le.blockSignals(True)
            le.setText(new)
            le.blockSignals(False)
            if digits_before <= 0:
                le.setCursorPosition(0)
            else:
                cnt, npos = 0, len(new)
                for i, ch in enumerate(new):
                    if ch.isdigit():
                        cnt += 1
                        if cnt == digits_before:
                            npos = i + 1
                            break
                le.setCursorPosition(min(npos, len(new)))
        self.dateChanged.emit(self.date())
        self._apply_state()

    def eventFilter(self, obj, ev):                       # noqa: N802 (Qt)
        if obj is self._edit and ev.type() == QEvent.KeyPress:
            key = ev.key()
            if key == Qt.Key_Tab and not (ev.modifiers() & Qt.ShiftModifier):
                st, _msg = self._compute_state()
                if st in (self.INCOMPLETE, self.ERROR):
                    self._apply_state()
                    return True                          # لا انتقال
                return False
            if (key == Qt.Key_Backspace and not self._edit.hasSelectedText()):
                p = self._edit.cursorPosition()
                txt = self._edit.text()
                if p > 0 and not txt[p - 1].isdigit():
                    self._edit.backspace()               # الفاصل
                    self._edit.backspace()               # الرقم قبله
                    self._on_text_edited("")
                    return True
        return super().eventFilter(obj, ev)

    def _try_paste(self, txt: str) -> bool:
        if not txt:
            return False
        for f in (_PASTE_DATE if self._kind == "date" else _PASTE_MONTH):
            try:
                self._set_from_pydate(_pydatetime.strptime(txt, f).date())
                return True
            except ValueError:
                pass
        digs = re.sub(r"\D", "", txt)
        if len(digs) == self._total_digits:
            vals, i = {}, 0
            for name, w in self._segs:
                vals[name] = int(digs[i:i + w])
                i += w
            try:
                self._set_from_pydate(_pydate(vals.get("y", 1), vals.get("m", 1),
                                              vals.get("d", 1)))
                return True
            except ValueError:
                return False
        return False

    # ----------------------- التقويم -----------------------
    def _open_calendar(self) -> None:
        if self._cal_popup is None:
            pop = QFrame(self, Qt.Popup)
            pop.setFrameShape(QFrame.StyledPanel)
            lay = QVBoxLayout(pop)
            lay.setContentsMargins(4, 4, 4, 4)
            lay.setSpacing(4)
            cal = QCalendarWidget(pop)
            cal.setGridVisible(True)
            cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
            cal.setLayoutDirection(Qt.LeftToRight)
            if self._min is not None:
                cal.setMinimumDate(QDate(self._min.year, self._min.month,
                                         self._min.day))
            if self._max is not None:
                cal.setMaximumDate(QDate(self._max.year, self._max.month,
                                         self._max.day))
            cal.clicked.connect(lambda qd: self._pick_calendar(qd))
            today = QPushButton("اليوم", pop)
            today.clicked.connect(
                lambda: self._pick_calendar(QDate.currentDate()))
            lay.addWidget(cal)
            lay.addWidget(today)
            self._cal_popup, self._cal_widget = pop, cal
        cur = self.date()
        self._cal_widget.setSelectedDate(
            cur if cur.isValid() else QDate.currentDate())
        gp = self._edit.mapToGlobal(self._edit.rect().bottomLeft())
        self._cal_popup.move(gp)
        self._cal_popup.show()

    def _pick_calendar(self, qd: QDate) -> None:
        if self._cal_popup is not None:
            self._cal_popup.hide()
        self._set_from_pydate(self._to_pydate(qd))
        self._edit.setFocus()

    # ----------------------- القراءة/الكتابة البرمجية -----------------------
    def _set_from_pydate(self, d, *, silent: bool = False) -> None:
        self._edit.blockSignals(True)
        if d is None:
            self._edit.clear()
        else:
            digits = ""
            for name, _w in self._segs:
                digits += (f"{d.year:04d}" if name == "y"
                           else f"{d.month:02d}" if name == "m"
                           else f"{d.day:02d}")
            self._edit.setText(self._format_digits(digits))
        self._edit.blockSignals(False)
        self._apply_state(silent=silent)
        if not silent:
            self.dateChanged.emit(self.date())

    def date(self) -> QDate:
        st, _msg = self._compute_state()
        if st == self.VALID:
            d, _c = self._parsed()
            return QDate(d.year, d.month, d.day)
        return QDate()

    def iso(self) -> str:
        st, _msg = self._compute_state()
        if st != self.VALID:
            return ""
        d, _c = self._parsed()
        return d.strftime(self._iso_fmt())

    def set_iso(self, value) -> None:
        s = str(value or "").strip()
        d = None
        if s:
            try:
                d = _pydatetime.strptime(s, self._iso_fmt()).date()
            except ValueError:
                d = None
        self._set_from_pydate(d)

    def set_extra_check(self, fn: Optional[Callable[[_pydate], Optional[str]]]
                        ) -> None:
        """قاعدة تحقّق إضافية: ``fn(pydate) -> رسالة خطأ | None``."""
        self._extra_check = fn
        self._apply_state()

    def error_text(self) -> str:
        return self._error

    def state(self) -> str:
        return self._state

    # ----------------------- ملاءمة الواجهة القديمة (QDateEdit) -----------------------
    def setDate(self, qd) -> None:                        # noqa: N802 (Qt)
        self._set_from_pydate(self._to_pydate(qd))

    def minimumDate(self) -> QDate:                       # noqa: N802 (Qt)
        return (QDate(self._min.year, self._min.month, self._min.day)
                if self._min is not None else QDate())

    def setMinimumDate(self, qd) -> None:                 # noqa: N802 (Qt)
        self._min = self._to_pydate(qd)
        self._apply_state()

    def maximumDate(self) -> QDate:                       # noqa: N802 (Qt)
        return (QDate(self._max.year, self._max.month, self._max.day)
                if self._max is not None else QDate())

    def setMaximumDate(self, qd) -> None:                 # noqa: N802 (Qt)
        self._max = self._to_pydate(qd)
        self._apply_state()

    def setFont(self, f) -> None:                         # noqa: N802 (Qt)
        super().setFont(f)
        self._edit.setFont(f)

    def text(self) -> str:
        return self._edit.text()

    def selectAll(self) -> None:                          # noqa: N802 (Qt)
        self._edit.selectAll()

    def setReadOnly(self, ro: bool) -> None:              # noqa: N802 (Qt)
        self._edit.setReadOnly(ro)
        self._btn.setEnabled(not ro)


_DateEdit = DateField                                     # توافق خلفي


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
