"""Unsaved Changes Dialogs — الواجهة المرئية الوحيدة لقرار الإغلاق
غير المحفوظ (P2.5 §5). ``WorkSession``/``WorkspaceManager`` لا يعرضان
أيّ ``QMessageBox`` بأنفسهما (§1/§7) — هذا الملف وحده يفعل ذلك، ويُستدعى
حصراً من ``CloseCoordinator`` (كـ``decision_provider``/
``multi_decision_provider`` افتراضيَّين، قابلَين للاستبدال في الاختبارات
— P2.5 §21).

قاعدة أمان ثابتة في كلا الحوارين: **Cancel هو المسار الآمن** — الزرّ
الافتراضي، ``Escape``، وإغلاق النافذة بـ×، كلّها تُعيد ``CANCEL``. لا
يوجد مسارٌ يُفسَّر افتراضياً بأنه Discard."""
from typing import List, Sequence

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout

from ui2.shell.close_types import CloseDecision, MultiCloseDecision


def build_single_close_dialog(parent, session):
    """يبني ``QMessageBox`` الحوار أحاديّ العمل **بلا تنفيذه** — مفصولٌ
    عن ``ask_single_close_decision`` عمداً (P2.5 §21) كي تستطيع
    الاختبارات فحص بنيته (``defaultButton``/``escapeButton``/ظهور زرّ
    Save) دون حلقة Modal حقيقية. يُرجع ``(box, save_btn_or_None,
    discard_btn, cancel_btn)``."""
    box = QMessageBox(parent)
    box.setWindowTitle("تغييرات غير محفوظة")
    box.setIcon(QMessageBox.Warning)
    box.setText(f"العمل «{session.title}» يحتوي تغييرات غير محفوظة.")
    box.setInformativeText("هل تريد حفظ التغييرات قبل الإغلاق؟")

    #  ‏Save لا تظهر إطلاقاً إن كانت session.can_save() == False (P2.5
    #  §14: لا زرّ سينتهي دائماً بالفشل لأنه غير مدعوم).
    save_btn = None
    if session.can_save():
        save_btn = box.addButton("حفظ", QMessageBox.AcceptRole)
    discard_btn = box.addButton("تجاهل", QMessageBox.DestructiveRole)
    cancel_btn = box.addButton("إلغاء", QMessageBox.RejectRole)

    #  ‏Cancel هو المسار الآمن دائماً: الزرّ الافتراضي (Enter) وEscape
    #  وإغلاق × (Qt يعامل × كـEscape لِـQMessageBox) كلّها تُفضي إليه.
    box.setDefaultButton(cancel_btn)
    box.setEscapeButton(cancel_btn)
    return box, save_btn, discard_btn, cancel_btn


def ask_single_close_decision(parent, session) -> CloseDecision:
    """عملٌ واحدٌ dirty — اسمه + رسالة + Save/Discard/Cancel."""
    box, save_btn, discard_btn, cancel_btn = build_single_close_dialog(parent, session)
    box.exec()
    clicked = box.clickedButton()
    if save_btn is not None and clicked is save_btn:
        return CloseDecision.SAVE
    if clicked is discard_btn:
        return CloseDecision.DISCARD
    return CloseDecision.CANCEL


def build_multi_close_dialog(parent, sessions: Sequence):
    """يبني حوار الإغلاق الجماعيّ **بلا تنفيذه** (P2.5 §21) — بسيطٌ عمداً
    (لا تحديدٍ جزئيّ/checkboxes، "لا تبنِ نظاماً ضخماً"). يُرجع
    ``(dlg, decision_box, btn_save_all, btn_discard_all, btn_cancel)``
    — ``decision_box`` قائمةٌ من عنصرٍ واحد تُحدَّث عند الضغط، تبدأ
    ‏``CANCEL`` (المسار الآمن الافتراضي قبل أيّ تفاعل، وما يبقى عليه
    Escape/× أيضاً لأنّهما يستدعيان ``reject()`` بلا تغييرها)."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("أعمال غير محفوظة")
    lay = QVBoxLayout(dlg)

    lay.addWidget(QLabel(f"هناك {len(sessions)} عملاً يحتوي تغييرات غير محفوظة:"))
    for session in sessions:
        lay.addWidget(QLabel(f"• {session.title}"))

    buttons = QDialogButtonBox()
    btn_save_all = buttons.addButton("حفظ الكلّ", QDialogButtonBox.AcceptRole)
    btn_discard_all = buttons.addButton("تجاهل الكلّ", QDialogButtonBox.DestructiveRole)
    btn_cancel = buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
    lay.addWidget(buttons)

    decision: List[MultiCloseDecision] = [MultiCloseDecision.CANCEL]

    def _choose_save_all() -> None:
        decision[0] = MultiCloseDecision.SAVE_ALL
        dlg.accept()

    def _choose_discard_all() -> None:
        decision[0] = MultiCloseDecision.DISCARD_ALL
        dlg.accept()

    btn_save_all.clicked.connect(_choose_save_all)
    btn_discard_all.clicked.connect(_choose_discard_all)
    btn_cancel.clicked.connect(dlg.reject)
    return dlg, decision, btn_save_all, btn_discard_all, btn_cancel


def ask_multi_close_decision(parent, sessions: Sequence) -> MultiCloseDecision:
    """عدّة أعمالٍ dirty معاً (Close All/إغلاق التطبيق) — حوارٌ مجمّعٌ
    واحد بدل QMessageBox لكلّ عمل (P2.5 §9)."""
    dlg, decision, *_ = build_multi_close_dialog(parent, sessions)
    dlg.exec()
    return decision[0]
