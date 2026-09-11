"""سجلّ خدمات Shell — Prototype فقط.

الفكرة كما في ``ui/home/services.py`` القديم: `HomeView` لا تعرف
تفاصيل أي خدمة؛ تُبنى بطاقاتها من هذه القائمة. إضافة خدمة جديدة لاحقاً
تصبح إضافة عنصر هنا، لا تعديل `HomeView` مباشرة.

هذا Prototype لا يربط أي ``open_handler`` حقيقي — فقط البيانات الوصفية
اللازمة لبناء البطاقة و Service Start View.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceDescriptor:
    key: str
    title: str
    description: str
    icon: str = ""
    enabled: bool = True


def default_services() -> list[ServiceDescriptor]:
    """قائمة الخدمات الافتراضية — نفس مفاتيح/تسميات ``ui/home/services.py``
    القديم حتى يبقى الاسم مألوفاً عند اعتماد Shell لاحقاً."""
    return [
        ServiceDescriptor(
            key="cd",
            title="CD",
            description="إنشاء وإدارة مستندات Change Devise",
            icon="💱",
        ),
        ServiceDescriptor(
            key="hr_bulletin_paie",
            title="كشف راتب شهري",
            description="توليد كشف الراتب الشهري مع حساب IRG (Bulletin de paie)",
            icon="💵",
        ),
        ServiceDescriptor(
            key="hr_attestation_travail",
            title="شهادة عمل",
            description="توليد شهادة عمل لأجير (Attestation de travail)",
            icon="📄",
        ),
        ServiceDescriptor(
            key="hr_titre_conge",
            title="شهادة عطلة",
            description="توليد شهادة عطلة (Titre de congé)",
            icon="🏖️",
        ),
        ServiceDescriptor(
            key="hr_releve_annuel",
            title="كشف راتب سنوي",
            description="توليد كشف الراتب السنوي (Relevé annuel des émoluments)",
            icon="📊",
        ),
    ]
