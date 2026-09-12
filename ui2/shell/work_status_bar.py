"""WorkStatusBar — شريط الحالة الوحيد أسفل Workspace (Prototype، P0.2/P0.3).

**بصريّ بحت الآن**: رسالة حالة + صفحات (‹ 1/1 ›)، أزرار عرضٍ (Fit Page/
Fit Width)، وتحكّم تكبير (−/slider/+/100%/ملء الشاشة). لا شيء هنا يربط
بأيّ خدمة أو مستند حقيقيّ — التنقّل بين الصفحات معطَّلٌ عمداً (لا Work
حقيقي بعد)، وFit Page/Fit Width/Zoom/Full Screen بلا أثرٍ فعليّ على أي
محتوى؛ شريط التكبير يحدّث تسميته الخاصّة فقط لإثبات الشكل. التنفيذ
الحقيقيّ (صفحات/زوم/ملء شاشة فعليّ) خارج نطاق هذه المرحلة.

**الشريط الوحيد (P0.3 §4)**: ``QMainWindow.statusBar()`` الأصليّة لا
تُستعمَل في Shell الجديد إطلاقاً — رسائل الحالة ("جاهز"، "خدمة: CD")
تصل هنا عبر :meth:`set_message` بدل شريطٍ ثانٍ منفصل.

مكانه ثابتٌ أسفل ``WorkspaceHost`` فقط (لا يمتدّ تحت Explorer) —
``WorkspaceHost`` هو من يضمّه في تخطيطه العموديّ.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from ui2 import theme
from ui2.shell import metrics
from ui2.shell._icon_button import IconButton

#  ‏P2.2 §1: القيمة الفعلية في ``ui2.shell.metrics`` — اسمٌ مُعاد
#  التصدير فقط (توافقٌ خلفيّ).
HEIGHT = metrics.WORK_STATUS_BAR_HEIGHT


class WorkStatusBar(QWidget):
    """أربع مناطق **مرتَّبة هندسياً LTR دائماً**: رسالة (أقصى اليسار) ·
    صفحات · عناصر عرض (وسط) · تكبير (أقصى اليمين).

    ‏**STRUCTURAL DIRECTION != TEXT DIRECTION** (P0.3 §3 — نفس مبدأ
    MainSplitter وTopBar في P0.1/P0.2): ترتيب هذه المناطق ``LEFT → RIGHT``
    مقصودٌ بنيوياً بصرف النظر عن apply_theme العامّ (RTL)؛ لو تُرِك هذا
    الودجت يرث RTL من WorkspaceHost الأب كما كان، لانقلب الشريط كاملاً
    (التكبير يظهر يساراً، الصفحات يميناً) — لذا يُضبَط LTR صراحةً هنا،
    بينما نصوص/ToolTips كل عنصر تبقى بلغتها المناسبة (عربية) دون تأثّر."""

    def __init__(self, parent=None):
        super().__init__(parent)
        #  اتجاهٌ بنيويّ صريح — انظر docstring الصنف أعلاه.
        self.setLayoutDirection(Qt.LeftToRight)
        self.setFixedHeight(HEIGHT)
        self.setStyleSheet(
            f"background: {theme.SURFACE}; border-top: 1px solid {theme.BORDER};"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.SPACE["md"], 0, theme.SPACE["md"], 0)
        lay.setSpacing(theme.SPACE["sm"])

        #  ‏P2.2 §15: الرسالة هي العنصر "الثانويّ" الوحيد الذي يتنازل —
        #  minimumWidth(0) + Ignored horizontal policy + stretch=1 تجعلها
        #  أوّل من يتقلّص (حتى الصفر) عند ضيق المساحة، بينما Pages/View/
        #  Zoom (بلا stretch) تحافظ على حجمها الطبيعيّ الثابت دائماً —
        #  لا تُدفَع خارج الشاشة أبداً. النصّ الكامل يُقصّ بـellipsis
        #  (``_refresh_message_elide``) ويبقى متاحاً كاملاً عبر tooltip.
        self._message_text = ""
        self.lbl_message = QLabel("")
        self.lbl_message.setStyleSheet(f"color: {theme.TEXT_DIM};")
        #  ‏minimumWidth(0) صريح (بخلاف QLabel الافتراضية التي تمنع
        #  الانكماش دون عرض النصّ كاملاً) — أوّل عنصرٍ يتنازل عند
        #  الازدحام الحقيقيّ فقط؛ السياسة تبقى Preferred الطبيعية كي لا
        #  يخسر مساحته أمام الفاصلتين addStretch(1) في الحالة الرحبة
        #  العادية (Ignored كانت تجعله ينهار دائماً — جُرِّب وتراجَع عنه).
        self.lbl_message.setMinimumWidth(0)
        lay.addWidget(self.lbl_message)
        lay.addSpacing(theme.SPACE["md"])

        #  ‏P2.2 §16: ترتيبٌ بنيويّ محفوظ من P0.3 — LEFT: pages ·
        #  CENTER: view controls (بين الفاصلتين) · RIGHT: zoom. الفاصلتان
        #  addStretch(1) هما مصدر المساحة المرنة الوحيد هنا (لا الرسالة).
        for w in self._build_pages_zone():
            lay.addWidget(w)
        lay.addStretch(1)
        for w in self._build_view_zone():
            lay.addWidget(w)
        lay.addStretch(1)
        for w in self._build_zoom_zone():
            lay.addWidget(w)

    def set_message(self, text: str) -> None:
        """رسالة الحالة الوحيدة في Shell (P0.3 §4) — بديل QStatusBar
        الثاني الذي كان يظهر تحت هذا الشريط. النصّ الكامل يبقى متاحاً
        عبر tooltip حتى لو قُصَّ بصرياً (P2.2 §15)."""
        self._message_text = text or ""
        self._refresh_message_elide()

    def _refresh_message_elide(self) -> None:
        fm = self.lbl_message.fontMetrics()
        available = max(self.lbl_message.width(), 0)
        elided = fm.elidedText(self._message_text, Qt.ElideRight, available)
        self.lbl_message.setText(elided)
        self.lbl_message.setToolTip(self._message_text)

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        self._refresh_message_elide()

    # ------------------------------------------------------------ المناطق
    def _build_pages_zone(self):
        #  ‏LEFT — Pages: لا Work حقيقي بعد، فتبقى معطَّلة (بند 6).
        self.btn_prev_page = IconButton("‹", tooltip="الصفحة السابقة")
        self.btn_prev_page.setEnabled(False)
        self.lbl_pages = QLabel("1 / 1")
        self.lbl_pages.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.btn_next_page = IconButton("›", tooltip="الصفحة التالية")
        self.btn_next_page.setEnabled(False)
        return (self.btn_prev_page, self.lbl_pages, self.btn_next_page)

    def _build_view_zone(self):
        #  ‏CENTER — عناصر عرض: بلا أثرٍ فعليّ الآن (تقييم Layout فقط).
        self.btn_fit_page = IconButton("▭", tooltip="ملاءمة الصفحة")
        self.btn_fit_width = IconButton("↔", tooltip="ملء العرض")
        return (self.btn_fit_page, self.btn_fit_width)

    def _build_zoom_zone(self):
        #  ‏RIGHT — تكبير: demo/visual فقط، لا يربط بأيّ محتوى/خدمة.
        self.btn_zoom_out = IconButton("−", tooltip="تصغير")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(90)
        self.zoom_slider.setToolTip("مستوى التكبير (عرضٌ تجريبيّ)")
        self.btn_zoom_in = IconButton("+", tooltip="تكبير")
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setStyleSheet(f"color: {theme.TEXT_DIM}; min-width: 34px;")
        self.btn_fullscreen = IconButton("⤢", tooltip="ملء الشاشة")

        #  تحديث التسمية فقط — عرضٌ ذاتيّ للمكوّن، لا زوم حقيقيّ لأيّ محتوى.
        self.zoom_slider.valueChanged.connect(
            lambda v: self.lbl_zoom.setText(f"{v}%"))
        self.btn_zoom_out.clicked.connect(
            lambda: self.zoom_slider.setValue(
                max(self.zoom_slider.minimum(), self.zoom_slider.value() - 10)))
        self.btn_zoom_in.clicked.connect(
            lambda: self.zoom_slider.setValue(
                min(self.zoom_slider.maximum(), self.zoom_slider.value() + 10)))

        return (self.btn_zoom_out, self.zoom_slider, self.btn_zoom_in,
                self.lbl_zoom, self.btn_fullscreen)
