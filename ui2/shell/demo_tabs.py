"""Demo Works — تحقّق بصريّ يمرّ عبر WorkspaceManager الحقيقيّ (P1 §11).

**لم تعُد آليّةً موازية:** كل عملٍ هنا ``WorkSession`` حقيقية تُفتَح عبر
``WorkspaceManager.open_work()`` — **نفس الأنبوب بالضبط** الذي ستستعمله
Paie/CD/Attestation الحقيقية لاحقاً. الفرق الوحيد محتوى Placeholder
بسيط (``DemoWorkContent``) بدل شاشة خدمةٍ فعلية؛ لا Work lifecycle
إضافي، لا كتابة قاعدة بيانات، لا Service Contract.

تُفعَّل فقط عبر:
    python -m ui2.shell --demo-tabs
"""
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui2 import theme
from ui2.shell.work import WorkKey, WorkSession


class DemoWorkContent(QWidget):
    """محتوى Placeholder بسيط جداً — ودجت **مستقلّة لكلّ عمل** (لا
    مشتركة) لإثبات أنّ ContentStack يعرض widget كلّ WorkSession بذاتها
    (P1 §6)."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(
            theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"], theme.SPACE["lg"]
        )
        label = QLabel(f"معاينة تجريبية — {title}")
        label.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['title']}px; font-weight: 600;"
            f" color: {theme.TEXT_DIM};"
        )
        label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        lay.addWidget(label)
        lay.addStretch(1)


@dataclass(frozen=True)
class DemoWorkSpec:
    key: WorkKey
    title: str
    dirty: bool = False
    locked: bool = False


#  ثلاثة أعمالٍ تجريبية — مفاتيح مختلفة الخدمة، تغطّي الحالات الثلاث
#  المطلوبة للتقييم البصري (dirty/locked/عاديّ).
DEMO_WORK_SPECS = (
    DemoWorkSpec(WorkKey("paie", "demo-bulletin"), "Bulletin Ahmed", dirty=True),
    DemoWorkSpec(WorkKey("cd", "demo-1584"), "CD 1584", locked=True),
    DemoWorkSpec(WorkKey("attestation", "demo-nadia"), "Attestation Nadia"),
)


def build_demo_session(spec: DemoWorkSpec) -> WorkSession:
    """يبني ``WorkSession`` حقيقية من مواصفة Demo — لا يُضيفها لِـQTabBar
    مباشرةً (ذلك عمل ``WorkspaceManager.open_work`` وحده، P1 §11)."""
    widget = DemoWorkContent(spec.title)
    return WorkSession(spec.key, spec.title, widget,
                       dirty=spec.dirty, locked=spec.locked)
