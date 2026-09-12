"""سجلّ خدمات Shell — Prototype فقط.

الفكرة كما في ``ui/home/services.py`` القديم: `HomeView` لا تعرف
تفاصيل أي خدمة؛ تُبنى بطاقاتها من هذه القائمة. إضافة خدمة جديدة لاحقاً
تصبح إضافة عنصر هنا، لا تعديل `HomeView` مباشرة.

معظم الخدمات لا تزال بلا ``open_handler`` حقيقي — بيانات وصفية فقط
لبناء البطاقة وService Start View. ``new_work_factory`` (P3 §6/§19) هو
الاستثناء الوحيد: دالّة بلا معاملات تُنشئ ``WorkSession`` جاهزة —
مسجَّلة عبر :func:`register_new_work_factory` من integration module
عند بدء التشغيل (مثلاً ``ui2.shell.integrations.paie``)، **لا** من هنا
ولا من ``WorkspaceHost`` — هذا الملف لا يستورد أيّ شيء من أيّ خدمة
حقيقية، فلا اعتماديّة دائرية."""
from dataclasses import dataclass
from typing import Callable, Dict, Optional

#  ‏key -> () -> WorkSession (النوع الفعليّ غير مستورَد هنا عمداً؛
#  Callable مجرّد يكفي ولا يُدخل أيّ اعتماديّة على ui2.shell.work).
_NEW_WORK_FACTORIES: Dict[str, Callable[[], object]] = {}


def register_new_work_factory(service_key: str, factory: Callable[[], object]) -> None:
    """يسجّل factory إنشاء Work حقيقية لخدمةٍ بعينها — يُستدعى مرّةً من
    integration module (مثل ``ui2.shell.integrations.paie.register()``)
    قبل إنشاء ``OfficeMainWindow`` الأولى، **لا** من ``services.py``
    نفسه ولا من ``WorkspaceHost`` (P3 §6/§19/§28: لا
    ``if service_key == "paie"`` متفرّقة في Shell core)."""
    _NEW_WORK_FACTORIES[service_key] = factory


@dataclass(frozen=True)
class ServiceDescriptor:
    key: str
    title: str
    description: str
    icon: str = ""
    enabled: bool = True
    #  ‏None = خدمة placeholder (Nouveau بلا أثر) — كل الخدمات عدا
    #  Bulletin de paie في P3 Phase 1 (P3 §20).
    new_work_factory: Optional[Callable[[], object]] = None


def default_services() -> list[ServiceDescriptor]:
    """قائمة الخدمات الافتراضية — نفس مفاتيح/تسميات ``ui/home/services.py``
    القديم حتى يبقى الاسم مألوفاً عند اعتماد Shell لاحقاً. ``new_work_
    factory`` يُقرأ من السجلّ المُحقَن خارجياً — غيابه (لم يُسجَّل أحد
    بعد) يترك الخدمة placeholder كما كانت بالضبط."""
    specs = [
        dict(key="cd", title="CD",
             description="إنشاء وإدارة مستندات Change Devise", icon="💱"),
        dict(key="hr_bulletin_paie", title="كشف راتب شهري",
             description="توليد كشف الراتب الشهري مع حساب IRG (Bulletin de paie)",
             icon="💵"),
        dict(key="hr_attestation_travail", title="شهادة عمل",
             description="توليد شهادة عمل لأجير (Attestation de travail)", icon="📄"),
        dict(key="hr_titre_conge", title="شهادة عطلة",
             description="توليد شهادة عطلة (Titre de congé)", icon="🏖️"),
        dict(key="hr_releve_annuel", title="كشف راتب سنوي",
             description="توليد كشف الراتب السنوي (Relevé annuel des émoluments)",
             icon="📊"),
    ]
    return [
        ServiceDescriptor(new_work_factory=_NEW_WORK_FACTORIES.get(s["key"]), **s)
        for s in specs
    ]
