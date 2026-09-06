"""حوار موحّد: عنوان، محتوى، أزرار حفظ/إلغاء، وتحقّق من الإدخال قبل
القبول."""
from typing import Callable, List, Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QMessageBox, QVBoxLayout, QWidget,
)

from ui2.form import Field, Form


class Dialog(QDialog):
    """حوار عام: ضع محتواك بـ:meth:`set_content`، وزوّد ``validator``
    اختيارياً يرجّع قائمة أخطاء (فارغة = يُقبَل)."""

    def __init__(self, title: str, parent=None, *,
                 save_text="حفظ", cancel_text="إلغاء"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._validator: Optional[Callable[[], List[str]]] = None

        self._buttons = QDialogButtonBox()
        self._save_btn = self._buttons.addButton(save_text, QDialogButtonBox.AcceptRole)
        self._save_btn.setDefault(True)
        self._buttons.addButton(cancel_text, QDialogButtonBox.RejectRole)
        self._buttons.accepted.connect(self._try_accept)
        self._buttons.rejected.connect(self.reject)

        self._lay = QVBoxLayout(self)

    def set_content(self, widget: QWidget):
        self._lay.addWidget(widget)
        self._lay.addWidget(self._buttons)

    def set_validator(self, fn: Callable[[], List[str]]):
        self._validator = fn

    def _try_accept(self):
        errs = self._validator() if self._validator is not None else []
        if errs:
            QMessageBox.warning(
                self, self.windowTitle(),
                "\n".join("• " + e for e in errs),
            )
            return
        self.accept()


class FormDialog(Dialog):
    """حوار جاهز حول :class:`ui2.form.Form`: يبني النموذج، يربط تحقّقه،
    ويكشف :meth:`values`."""

    def __init__(self, title: str, fields: List[Field], parent=None, values=None):
        super().__init__(title, parent)
        self.form = Form(fields, self)
        if values:
            self.form.set_values(values)
        self.set_content(self.form)
        self.set_validator(self.form.errors)

    def values(self):
        return self.form.values()
