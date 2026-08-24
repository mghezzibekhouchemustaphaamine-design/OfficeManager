"""
خدمة CD (Change Devise): شاشة وحدة — تكتب البيانات مباشرة فوق صورة
النموذج الفاضي بمكانها الدقيق (زي الكتابة على الورقة الحقيقية)، وزر
واحد ينشئ المستند النهائي (Word) بنفس البيانات بالضبط.

الورقة تتوسّط دائماً بمنطقة العرض (أي حجم نافذة)، ومزوّدة بتكبير/تصغير
(زوم) وسكرول عمودي/أفقي.
"""
import tkinter as tk
import tkinter.font as tkfont

from tkinter import ttk, messagebox

from ui.cd_document import (
    generate_cd_document,
    get_blank_background,
    field_layout_px,
    FIELD_LAYOUT,
    TAUX_MAX_VALUE,
    TAUX_DEC_DIGITS,
)
from ui.widgets import MaskedDateEntry, MaskedTimeEntry, SplitDateEntry, select_all_on_real_focus
from utils import open_path

TARGET_W = 750  # عرض الصورة الأساسي (زوم 100%)
CANVAS_MARGIN = 20  # أقل مسافة بين الورقة وحواف منطقة العرض
# 9 كانت تعطي عرض حرف أضيق فعلياً (7px) من عرض الحرف الحقيقي بالمستند
# بنفس التكبير (8.3px تقريباً، محسوبة من نفس صيغة field_layout_px) —
# فرق كان يبين كفجوة بيضاء زايدة قبل أي نص "يُكتب أوتوماتيكياً" مباشرة
# بعد خانة كتابة (زي اسم الراكب المكرر بعد Guichet). 10 أقرب قياس ممكن
# (الأحجام صحيحة أرقام كاملة بس بـTk، ما فيها كسور) لعرض الحرف الحقيقي.
BASE_FONT_SIZE = 10
HOVER_IDLE_COLOR = "white"   # بلا إطار ظاهر (يندمج مع خلفية الورقة البيضاء) — لخانة معبّأة
HOVER_ON_COLOR = "#4a90d9"   # لون الإطار وقت التحويم
EMPTY_BORDER_COLOR = "#cfcfcf"  # حد رمادي خفيف يميّز مكان الكتابة الفاضي قبل التعبئة
ZOOM_LEVELS = [50, 75, 100, 125, 150, 175, 200]  # نسب مئوية نظيفة (كسور بسيطة)
DEFAULT_ZOOM_INDEX = ZOOM_LEVELS.index(100)


def _safe_float_or_none(text):
    text = (text or "").strip()
    if not text:
        return None
    if "." in text and "," in text:
        # صيغة فرنسية مُنسَّقة (زي "1.000,00"): النقطة فاصل آلاف، الفاصلة
        # فاصل عشري — نشيل النقاط أولاً ثم نبدّل الفاصلة بنقطة عشرية.
        text = text.replace(".", "").replace(",", ".")
    else:
        # صيغة بسيطة (زي taux "151.11" أو فاصلة عشرية وحيدة بلا فواصل آلاف).
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


class CDTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app

        self.zoom_index = DEFAULT_ZOOM_INDEX
        self._bg_photo_cache = {}  # نسبة الزوم -> PhotoImage بدقة أصلية (بدون تكبير/تضبيب)
        self.field_widgets = {}
        self.field_window_ids = {}
        self.field_natural_size = {}
        self.bg_item_id = None

        self._build_top_bar()
        self._build_canvas_area()
        self.after(50, self._load_background)

    # ---------- الشريط العلوي ----------
    def _build_top_bar(self):
        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(top_bar, text="🎛️ لوحة التحكم / الموديل", font=("Segoe UI", 14, "bold")).pack(side="left")

        zoom_bar = ttk.Frame(top_bar)
        zoom_bar.pack(side="left", padx=(25, 0))
        ttk.Button(zoom_bar, text="－", width=3, command=self.zoom_out).pack(side="left")
        self.zoom_label = ttk.Label(zoom_bar, text="100%", width=5, anchor="center")
        self.zoom_label.pack(side="left", padx=4)
        ttk.Button(zoom_bar, text="＋", width=3, command=self.zoom_in).pack(side="left")

        ttk.Button(top_bar, text="📄 إنشاء المستند (Word)", command=self.generate_document).pack(side="right")
        ttk.Button(top_bar, text="← رجوع", command=self.app.show_home).pack(side="right", padx=(0, 8))

    # ---------- منطقة الصورة القابلة للتمرير ----------
    def _build_canvas_area(self):
        holder = tk.Frame(self)
        holder.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(holder, bg="#c9c9c9", highlightthickness=0)
        vscroll = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        hscroll = ttk.Scrollbar(holder, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.loading_id = self.canvas.create_text(
            20, 20, anchor="nw", font=("Segoe UI", 12),
            text="⏳ جاري تجهيز الورقة أول مرة (يشتغل عبر Word، بضع ثواني)...",
        )

    def _load_background(self):
        if self.bg_item_id is not None:
            return  # تحميل مسبق فعلاً، ما نكرره (يمنع صور/حقول مكررة)
        self.canvas.delete(self.loading_id)
        self.bg_item_id = self.canvas.create_image(0, 0, anchor="nw")
        self._build_fields()
        self.canvas.bind("<Configure>", lambda _e: self._relayout())
        # Ctrl + عجلة الفأرة للزوم (فوق=تكبير، تحت=تصغير)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self._relayout()

    # ---------- الزوم ----------
    def zoom_in(self):
        if self.zoom_index < len(ZOOM_LEVELS) - 1:
            self.zoom_index += 1
            self._relayout()

    def zoom_out(self):
        if self.zoom_index > 0:
            self.zoom_index -= 1
            self._relayout()

    def _on_ctrl_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        return "break"  # يمنع السكرول العادي وقت الزوم بـ Ctrl

    def _current_zoom_pct(self):
        return ZOOM_LEVELS[self.zoom_index]

    def _bg_image_for_pct(self, pct, target_w):
        """
        يرجّع صورة الخلفية بدقة أصلية (مو مكبّرة من صورة أصغر، حتى تبقى
        الكتابة حادة دائماً). أول مرة لكل مستوى زوم تاخذ بضع ثواني
        (تولّد عبر Word)، وبعدها محفوظة (بالذاكرة وعلى القرص) وفورية.
        """
        if pct in self._bg_photo_cache:
            return self._bg_photo_cache[pct]

        loading_id = self.canvas.create_text(
            20, 20, anchor="nw", font=("Segoe UI", 11),
            text=f"⏳ جاري تجهيز الورقة بدقة {pct}% (أول مرة بس)...",
        )
        self.canvas.update_idletasks()
        try:
            bg_path = get_blank_background(target_w)
        except Exception as exc:  # noqa: BLE001
            self.canvas.delete(loading_id)
            messagebox.showerror("خطأ", f"تعذر تجهيز الورقة بهالمستوى:\n{exc}")
            return None
        self.canvas.delete(loading_id)

        img = tk.PhotoImage(file=bg_path)
        self._bg_photo_cache[pct] = img
        return img

    def _set_widget_font(self, widget, font):
        # ودجت مركّبة بعدة خانات كتابة (زي SplitDateEntry) تعرّف .entries
        # (قائمة)؛ ودجت بخانة وحدة (MaskedDateEntry/MaskedTimeEntry) تعرّف
        # .entry (مفرد)؛ خانة عادية (tk.Entry) نطبّق عليها مباشرة.
        targets = getattr(widget, "entries", None) or [getattr(widget, "entry", widget)]
        for target in targets:
            try:
                target.configure(font=font)
            except tk.TclError:
                pass
        # ودجت زي SplitDateEntry فيها خانة (السنة) تتموضع حياً حسب طول
        # النص جوار جنبها — لازم نعيد حسابها بعد ما يتبدل حجم الخط بالزوم.
        reposition = getattr(widget, "reposition_year", None)
        if reposition is not None:
            reposition()

    # ---------- إعادة التوضّع: توسيط الورقة + تطبيق مستوى الزوم ----------
    def _relayout(self):
        if self.bg_item_id is None:
            return

        pct = self._current_zoom_pct()
        self.zoom_label.config(text=f"{pct}%")

        target_w = round(TARGET_W * pct / 100)
        bg_image = self._bg_image_for_pct(pct, target_w)
        if bg_image is None:
            return
        self.layout = field_layout_px(target_w)
        self.current_bg_image = bg_image  # لازم مرجع حتى ما تُمسح

        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        img_w, img_h = bg_image.width(), bg_image.height()
        ox = max((canvas_w - img_w) // 2, CANVAS_MARGIN)
        oy = max((canvas_h - img_h) // 2, CANVAS_MARGIN)

        self.canvas.itemconfigure(self.bg_item_id, image=bg_image)
        self.canvas.coords(self.bg_item_id, ox, oy)

        font_size = max(6, round(BASE_FONT_SIZE * pct / 100))
        scaled_font = ("Courier New", font_size)

        for name, item_id in self.field_window_ids.items():
            x, y, w, h = self.layout[name]
            self.canvas.coords(item_id, ox + x, oy + y)
            if not self.field_natural_size[name]:
                self.canvas.itemconfigure(item_id, width=w, height=h)
            self._set_widget_font(self.field_widgets[name], scaled_font)

        # حقل الوقت يتبع فعلياً حرف "a" (جزء من date_entry نفسه) بفاصل
        # مسافة واحدة، مقاسة بالبكسل الحقيقي من الودجت نفسه — بدل عمود
        # تجريدي ثابت قد يتصادم مع الشهر أثناء الكتابة الجزئية.
        date_x, date_y, _, _ = self.layout["date"]
        time_font = tkfont.Font(font=self.time_entry.entry.cget("font"))
        space_px = time_font.measure(" ")
        time_x = ox + date_x + self.date_entry.a_right_edge_px() + space_px
        time_y = oy + self.layout["time"][1]
        self.canvas.coords(self.field_window_ids["time"], time_x, time_y)

        self.canvas.configure(
            scrollregion=(0, 0, max(img_w + 2 * ox, canvas_w), max(img_h + 2 * oy, canvas_h))
        )

    # ---------- الحقول فوق الصورة ----------
    def _place(self, name, widget, natural_size=False):
        """
        natural_size=True: لا نفرض عرض/طول بالبكسل (نسيب الودجت تاخذ
        حجمها الطبيعي) — ضروري للودجت المركّبة (تاريخ/وقت) حتى ما ننقص
        عرضها ونقص آخر حرف مكتوب. الموضع الفعلي يتحدد بـ _relayout().
        """
        item_id = self.canvas.create_window(0, 0, window=widget, anchor="nw")
        self.field_widgets[name] = widget
        self.field_window_ids[name] = item_id
        self.field_natural_size[name] = natural_size

    def _base_entry_kwargs(self):
        # justify="left" صريحة حتى تكتب دائماً من اليسار لليمين (LTR)، بغض
        # النظر عن إعدادات اللغة/الاتجاه بالنظام. بدون إطار افتراضياً حتى
        # تبقى الشاشة نظيفة — الإطار يظهر ثابت طول ما الفأرة فوق الخانة
        # (إشارة بصرية إنها قابلة للكتابة)، ويختفي لما الفأرة تبعد.
        return dict(
            font=("Courier New", BASE_FONT_SIZE), bd=0, relief="flat",
            bg="white", highlightthickness=1,
            highlightbackground=HOVER_IDLE_COLOR, highlightcolor=HOVER_IDLE_COLOR,
            justify="left",
        )

    def _entry(self, var, maxlen=None):
        """maxlen (اختياري): حد أقصى لعدد الحروف — ضروري لأي حقل تليه
        كتابة أخرى بنفس السطر بالمستند الحقيقي (زي Guichet قبل اسم
        الراكب المكرر، أو N° Passport قبل "Obtent."): لو تجاوز المكتوب
        العرض المخصّص له بـFIELD_LAYOUT، القيمتين تتلاصقان بلا فاصل
        بالمستند النهائي (.ljust() ما يأثر إذا النص أصلاً أطول من العمود
        المطلوب) — خلل حقيقي بالبيانات، مو بس مظهر."""
        kwargs = self._base_entry_kwargs()
        if maxlen is not None:
            vcmd = (self.register(lambda P: P == "" or len(P) <= maxlen), "%P")
            e = tk.Entry(self.canvas, textvariable=var, validate="key", validatecommand=vcmd, **kwargs)
        else:
            e = tk.Entry(self.canvas, textvariable=var, **kwargs)
        self._add_hover(e, var)
        # الانتقال (بـTab أو نقرة) لخانة فيها كتابة سابقة يُبرز (يحدّد)
        # القيمة كاملة بدل ما يترك المؤشر يضيف لآخرها — أول حرف تكتبه
        # يستبدلها مباشرة (Entry عادية، Tk يتكفّل بالاستبدال أوتوماتيكياً).
        # ما ينطبق لو الرجوع مجرد Alt+Tab من برنامج آخر ثم العودة لنفس
        # الخانة (راجع select_all_on_real_focus بـui.widgets) — عندها
        # المؤشر والكتابة الجزئية تبقى كما هي بالضبط، نكمّل من نفس المكان.
        e.bind("<FocusIn>", lambda _ev: select_all_on_real_focus(e))
        return e

    def _numeric_entry(self, var, maxlen):
        """خانة أرقام بس (بدون حروف)، بحد أقصى maxlen رقم."""
        vcmd = (self.register(lambda P: P == "" or (P.isdigit() and len(P) <= maxlen)), "%P")
        e = tk.Entry(
            self.canvas, textvariable=var, validate="key", validatecommand=vcmd,
            **self._base_entry_kwargs(),
        )
        self._add_hover(e, var)
        # نفس لمسة حقول التاريخ/الوقت: رجوع للخانة يُبرز (يحدّد) قيمتها
        # كاملة بدل ما يمسحها — Entry عادية، فـTk يستبدل المحدَّد
        # أوتوماتيكياً بأول رقم يُكتب. ما ينطبق لمجرد Alt+Tab من برنامج
        # آخر (راجع الملاحظة بـ_entry أعلاه).
        e.bind("<FocusIn>", lambda _ev: select_all_on_real_focus(e))
        return e

    def _alnum_entry(self, var, allow_space=False, maxlen=None):
        """خانة نص تقبل بس أرقام وحروف لاتينية (إنجليزي/فرنسي بلا حركات)،
        وتُحوَّل تلقائياً لحروف كبيرة أثناء الكتابة (زي "abc" -> "ABC")
        بدل ما ترفضها — أسهل للمستخدم من رفضها ومطالبته يفعّل Caps Lock
        يدوياً. allow_space=True يسمح بمسافة كمان (أسماء بكلمتين وأكثر،
        زي "TEST PASSAGER")."""
        kwargs = self._base_entry_kwargs()

        def char_ok(c):
            return (c.isascii() and (c.isalpha() or c.isdigit())) or (allow_space and c == " ")

        def validate(P):
            if maxlen is not None and len(P) > maxlen:
                return False
            return all(char_ok(c) for c in P)

        vcmd = (self.register(validate), "%P")
        e = tk.Entry(self.canvas, textvariable=var, validate="key", validatecommand=vcmd, **kwargs)
        self._add_hover(e, var)
        # ما ينطبق لمجرد Alt+Tab من برنامج آخر (راجع الملاحظة بـ_entry).
        e.bind("<FocusIn>", lambda _ev: select_all_on_real_focus(e))

        def force_upper(*_a):
            cur = var.get()
            upper = cur.upper()
            if upper != cur:
                pos = e.index(tk.INSERT)
                var.set(upper)
                e.icursor(pos)
                # نفس ملاحظة _currency_entry: var.set() يعطّل validate
                # أوتوماتيكياً، لازم نرجّعه يدوياً.
                e.configure(validate="key")

        var.trace_add("write", force_upper)
        return e

    def _currency_entry(self, var, max_value=999999, decimals=2):
        """خانة مبلغ مالي: أثناء الكتابة تقبل أرقام صرف، وفاصلة عشرية
        وحيدة اختيارية ("," أو ".") متبوعة بـ0-decimals رقم بعدها (الجزء
        الصحيح محدود بـmax_value)، محاذاة لليمين دائماً. بمجرد ما تخرج
        منها (FocusOut) تُنسَّق أوتوماتيكياً بصيغة فرنسية: فاصل آلاف "."
        + فاصلة عشرية "," بعدد أرقام decimals بالضبط بعدها دائماً (مثال
        بـdecimals=2):
          - "1000"  (بلا فاصلة) -> "1.000,00"
          - "10,1"  (رقم عشري واحد) -> "10,10"
          - "10.1"  (نقطة بدل الفاصلة) -> "10,10" (نفس المعاملة)
          - "10,10" (رقمين عشريين) -> "10,10" (بلا تغيير)

        القيمة تبقى نص خام (فاصلة/نقطة وحيدة بس، بلا فاصل آلاف) طول ما
        إحنا داخل الخانة نكتب فيها — التنسيق يصير مرة وحدة بس عند الخروج،
        وما يتكرر لو رجعت للخانة وخرجت منها بلا تعديل (النص المنسَّق فيه
        فاصل آلاف "." وفاصلة عشرية "," معاً، فنميّزه ونتجاهله)."""
        kwargs = dict(self._base_entry_kwargs(), justify="right")

        def validate(P):
            if P == "":
                return True
            sep_count = P.count(",") + P.count(".")
            if sep_count > 1:
                return False
            if sep_count == 1:
                sep = "," if "," in P else "."
                int_part, dec_part = P.split(sep)
            else:
                int_part, dec_part = P, ""
            if int_part and not int_part.isdigit():
                return False
            if dec_part and not (dec_part.isdigit() and len(dec_part) <= decimals):
                return False
            if int_part and int(int_part) > max_value:
                return False
            return True

        vcmd = (self.register(validate), "%P")
        e = tk.Entry(self.canvas, textvariable=var, validate="key", validatecommand=vcmd, **kwargs)
        self._add_hover(e, var)
        # ما ينطبق لمجرد Alt+Tab من برنامج آخر (راجع الملاحظة بـ_entry) —
        # التنسيق عند الخروج (format_on_leave بالأسفل) يبقى يشتغل عادي
        # بكل الحالات (حتى لو الخروج بسبب Alt+Tab)، بس التحديد الكامل
        # للنص هو اللي ما يصير إلا بتنقّل حقيقي.
        e.bind("<FocusIn>", lambda _ev: select_all_on_real_focus(e))

        def format_on_leave(_ev=None):
            raw = var.get().strip()
            if not raw or ("." in raw and "," in raw):
                return  # فاضي، أو فيه فاصل آلاف وفاصلة عشرية معاً -> منسَّق أصلاً
            sep = "," if "," in raw else ("." if "." in raw else None)
            int_part, dec_part = raw.split(sep, 1) if sep else (raw, "")
            if (int_part and not int_part.isdigit()) or (dec_part and not dec_part.isdigit()):
                return
            int_part = int_part or "0"
            dec_part = (dec_part + "0" * decimals)[:decimals]
            var.set(f"{int(int_part):,}".replace(",", ".") + "," + dec_part)
            # Tk يعطّل "validate" أوتوماتيكياً (يرجعه "none") بمجرد ما
            # نغيّر النص برمجياً (var.set) بدل كتابة حقيقية — لازم
            # نرجّعه "key" يدوياً، وإلا القيود (الحد الأقصى...) تنعطّل
            # نهائياً بعد أول تنسيق.
            e.configure(validate="key")

        e.bind("<FocusOut>", format_on_leave, add="+")
        return e

    def _add_hover(self, widget, var=None):
        """يظهر إطار ملوّن ثابت طول ما الفأرة فوق الخانة، ويختفي لما الفأرة
        تبعد — إشارة بصرية بسيطة إنها قابلة للكتابة، بدون وميض.

        var (اختياري): لو انعطى، الخانة الفاضية تاخذ حداً رمادياً خفيفاً
        دائم (حتى بدون تحويم الفأرة) — يميّز مكان الكتابة قبل التعبئة.
        بمجرد ما تُكتب فيها، الحد يختفي (يرجع لسلوكها العادي المندمج مع
        الورقة)."""

        def idle_color():
            if var is not None and not (var.get() or "").strip():
                return EMPTY_BORDER_COLOR
            return HOVER_IDLE_COLOR

        def set_idle():
            color = idle_color()
            widget.configure(highlightbackground=color, highlightcolor=color)

        def on_enter(_event):
            widget.configure(highlightbackground=HOVER_ON_COLOR, highlightcolor=HOVER_ON_COLOR)

        def on_leave(_event):
            set_idle()

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        set_idle()
        if var is not None:
            var.trace_add("write", lambda *a: set_idle())

    def _maybe_year_complete(self):
        """بمجرد ما تكتمل السنة (4 أرقام)، ننتقل أوتوماتيكياً لخانة
        الوقت — نفس مبدأ اليوم/الشهر بالضبط."""
        if len(self.date_entry.year_var.get()) == 4:
            self.after_idle(self.time_entry.entry.focus_set)

    def _label_display(self, var, anchor="w"):
        """نص حي (Label) بدون كتابة مباشرة — يعكس متغيّر آخر تلقائياً.
        anchor="w" افتراضياً (محاذاة يسار، زي انعكاس اسم الراكب بسطر
        Guichet)؛ anchor="e" للحقول اللي لازم تظهر أقصى اليمين (زي
        Net a créditer، نفس محاذاة الأرقام بباقي حقول المبالغ)."""
        lbl = tk.Label(
            self.canvas, textvariable=var, font=("Courier New", BASE_FONT_SIZE), bg="white", anchor=anchor,
            highlightthickness=0,
        )
        return lbl

    def _build_fields(self):
        self.no_var = tk.StringVar()
        self.agence_var = tk.StringVar()
        self.guichet_var = tk.StringVar()
        self.caisse_var = tk.StringVar()
        self.guichetier_var = tk.StringVar()
        self.passager_var = tk.StringVar()
        self.passport_var = tk.StringVar()
        self.taux_var = tk.StringVar()
        self.eur_var = tk.StringVar()
        self.dzd_var = tk.StringVar()
        self.net_crediter_var = tk.StringVar(value="")

        self._place("no", self._numeric_entry(self.no_var, FIELD_LAYOUT["no"][2]))

        self.date_entry = SplitDateEntry(self.canvas, default_today=False)
        self._place("date", self.date_entry, natural_size=True)
        self._add_hover(self.date_entry.day_entry, self.date_entry.day_var)
        self._add_hover(self.date_entry.month_entry, self.date_entry.month_var)
        self._add_hover(self.date_entry.year_entry, self.date_entry.year_var)
        # حرف "a" جزء داخلي من date_entry نفسه (سطر/جملة واحدة متماسكة مع
        # يوم/شهر/سنة) — لا حاجة لعنصر منفصل هنا، راجع SplitDateEntry.

        # حقل الوقت يتبع حياً نهاية حقل التاريخ (بعد حرف "a"): أي تغيير
        # باليوم/الشهر/السنة يعيد حساب مكانهما فوراً (زي ما يتحسبان بالضبط
        # بالمستند الحقيقي).
        for var in (self.date_entry.day_var, self.date_entry.month_var, self.date_entry.year_var):
            var.trace_add("write", lambda *a: self._relayout())
        self.time_entry = MaskedTimeEntry(self.canvas, default_now=False)
        self._place("time", self.time_entry, natural_size=True)
        self._add_hover(self.time_entry.entry, self.time_entry.var)

        # لما تكتمل السنة (4 أرقام) ننتقل أوتوماتيكياً لخانة الوقت — نفس
        # مبدأ اليوم يكمل وينتقل للشهر، والشهر يكمل وينتقل للسنة. مؤجّل
        # بـafter_idle (زي انتقالات اليوم/الشهر بالضبط) حتى ما نغيّر
        # التركيز ونحن لسا وسط معالجة ضغطة الرقم نفسها.
        self.date_entry.year_var.trace_add("write", lambda *a: self._maybe_year_complete())

        # كل حقول النص العادية محدودة بعرضها المعلن بـFIELD_LAYOUT بالضبط
        # (لا أزيد ولا أنقص) — نفس مبدأ Guichet/N° Passport، حتى لو ما
        # كانت متبوعة بكتابة أخرى بنفس السطر (يمنع الكتابة تفيض عن حدود
        # المساحة الحقيقية المتاحة لها بالمستند المطبوع).
        self._place("agence", self._entry(self.agence_var, maxlen=FIELD_LAYOUT["agence"][2]))
        self._place("guichet", self._entry(self.guichet_var, maxlen=FIELD_LAYOUT["guichet"][2]))
        self._place("caisse", self._entry(self.caisse_var, maxlen=FIELD_LAYOUT["caisse"][2]))
        self._place("guichetier", self._entry(self.guichetier_var, maxlen=FIELD_LAYOUT["guichetier"][2]))

        # انعكاس اسم الراكب بآخر سطر Guichet (نص حي، مو خانة كتابة)
        self.guichet_mirror_lbl = self._label_display(self.passager_var)
        self._place("guichet_mirror", self.guichet_mirror_lbl)

        # اسم الراكب: أرقام وحروف كبيرة بس (تُحوَّل تلقائياً)، مع مسافة
        # مسموحة (أسماء بكلمتين وأكثر)، ومحدود بعرضه المعلن بـFIELD_LAYOUT.
        self._place(
            "passager",
            self._alnum_entry(self.passager_var, allow_space=True, maxlen=FIELD_LAYOUT["passager"][2]),
        )
        # نفس مبدأ Guichet بالضبط: N° Passport يتبعه "Obtent." بنفس السطر.
        # نفس قيد الاسم (أرقام وحروف كبيرة بس، بلا مسافة) — أرقام الجواز
        # عادة مزيج أحرف وأرقام.
        self._place("passport_no", self._alnum_entry(self.passport_var, maxlen=FIELD_LAYOUT["passport_no"][2]))

        self.delivrance_entry = MaskedDateEntry(self.canvas, default_today=False)
        self._place("date_delivrance", self.delivrance_entry, natural_size=True)
        self._add_hover(self.delivrance_entry.entry, self.delivrance_entry.var)

        # حقلا المبلغ (EUR وDZD): تنسيق تلقائي بصيغة فرنسية (فاصل آلاف
        # "." + ",00" بالنهاية) عند الخروج منهما، بحد أقصى 999.999 —
        # راجع _currency_entry.
        self._place("eur", self._currency_entry(self.eur_var))
        # taux: نفس مبدأ EUR/DZD (صيغة فرنسية + تنسيق تلقائي عند الخروج)
        # بس 3 أرقام صحيحة كحد أقصى و7 أرقام عشرية بالضبط دائماً (بدل 2).
        self._place("taux", self._currency_entry(self.taux_var, max_value=TAUX_MAX_VALUE, decimals=TAUX_DEC_DIGITS))
        self._place("dzd", self._currency_entry(self.dzd_var))

        # Net a créditer: نص حي يعكس DZD (نفس القيمة دائماً لأن العمولات 0)
        self.net_crediter_lbl = self._label_display(self.net_crediter_var, anchor="e")
        self._place("net_crediter", self.net_crediter_lbl)

        # مثلث Taux/EUR/DZD: تكتب أي خانتين بأي ترتيب، والثالثة تتحسب لحالها
        self._triangle_vars = {"taux": self.taux_var, "eur": self.eur_var, "dzd": self.dzd_var}
        self._triangle_edit_order = []
        self._triangle_updating = False
        for name, var in self._triangle_vars.items():
            var.trace_add("write", lambda *a, n=name: self._on_triangle_change(n))

        self.dzd_var.trace_add("write", lambda *a: self._update_net_crediter())

    def _update_net_crediter(self):
        val = _safe_float_or_none(self.dzd_var.get())
        self.net_crediter_var.set(f"{val:,.2f}".translate(str.maketrans(",.", ".,")) if val is not None else "")

    def _on_triangle_change(self, name):
        if self._triangle_updating:
            return
        if name in self._triangle_edit_order:
            self._triangle_edit_order.remove(name)
        self._triangle_edit_order.append(name)
        self._triangle_edit_order = self._triangle_edit_order[-2:]

        if len(self._triangle_edit_order) < 2:
            return

        target = (set(self._triangle_vars) - set(self._triangle_edit_order)).pop()
        known = {}
        for n in self._triangle_edit_order:
            val = _safe_float_or_none(self._triangle_vars[n].get())
            if val is None:
                return
            known[n] = val

        try:
            if target == "dzd":
                result = known["taux"] * known["eur"]
            elif target == "eur":
                if known["taux"] == 0:
                    return
                result = known["dzd"] / known["taux"]
            else:  # target == "taux"
                if known["eur"] == 0:
                    return
                result = known["dzd"] / known["eur"]
        except (KeyError, ZeroDivisionError):
            return

        self._triangle_updating = True
        try:
            # الثلاثة (taux/eur/dzd) الآن نفس نوع الحقل (_currency_entry)
            # وناخذ نفس التنسيق الفرنسي لما تُحسب أوتوماتيكياً — فقط عدد
            # الأرقام العشرية يختلف (7 لـtaux، 2 للباقي).
            decimals = TAUX_DEC_DIGITS if target == "taux" else 2
            self._triangle_vars[target].set(f"{result:,.{decimals}f}".translate(str.maketrans(",.", ".,")))
            # نفس ملاحظة _currency_entry: تعديل النص برمجياً (var.set)
            # يعطّل validate أوتوماتيكياً — نرجّعه يدوياً.
            self.field_widgets[target].configure(validate="key")
        finally:
            self._triangle_updating = False

    # ---------- جمع البيانات وتوليد المستند ----------
    def collect_data(self):
        try:
            entry_date = self.date_entry.get_date()
        except ValueError:
            entry_date = None
        try:
            time_str = self.time_entry.get_time_str()
        except ValueError:
            time_str = ""
        try:
            delivrance_date = self.delivrance_entry.get_date()
        except ValueError:
            delivrance_date = None

        taux = _safe_float_or_none(self.taux_var.get())
        eur = _safe_float_or_none(self.eur_var.get())
        dzd = _safe_float_or_none(self.dzd_var.get())

        return {
            "no": self.no_var.get().strip(),
            "date": entry_date,
            "time": time_str,
            "agence": self.agence_var.get().strip(),
            "guichet": self.guichet_var.get().strip(),
            "caisse": self.caisse_var.get().strip(),
            "guichetier": self.guichetier_var.get().strip(),
            "passager": self.passager_var.get().strip(),
            "passport_no": self.passport_var.get().strip(),
            "date_delivrance": delivrance_date,
            "taux": taux,
            "eur": eur,
            "dzd": dzd,
        }

    # الحقول الأساسية اللي تحدّد هوية المستند — لو كلها أو بعضها فاضي،
    # ننبّه قبل التوليد بدل ما نطلع ملف Word رسمي فاضي بصمت (خطر حقيقي
    # على مستند عمل، مو مجرد تفصيل شكلي).
    _REQUIRED_FIELDS = [
        ("no", "رقم البوردرو (No)"),
        ("date", "التاريخ"),
        ("passager", "اسم الراكب"),
    ]

    def generate_document(self):
        if not hasattr(self, "layout"):
            messagebox.showwarning("تنبيه", "الورقة لسا ما جهزت، انتظر لحظة وحاول مرة ثانية")
            return
        data = self.collect_data()

        missing = [label for key, label in self._REQUIRED_FIELDS if not data.get(key)]
        if missing:
            proceed = messagebox.askyesno(
                "تنبيه",
                "الحقول التالية فاضية أو غير صالحة:\n"
                + "\n".join(f"• {m}" for m in missing)
                + "\n\nتريد تكمل وتنشئ المستند مع هذا؟",
            )
            if not proceed:
                return

        try:
            path = generate_cd_document(data)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("خطأ", f"تعذر إنشاء المستند:\n{exc}")
            return
        open_path(path)

    def refresh(self):
        pass
