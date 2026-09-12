"""TopBar — شريط عامّ ثابت خاصّ بـ OfficeManager (وليس بأيّ خدمة).

P0.2: منطقتان بنيويّتان ثابتتا الموضع (بغضّ النظر عن RTL — نفس مبدأ
Explorer|Workspace في P0.1):

* **Brand Zone** يساراً — فوق Explorer تقريباً، بعرضٍ يتزامن معه.
* **Nav Zone** يميناً — فوق Workspace: Home (+ Back placeholder) عند
  بداية المنطقة، Settings/Lock عند طرفها الآخر.

لا Save/Print/Undo/Zoom هنا — هذه أدوات خدمة تعيش في ``CommandBar``
مستقبلاً. Settings/Lock تبقيان placeholders معطّلين بصريّين فقط.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui2 import theme
from ui2.shell._icon_button import IconButton

HEIGHT = 52
#  عرض Brand Zone الافتراضي — يطابق عرض Explorer الابتدائي في
#  main_window.py (splitter.setSizes([220, ...])). يُزامَن لاحقاً مع
#  سحب الفاصل عبر set_brand_width()، بحدٍّ أقصى (P0.3 §2): Explorer
#  قابلٌ للتوسّع حتى 460px (main_window.EXPLORER_MAX_WIDTH)، لكن Brand
#  Zone لا تكبر معه بلا حدود — تتجمّد عند MAX_BRAND_WIDTH فلا تتحوّل
#  رأس "OfficeManager" إلى مساحة فارغة ضخمة.
MIN_BRAND_WIDTH = 180
DEFAULT_BRAND_WIDTH = 220
MAX_BRAND_WIDTH = 320


class TopBar(QWidget):

    homeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        #  ‏STRUCTURAL DIRECTION != TEXT DIRECTION (يمتدّ مبدأ P0.1 إلى
        #  TopBar نفسه): Brand Zone يسار المصفوفة، Nav Zone يمينها —
        #  ثابتان هندسياً بصرف النظر عن apply_theme العامّ، فيُضبَط
        #  الحاوي الأعلى هنا LTR صراحةً (لا اعتماداً عرضياً على RTL).
        self.setLayoutDirection(Qt.LeftToRight)
        self.setFixedHeight(HEIGHT)
        self.setStyleSheet(
            f"background: {theme.SURFACE}; border-bottom: 1px solid {theme.BORDER};"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._brand_zone = self._build_brand_zone()
        outer.addWidget(self._brand_zone)

        nav_zone = self._build_nav_zone()
        outer.addWidget(nav_zone, 1)

    # ------------------------------------------------------------ البناء
    def _build_brand_zone(self) -> QWidget:
        zone = QWidget(self)
        zone.setFixedWidth(DEFAULT_BRAND_WIDTH)
        #  حدّ الفصل عن Nav Zone يقع على الحافة اليمنى لهذه المنطقة (هي
        #  يسار الشاشة هندسياً) — يمتدّ بصرياً مع حدّ Explorer/Workspace
        #  تحته تقريباً.
        zone.setStyleSheet(f"border-right: 1px solid {theme.BORDER};")
        lay = QHBoxLayout(zone)
        lay.setContentsMargins(theme.SPACE["lg"], 0, theme.SPACE["md"], 0)
        lay.setSpacing(theme.SPACE["sm"])

        icon = QLabel("◈")
        icon.setStyleSheet(f"font-size: 16px; color: {theme.PRIMARY};")
        lay.addWidget(icon)

        brand = QLabel("OfficeManager")
        brand.setStyleSheet(
            f"font-size: {theme.FONT_SIZES['card']}px; font-weight: 700;"
        )
        lay.addWidget(brand)
        lay.addStretch(1)
        return zone

    def _build_nav_zone(self) -> QWidget:
        zone = QWidget(self)
        lay = QHBoxLayout(zone)
        lay.setContentsMargins(theme.SPACE["md"], 0, theme.SPACE["lg"], 0)
        lay.setSpacing(theme.SPACE["xs"])

        #  Back — placeholder سياقيّ فقط، معطَّل حالياً (لا تاريخ تنقّلٍ
        #  حقيقيّ بعد). يجاور Home عند بداية Nav Zone.
        self.btn_back = IconButton("‹", tooltip="رجوع")
        self.btn_back.setEnabled(False)
        lay.addWidget(self.btn_back)

        self.btn_home = IconButton("⌂", "الرئيسية", tooltip="الرئيسية",
                                    checkable=True)
        self.btn_home.clicked.connect(self.homeRequested)
        lay.addWidget(self.btn_home)

        lay.addStretch(1)

        # placeholders بصرية فقط — بلا سلوك في هذه المرحلة
        self.btn_settings = IconButton("⚙", tooltip="الإعدادات")
        self.btn_settings.setEnabled(False)
        lay.addWidget(self.btn_settings)

        self.btn_lock = IconButton("🔒", tooltip="قفل")
        self.btn_lock.setEnabled(False)
        lay.addWidget(self.btn_lock)
        return zone

    # -------------------------------------------------------------- حالة
    def set_home_active(self, active: bool) -> None:
        """‏Home نشِطة (خلفيّة Accent خفيفة) عندما تكون HomeView المعروضة
        فعلياً؛ تعود غير نشِطة في ServiceStartView."""
        self.btn_home.setChecked(bool(active))

    def set_brand_width(self, width: int) -> None:
        """مزامنة عرض Brand Zone مع عرض Explorer الفعليّ (سحب الفاصل) —
        بصريّ فقط، مُحدَّدةً بـ[MIN_BRAND_WIDTH, MAX_BRAND_WIDTH]
        (P0.3 §2: ``brand_width = clamp(explorer_width, min, max)``) —
        لا تتبع Explorer حرفياً بلا حدود."""
        if width <= 0:
            return
        clamped = max(MIN_BRAND_WIDTH, min(MAX_BRAND_WIDTH, width))
        self._brand_zone.setFixedWidth(clamped)
