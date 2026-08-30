"""تعريف الخدمات الظاهرة في OfficeManager.

الفكرة: النافذة الرئيسية لا تعرف تفاصيل كل خدمة؛ تعرف فقط كيف تعرض
الخدمات المسجلة هنا وتستدعي دالة فتحها. إضافة خدمة مستقبلًا تصبح عملية
محدودة بدل تعديل منطق النافذة بالكامل.
"""
from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class ServiceDefinition:
    key: str
    title: str
    description: str
    open_handler: Callable[[Any], None]
    icon: str = ""
    enabled: bool = True


def build_services(app):
    """يرجع الخدمات المتاحة حاليًا بالترتيب المعروض في الصفحة الرئيسية."""
    return [
        ServiceDefinition(
            key="cd",
            title="CD",
            description="إنشاء وإدارة مستندات Change Devise",
            open_handler=lambda owner: owner.open_cd(),
            icon="💱",
        ),
        ServiceDefinition(
            key="backup",
            title="النسخ الاحتياطي",
            description="حماية قاعدة البيانات وملفات العمل",
            open_handler=lambda owner: owner.open_backup(),
            icon="🗄️",
        ),
    ]
