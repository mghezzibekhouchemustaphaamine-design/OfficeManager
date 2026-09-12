"""بيانات Demo Work Tabs — تحقّق بصريّ معزول فقط (P0.3 §6).

**هذه ليست تنفيذاً نهائياً ولا تدخل مسار المنتج الحقيقي:** لا Work
lifecycle، لا كتابة قاعدة بيانات، لا ربط بأيّ خدمة فعلية. الهدف الوحيد
تقييم اللغة البصريّة لِـ``WorkTabBar`` (Active/Inactive/Hover/Dirty/
Locked/Close) قبل ربط أعمالٍ حقيقية.

تُفعَّل فقط عبر ``python -m ui2.shell --demo-tabs`` أو استدعاء صريح
لِـ``OfficeMainWindow.enable_demo_tabs()`` — لا شيء يُفعِّلها تلقائياً
في الوضع العاديّ.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoWorkTab:
    title: str
    dirty: bool = False
    locked: bool = False

    def display_text(self) -> str:
        """نصّ التبويب مع مؤشّرٍ صغير — ● للتعديل غير المحفوظ، 🔒
        للقفل (بند 6: مؤشّراتٌ بصريّة فقط، بلا lifecycle حقيقيّ)."""
        if self.locked:
            return f"{self.title} 🔒"
        if self.dirty:
            return f"{self.title} ●"
        return self.title


#  ثلاثة أعمالٍ تجريبية تغطي الحالات الثلاث المطلوبة للتقييم البصري.
DEMO_WORK_TABS = (
    DemoWorkTab("Bulletin Ahmed", dirty=True),
    DemoWorkTab("CD 1584", locked=True),
    DemoWorkTab("Attestation Nadia"),
)
