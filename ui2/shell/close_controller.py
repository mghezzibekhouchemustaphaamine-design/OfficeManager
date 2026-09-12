"""CloseCoordinator — الطبقة الوحيدة المخوَّلة بإغلاق عملٍ مفتوح فعلياً
من الواجهة (P2.5 §7/§18).

    UI close requests (Tab ×, يمين-كليك, All Open Works, إغلاق التطبيق)
                    ↓
              CloseCoordinator
                    ↓
          قرار (Dialog أو مُحقَن في الاختبارات) + save()
                    ↓
          WorkspaceManager.close_work()/close_all() (primitive داخليّ)

``WorkspaceManager`` يبقى model/lifecycle manager بحتاً — لا يعرض أيّ
UI (P2.5 §7). ``WorkSession`` لا تعرض أيّ MessageBox بنفسها (§1) — فقط
``dirty``/``can_save()``/``save()``/``can_close``. **ممنوعٌ** أن تستدعي
أيّ واجهة (WorkTabBar/WorkspaceHost) ‏``workspace_manager.close_work``/
``close_others``/``close_all`` مباشرةً — المرور عبر هذا الصنف إلزاميّ
لكلّ مسارات الإغلاق (§18)؛ الاستثناء الوحيد هو ``CloseCoordinator``
نفسه الذي يستدعي تلك الدوال بعد اتخاذ القرار.

**قابليّة الاختبار (§21)**: ``decision_provider``/``multi_decision_
provider`` قابلان للحقن — الإنتاج يستعمل ``unsaved_dialog`` (Dialog
حقيقي)، الاختبارات تمرّر دالّةً تُرجع ``CloseDecision``/
``MultiCloseDecision`` مباشرةً بلا أيّ UI فعليّ."""
from typing import Callable, List, Optional

from ui2.shell.close_types import CloseDecision, MultiCloseDecision, SaveResult
from ui2.shell.work import WorkKey, WorkSession
from ui2.shell.workspace_manager import WorkspaceManager


class CloseCoordinator:

    def __init__(self, workspace_manager: WorkspaceManager, parent=None, *,
                 decision_provider: Optional[Callable[[WorkSession], CloseDecision]] = None,
                 multi_decision_provider: Optional[
                     Callable[[List[WorkSession]], MultiCloseDecision]] = None,
                 error_reporter: Optional[Callable[[WorkSession], None]] = None):
        self._mgr = workspace_manager
        self._parent = parent
        self._decision_provider = decision_provider or self._default_single_provider
        self._multi_decision_provider = multi_decision_provider or self._default_multi_provider
        self._error_reporter = error_reporter or self._default_error_reporter

    # -------------------------------------------------- افتراضيّات الإنتاج
    def _default_single_provider(self, session: WorkSession) -> CloseDecision:
        from ui2.shell.unsaved_dialog import ask_single_close_decision
        return ask_single_close_decision(self._parent, session)

    def _default_multi_provider(self, sessions: List[WorkSession]) -> MultiCloseDecision:
        from ui2.shell.unsaved_dialog import ask_multi_close_decision
        return ask_multi_close_decision(self._parent, sessions)

    def _default_error_reporter(self, session: WorkSession) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(
            self._parent, "فشل الحفظ", f"تعذّر حفظ «{session.title}».",
        )

    # ------------------------------------------------------------- الحفظ
    def _safe_save(self, session: WorkSession) -> SaveResult:
        """طبقة أمانٍ إضافية فوق ``WorkSession.save()`` (التي تمسك
        استثناءاتها هي أيضاً، P2.5 §3) — دفاعٌ مضاعَف لا اعتماد وحيد.
        ``FAILED`` يُبلَّغ عبر ``error_reporter`` (Dialog/alert، لا
        اعتماداً على status bar فقط — P2.5 §17)."""
        try:
            result = session.save()
        except Exception:
            result = SaveResult.FAILED
        if result == SaveResult.FAILED:
            self._error_reporter(session)
        return result

    # -------------------------------------------------------- عملٌ واحد
    def request_close_work(self, key: WorkKey) -> bool:
        """المسار الوحيد المسموح لإغلاق عملٍ واحد (P2.5 §6). يُرجع
        ``True`` إن أُغلق العمل فعلياً."""
        session = self._mgr.get(key)
        if session is None:
            return False
        if not session.dirty:
            return self._mgr.close_work(key)   # يحترم can_close veto داخلياً

        decision = self._decision_provider(session)
        if decision == CloseDecision.DISCARD:
            return self._mgr.close_work(key)
        if decision == CloseDecision.SAVE:
            if self._safe_save(session) == SaveResult.SUCCESS:
                return self._mgr.close_work(key)
            return False
        return False   # CANCEL

    # ----------------------------------------------------- Close Others
    def request_close_others(self, keep_key: WorkKey) -> bool:
        """‏P2.5 §8 — قرارٌ صريح: كلّ عملٍ آخر يُعالَج تباعاً بنفس مسار
        الإغلاق أحاديّ العمل (لا Dialog جماعي هنا) — الأبسط والأأمن لهذه
        المرحلة. يتوقّف فوراً عند أوّل عملٍ لا يُغلَق (Cancel، Save فشل/
        أُلغي، أو veto ``can_close``)؛ الأعمال المُغلَقة قبل تلك اللحظة
        تبقى مُغلَقة (semantics تسلسلية، بلا Rollback)."""
        targets = [s.key for s in self._mgr.open_works() if s.key != keep_key]
        for key in targets:
            if not self.request_close_work(key):
                return False
        return True

    # ------------------------------------------------------- Close All
    def request_close_all(self) -> bool:
        return self._close_many(self._mgr.open_works())

    def request_app_close(self) -> bool:
        """نفس منطق Close All بالضبط — حوارٌ مجمّعٌ واحد، لا سلسلة
        نوافذ لكلّ Tab عند إغلاق التطبيق (P2.5 §12)."""
        return self._close_many(self._mgr.open_works())

    def _close_many(self, works: List[WorkSession]) -> bool:
        dirty = [s for s in works if s.dirty]
        if not dirty:
            self._mgr.close_all()
            return True

        decision = self._multi_decision_provider(dirty)
        if decision == MultiCloseDecision.CANCEL:
            return False
        if decision == MultiCloseDecision.DISCARD_ALL:
            self._mgr.close_all()
            return True
        if decision == MultiCloseDecision.SAVE_ALL:
            #  ‏P2.5 §10: بترتيب open_works الحاليّ؛ أوّل فشل/إلغاء يوقف
            #  العملية بالكامل — لا إغلاق لأيّ عمل، ولا Rollback للأعمال
            #  التي نجح حفظها فعلاً قبل التوقّف (تبقى dirty=False، طبيعيّ).
            for session in works:
                if session.dirty:
                    if self._safe_save(session) != SaveResult.SUCCESS:
                        return False
            self._mgr.close_all()
            return True
        return False
