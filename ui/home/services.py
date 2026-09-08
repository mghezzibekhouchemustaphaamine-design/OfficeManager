"""تعريف الخدمات الظاهرة في OfficeManager.

الفكرة: النافذة الرئيسية لا تعرف تفاصيل كل خدمة؛ تعرف فقط كيف تعرض
الخدمات المسجلة هنا وتستدعي دالة فتحها. إضافة خدمة مستقبلًا تصبح عملية
محدودة بدل تعديل منطق النافذة بالكامل.
"""
from dataclasses import dataclass
from typing import Callable, Any

# شاشة كشف الراتب الجديدة (PySide6، حزمة ui2/) — تُطلَق كعملية منفصلة
# (راجع OfficeApp.open_paie_v2). علم واحد لإخفائها بسرعة إن لزم — نفس نمط
# SHOW_ADMIN_SCREENS في demos/ui2_paie_gallery.py.
SHOW_PAIE_V2 = True


@dataclass(frozen=True)
class ServiceDefinition:
    key: str
    title: str
    description: str
    open_handler: Callable[[Any], None]
    icon: str = ""
    enabled: bool = True


def build_services(app):
    """يرجع الخدمات المتاحة حاليًا بالترتيب المعروض في الصفحة الرئيسية.

    النسخ الاحتياطي مو "خدمة" هنا (تُفتح بس من جوا شاشة الإعدادات —
    راجع ui/settings_screen.py وapp.open_backup/return_to_settings)."""
    return [
        ServiceDefinition(
            key="cd",
            title="CD",
            description="إنشاء وإدارة مستندات Change Devise",
            open_handler=lambda owner: owner.open_cd(),
            icon="💱",
        ),
        ServiceDefinition(
            key="hr_attestation_travail",
            title="شهادة عمل",
            description="توليد شهادة عمل لأجير (Attestation de travail)",
            open_handler=lambda owner: owner.open_hr("hr_attestation_travail"),
            icon="📄",
        ),
        ServiceDefinition(
            key="hr_titre_conge",
            title="شهادة عطلة",
            description="توليد شهادة عطلة (Titre de congé)",
            open_handler=lambda owner: owner.open_hr("hr_titre_conge"),
            icon="🏖️",
        ),
        ServiceDefinition(
            key="hr_bulletin_paie",
            title="كشف راتب شهري",
            description="توليد كشف الراتب الشهري مع حساب IRG (Bulletin de paie)",
            open_handler=lambda owner: owner.open_hr("hr_bulletin_paie"),
            icon="💵",
        ),
        ServiceDefinition(
            key="hr_releve_annuel",
            title="كشف راتب سنوي",
            description="توليد كشف الراتب السنوي (Relevé annuel des émoluments)",
            open_handler=lambda owner: owner.open_hr("hr_releve_annuel"),
            icon="📊",
        ),
        *([ServiceDefinition(
            key="paie_v2",
            title="كشف راتب (PySide6)",
            description="شاشة توليد الكشف الجديدة — تُفتح في نافذة مستقلّة",
            open_handler=lambda owner: owner.open_paie_v2(),
            icon="🧾",
        )] if SHOW_PAIE_V2 else []),
    ]
