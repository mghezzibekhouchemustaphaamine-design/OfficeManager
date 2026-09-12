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
from ui2.shell._icon_button import IconButton

HEIGHT = 30


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

        self.lbl_message = QLabel("")
        self.lbl_message.setStyleSheet(f"color: {theme.TEXT_DIM};")
        lay.addWidget(self.lbl_message)
        lay.addSpacing(theme.SPACE["md"])

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
        الثاني الذي كان يظهر تحت هذا الشريط."""
        self.lbl_message.setText(text or "")

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
