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
from ui2.shell.close_types import SaveResult
from ui2.shell.commands import CommandId
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
    مباشرةً (ذلك عمل ``WorkspaceManager.open_work`` وحده، P1 §11).

    ‏P2 §9: تُعلن Commands حقيقية عبر النظام الجديد (``WorkSession.
    set_command``) — نفس الأنبوب الذي ستستعمله Paie/CD لاحقاً؛ الفرع
    حسب ``service_key`` هنا مقبولٌ لأنّه تعريف Demo بحت (لا داخل Shell
    نفسه — CommandManager/CommandBar لا يعرفان معنى أيّ خدمة، P2 §14)."""
    widget = DemoWorkContent(spec.title)
    session = WorkSession(spec.key, spec.title, widget,
                          dirty=spec.dirty, locked=spec.locked)
    _bind_demo_commands(session, spec)
    return session


def _demo_save_success(session: WorkSession) -> SaveResult:
    session.set_dirty(False)
    return SaveResult.SUCCESS


def _bind_demo_commands(session: WorkSession, spec: DemoWorkSpec) -> None:
    """‏P2 §9/§10 → P2.5 §15: Handlers تجريبية فقط — تُثبت أنّ التوجيه
    الحقيقيّ يعمل (QAction → CommandManager → Active Work → handler →
    state تتغيّر → CommandBar يُحدَّث) بلا أيّ منطق حفظ/طباعة/إصدار
    حقيقيّ. ``session.save`` (لا دالّة منفصلة) هي WorkCommandBinding
    الخاصّ بـSAVE — نفس العملية بالضبط التي يستدعيها CloseCoordinator
    عند إغلاق عملٍ dirty (P2.5 §15: لا save_handler_A للزرّ وsave_
    handler_B للإغلاق)."""

    if spec.key.service_key == "paie":
        #  ‏Bulletin Ahmed: SAVE/PRINT/FINALIZE مدعومة ومفعَّلة (dirty
        #  يُطفئ نفسه بعد Save — إثباتٌ حيّ لكامل الأنبوب، P2 §10).
        session.set_save_handler(lambda: _demo_save_success(session), can_save=True)
        session.set_command(CommandId.SAVE, session.save, enabled=lambda: session.dirty)
        session.set_command(CommandId.PRINT, lambda: None, enabled=True)
        session.set_command(CommandId.FINALIZE, lambda: None, enabled=True)
    elif spec.key.service_key == "cd":
        #  ‏CD 1584: مقفلٌ — can_save=False طالما locked (P2.5 §14: لا
        #  زرّ Save سينتهي دائماً بالفشل لأنه غير مدعوم أصلاً؛ حوار
        #  الإغلاق يُخفيه تلقائياً عبر session.can_save()). UNDO/REDO
        #  مدعومة لكن معطَّلة (SUPPORTED BUT DISABLED)، PRINT مفعَّلة،
        #  FINALIZE غير مدعومة إطلاقاً.
        session.set_save_handler(
            lambda: _demo_save_success(session), can_save=lambda: not session.locked
        )
        session.set_command(
            CommandId.SAVE, session.save,
            enabled=lambda: session.dirty and session.can_save(),
        )
        session.set_command(CommandId.PRINT, lambda: None, enabled=True)
        session.set_command(CommandId.UNDO, lambda: None, enabled=False)
        session.set_command(CommandId.REDO, lambda: None, enabled=False)
    else:
        #  ‏Attestation Nadia: SAVE/PRINT فقط.
        session.set_save_handler(lambda: _demo_save_success(session), can_save=True)
        session.set_command(CommandId.SAVE, session.save, enabled=lambda: session.dirty)
        session.set_command(CommandId.PRINT, lambda: None, enabled=True)


def build_failing_demo_session() -> WorkSession:
    """‏P2.5 §16/§21: عملٌ تجريبيّ **لاختبارات الحفظ الفاشل فقط** — save
    يرجع دائماً ``SaveResult.FAILED``، لإثبات أنّ CloseCoordinator يُبقي
    العمل مفتوحاً ويُبلِّغ الخطأ بدل الإغلاق الصامت. غير مُستعمَل في أيّ
    مسار CLI عاديّ (لا يُفسِد demo المعتادة)."""
    key = WorkKey("demo-fail", "always-fails")
    widget = DemoWorkContent("Demo — حفظ فاشل دائماً")
    session = WorkSession(key, "Demo Fail", widget, dirty=True)
    session.set_save_handler(lambda: SaveResult.FAILED, can_save=True)
    session.set_command(CommandId.SAVE, session.save, enabled=lambda: session.dirty)
    return session


#  ‏P2.1 §15: عناوين قصيرة وطويلة متعمَّدة — تثبت العرض الموحَّد +
#  ellipsis + tooltip الكامل + overflow/scroll معاً في اختبارٍ واحد.
MANY_DEMO_TITLES = (
    "Bulletin Ahmed",
    "CD 1584",
    "Attestation Nadia",
    "Bulletin BENALI Karim OCTOBRE 2026",
    "CD 2201",
    "Attestation Yasmine — Description Longue Ville",
    "Bulletin X",
    "CD 9999 Dossier Complet Annuel",
    "Attestation K",
    "Bulletin Sara Mensuel",
    "CD 42",
    "Attestation — Titre Très Long Pour Tester Overflow",
    "Bulletin Z",
)


def build_many_demo_sessions(count: int = 13):
    """‏P2.1 §15: مولّد Demo Works للاختبار اليدويّ/الآليّ لِـoverflow —
    مفاتيحه منفصلة عن ``DEMO_WORK_SPECS`` (``service_key="demo-many"``)
    فلا تتصادم معها إن استُدعيا معاً. بلا Commands (خارج نطاق هذا
    الاختبار — التركيز هنا على عرض/تمرير التبويبات فقط)."""
    sessions = []
    for i in range(count):
        title = MANY_DEMO_TITLES[i % len(MANY_DEMO_TITLES)]
        key = WorkKey("demo-many", f"work-{i}")
        widget = DemoWorkContent(title)
        sessions.append(WorkSession(key, f"{title} #{i + 1}", widget))
    return sessions
