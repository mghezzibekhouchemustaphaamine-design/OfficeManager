"""PaieWorkAdapter — الجسر الوحيد بين Shell وBulletinTemplateScreen
(P3 §3). يعرف الطرفين معاً؛ لا Shell import داخل
``ui2/hr/paie/bulletin_template.py`` (P3 §2/§28)، ولا معرفة لهذا الملف
بتفاصيل CommandManager/WorkspaceManager الداخلية أبعد من العقد العامّ
(‏``WorkSession.set_save_handler``/``set_command``/``set_lifecycle_
handlers``).

**نطاق P3.2** (يكمل P3 Phase 1 — راجع التقرير النهائي لتفاصيل كلّ قرار):
- SAVE: كما في P3 — ``BulletinTemplateScreen._on_save()`` عبر
  ``WorkSession.save()``.
- FINALIZE: مربوطة الآن — ``_on_finalize()`` عادت ``bool`` (P3.2 §12،
  تعديلٌ صغير في bulletin_template.py) فبنينا SaveResult بدقّة.
  ‏enabled = ``not screen.locked`` فقط؛ لا قاعدة payroll في
  CommandManager (P3.2 §13) — عدم اكتمال البيانات يُعالَج داخل
  ``_on_finalize`` نفسها (حوارها الحالي، بلا تكراره هنا).
- PRINT: كما في P3 — لا تزال Preview فعلياً (راجع commands.py: تلميح
  Registry العامّ عُدِّل إلى "معاينة / طباعة" بدل الادّعاء بطباعة
  حقيقية — P3.2 §17 خيار A: لا CommandId جديد).
- Locked/Dirty: مزامنةٌ حقيقية كما في P3.
- Title: ديناميكيّ الآن عبر ``BulletinTemplateScreen.titleChanged``
  (إشارة صغيرة أُضيفت هناك، P3.2 §5) — الـAdapter لا يبني العنوان بنفسه
  (Shell/Adapter ممنوعان من قراءة حقول Paie مباشرةً، P3.2 §4)؛ Paie
  وحدها (``display_title()``) تعرف صيغته.
- Lifecycle: ``screen.on_activate``/``on_deactivate`` (الموجودتان أصلاً
  في ``ui2.screen.Screen``) مربوطتان مباشرةً — لا كود جديد داخل Paie.
- Document identity: ``session.document_id``/``document_path`` تُملأان
  من ``screen._work_id``/``_final_pdf``/``_final_docx`` بعد save/
  finalize **ناجحين فقط** (P3.2 §8/§9) — ``WorkKey`` لا تتأثّر إطلاقاً."""
import uuid

from programme.database import get_connection
from programme.paths import ensure_user_data_migrated
from ui2.hr.paie.bulletin_template import BulletinTemplateScreen
from ui2.shell.close_types import SaveResult
from ui2.shell.commands import CommandId
from ui2.shell.services import register_new_work_factory
from ui2.shell.work import WorkKey, WorkSession

SERVICE_KEY = "hr_bulletin_paie"


class PaieWorkAdapter:
    """يغلّف ``BulletinTemplateScreen`` واحدة بعقد ``WorkSession``.
    Shell تتعامل مع ``session`` فقط؛ لا تصل أبداً إلى ``screen``
    مباشرةً — كل تزاوجٍ يمرّ من هنا."""

    def __init__(self, screen: BulletinTemplateScreen, session: WorkSession):
        self.screen = screen
        self.session = session
        screen.dirtyChanged.connect(self._sync_dirty)
        screen.lockedChanged.connect(self._sync_locked)
        screen.titleChanged.connect(session.set_title)

    @classmethod
    def create_new(cls) -> WorkSession:
        """‏P3 §7: ``WorkKey`` بمعرّفٍ مؤقّت (uuid4 — لا اعتماد على
        عنوان/DB بعد؛ يمكن ربطه لاحقاً بمعرّف hr_documents الحقيقي عند
        أوّل حفظ). نفس إعداد الاتصال الذي يستعمله launcher المستقلّ
        (``ui2/hr/paie/__main__.py``: ``ensure_user_data_migrated`` +
        ``get_connection``) — لا نسخة موازية من منطق التخزين."""
        ensure_user_data_migrated()
        conn = get_connection()
        screen = BulletinTemplateScreen(conn=conn)

        key = WorkKey(SERVICE_KEY, uuid.uuid4().hex)
        #  ‏P3.2 §6: نفس Fallback الذي تُرجعه display_title() لعملٍ فارغ
        #  — عنوانٌ ابتدائيّ متّسق، سيُستبدَل فوراً عبر titleChanged عند
        #  أوّل كتابة اسم/فترة.
        session = WorkSession(key, screen.display_title(), screen)
        adapter = cls(screen, session)
        #  ‏مرجعٌ حيّ من الـwidget طويل العمر إلى الـAdapter — يمنع GC
        #  خارج أيّ اعتمادٍ ضمنيّ على آلية إبقاء PySide لملتقطات الإشارة.
        screen._work_adapter = adapter

        #  ‏P3.2 §2/§19: دورة حياة عامّة — screen.on_activate/on_deactivate
        #  موجودتان أصلاً في Screen (تسجيل/إلغاء اختصارات + flush_draft)؛
        #  لا كود Paie جديد لهذا البند إطلاقاً.
        session.set_lifecycle_handlers(
            on_activate=screen.on_activate, on_deactivate=screen.on_deactivate)

        #  ‏P2.5 §15: نفس session.save بالضبط لِـSAVE — لا نسخة موازية.
        session.set_save_handler(adapter.save, can_save=adapter.can_save)
        session.set_command(CommandId.SAVE, session.save, enabled=lambda: session.dirty)
        #  ‏P3 §12: PRINT مربوطة بمعاينة حقيقية (تفتح PDF/DOCX الموجود
        #  أو تُخبر بعدم وجود نسخة نهائية بعد) — لا dummy.
        session.set_command(CommandId.PRINT, screen._on_preview, enabled=True)
        #  ‏P3.2 §13: FINALIZE — enabled فقط "غير مقفلة أصلاً"؛ نقص
        #  البيانات يُعالَج داخل _on_finalize نفسها (حوارها الحالي).
        session.set_command(
            CommandId.FINALIZE, adapter.finalize, enabled=lambda: not screen.locked)
        return session

    # ------------------------------------------------------------- الحفظ
    def can_save(self) -> bool:
        """عملٌ 🔒 لا يمكن حفظه (الشاشة نفسها ترفض وتُنبّه) — لا نعرض
        زرّ Save فعّالاً في حوار الإغلاق لسيناريوٍ سينتهي بالفشل حتماً
        (P2.5 §14)."""
        return not self.screen.locked

    def save(self) -> SaveResult:
        ok = self.screen._on_save()
        if ok:
            self._sync_document_identity()
            return SaveResult.SUCCESS
        return SaveResult.FAILED

    # ----------------------------------------------------------- الإصدار
    def finalize(self) -> SaveResult:
        """‏P3.2 §14: تستدعي منطق Finalize الحقيقيّ في Paie فقط — لا
        Save منفصلة من Shell قبلها (``_on_finalize`` تعيد الحساب
        وتبني من القيم الحالية مباشرةً). عند النجاح: lockedChanged/
        dirtyChanged الحقيقيّتان تصلان WorkSession تلقائياً (عبر
        الإشارات المربوطة في ``__init__``)، ونُزامن هوية الوثيقة."""
        ok = self.screen._on_finalize()
        if ok:
            self._sync_document_identity()
            return SaveResult.SUCCESS
        return SaveResult.FAILED

    # --------------------------------------------------------- مزامنة الحالة
    def _sync_dirty(self, value: bool) -> None:
        self.session.set_dirty(value)

    def _sync_locked(self, value: bool) -> None:
        self.session.set_locked(value)

    def _sync_document_identity(self) -> None:
        """‏P3.2 §8/§9: تُستدعى فقط بعد save/finalize **ناجحين** — لا
        نخمّن هويّة وثيقة من عمليةٍ فاشلة/مُلغاة. ``WorkKey`` لا تتأثّر
        إطلاقاً (تبقى ثابتة طوال عمر الجلسة، P3.2 §7)."""
        self.session.document_id = self.screen._work_id
        self.session.document_path = self.screen._final_pdf or self.screen._final_docx


def register() -> None:
    """يُستدعى مرّةً من نقطة الدخول قبل إنشاء ``OfficeMainWindow``
    الأولى (P3 §19) — بعدها فقط ``ServiceStartView`` لخدمة «كشف راتب
    شهري» تملك Nouveau حقيقياً."""
    register_new_work_factory(SERVICE_KEY, PaieWorkAdapter.create_new)
