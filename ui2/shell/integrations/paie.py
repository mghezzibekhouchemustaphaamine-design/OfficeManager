"""PaieWorkAdapter — الجسر الوحيد بين Shell وBulletinTemplateScreen
(P3 §3). يعرف الطرفين معاً؛ لا Shell import داخل
``ui2/hr/paie/bulletin_template.py`` (P3 §2/§28)، ولا معرفة لهذا الملف
بتفاصيل CommandManager/WorkspaceManager الداخلية أبعد من العقد العامّ
(‏``WorkSession.set_save_handler``/``set_command``).

**نطاق P3 Phase 1** (موثَّقٌ صراحةً — راجع التقرير النهائي لتفاصيل كلّ
قرار):
- SAVE: مربوطة بـ``BulletinTemplateScreen._on_save()`` الحقيقية عبر
  ``WorkSession.save()`` — نفس المسار لِـCtrl+S/CommandBar/Safe Close.
- PRINT: مربوطة بـ``_on_preview()`` الحقيقية (معاينة/فتح PDF/DOCX
  الموجود، أو رسالة "لا نسخة نهائية بعد") — إجراءٌ آمن، لا محتوى وهميّ.
- FINALIZE: **غير مربوطة عمداً** في Phase 1 (راجع التقرير — إجراءٌ
  معامليّ يُنتج ملفّات حقيقية ويتطلّب مراجعة UX حوارات منفصلة قبل
  ربطه بـCommand routing العامّ؛ الزرّ الأصليّ داخل الشاشة نفسها يبقى
  متاحاً كما هو، بلا تغيير).
- Locked (🔒): مربوطٌ عبر ``lockedChanged`` الحقيقية.
- Title: ثابتٌ "Bulletin de paie — Nouveau" — لا مزامنة مع اسم
  العامل/الشهر بعد (P3 §8: لا يوجد signal مناسب جاهز، وتفعيله يحتاج
  تصميم أوسع من نطاق Phase 1)."""
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
        session = WorkSession(key, "Bulletin de paie — Nouveau", screen)
        adapter = cls(screen, session)
        #  ‏مرجعٌ حيّ من الـwidget طويل العمر إلى الـAdapter — يمنع GC
        #  خارج أيّ اعتمادٍ ضمنيّ على آلية إبقاء PySide لملتقطات الإشارة.
        screen._work_adapter = adapter

        #  ‏P2.5 §15: نفس session.save بالضبط لِـSAVE — لا نسخة موازية.
        session.set_save_handler(adapter.save, can_save=adapter.can_save)
        session.set_command(CommandId.SAVE, session.save, enabled=lambda: session.dirty)
        #  ‏P3 §12: PRINT مربوطة بمعاينة حقيقية (تفتح PDF/DOCX الموجود
        #  أو تُخبر بعدم وجود نسخة نهائية بعد) — لا dummy.
        session.set_command(CommandId.PRINT, screen._on_preview, enabled=True)
        return session

    # ------------------------------------------------------------- الحفظ
    def can_save(self) -> bool:
        """عملٌ 🔒 لا يمكن حفظه (الشاشة نفسها ترفض وتُنبّه) — لا نعرض
        زرّ Save فعّالاً في حوار الإغلاق لسيناريوٍ سينتهي بالفشل حتماً
        (P2.5 §14)."""
        return not self.screen.locked

    def save(self) -> SaveResult:
        ok = self.screen._on_save()
        return SaveResult.SUCCESS if ok else SaveResult.FAILED

    # --------------------------------------------------------- مزامنة الحالة
    def _sync_dirty(self, value: bool) -> None:
        self.session.set_dirty(value)

    def _sync_locked(self, value: bool) -> None:
        self.session.set_locked(value)


def register() -> None:
    """يُستدعى مرّةً من نقطة الدخول قبل إنشاء ``OfficeMainWindow``
    الأولى (P3 §19) — بعدها فقط ``ServiceStartView`` لخدمة «كشف راتب
    شهري» تملك Nouveau حقيقياً."""
    register_new_work_factory(SERVICE_KEY, PaieWorkAdapter.create_new)
