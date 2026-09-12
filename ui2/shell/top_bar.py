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
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from ui2 import theme
from ui2.shell import metrics
from ui2.shell._icon_button import IconButton

#  ‏P2.2 §1: القيَم الفعلية في ``ui2.shell.metrics`` المركزية — أسماءٌ
#  مُعادة التصدير فقط (توافقٌ خلفيّ لاختبارات P0.2/P0.3 التي تستورد من هنا).
HEIGHT = metrics.TOP_BAR_HEIGHT
MIN_BRAND_WIDTH = metrics.BRAND_MIN_WIDTH
DEFAULT_BRAND_WIDTH = metrics.BRAND_DEFAULT_WIDTH
MAX_BRAND_WIDTH = metrics.BRAND_MAX_WIDTH


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

        lay.addSpacing(theme.SPACE["md"])
        #  ‏P2.1 §13 → P2.2 §11: مكانٌ بصريّ محجوز فقط لحقل بحث مستقبليّ —
        #  بلا أيّ منطق (لا Explorer، لا DB، لا Global/Explorer قرار
        #  الآن). read-only + NoFocus صراحةً: يبدو طبيعياً (غير رماديّ/
        #  disabled) لكن لا يستقبل كتابة فعلية ولا يسرق Tab focus بلا
        #  معنى — كي لا يوحي للمستخدم بخللٍ ("لماذا لا تكتب؟"). يتقلّص
        #  هو أوّلاً (P2.2 §10) ضمن حدّي metrics.SEARCH_MIN/MAX_WIDTH —
        #  الأزرار المجاورة (Home/Settings/Lock) بلا stretch فتحافظ على
        #  حجمها الطبيعيّ دائماً، فلا تُدفَع خارج الشاشة.
        self.search_box = QLineEdit(zone)
        self.search_box.setPlaceholderText("بحث…")
        self.search_box.setReadOnly(True)
        self.search_box.setFocusPolicy(Qt.NoFocus)
        self.search_box.setCursor(Qt.ArrowCursor)
        self.search_box.setMinimumWidth(metrics.SEARCH_MIN_WIDTH)
        self.search_box.setMaximumWidth(metrics.SEARCH_MAX_WIDTH)
        self.search_box.setFixedHeight(30)
        self.search_box.setStyleSheet(
            f"QLineEdit {{ background: {theme.BG}; border: 1px solid {theme.BORDER};"
            f" border-radius: 6px; padding: 2px 10px; color: {theme.TEXT_DIM}; }}"
        )
        lay.addWidget(self.search_box, 1)

        lay.addStretch(0)

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
