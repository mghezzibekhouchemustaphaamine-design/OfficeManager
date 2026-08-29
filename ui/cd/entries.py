"""
خانات الكتابة المخصّصة لشاشة CD (رقم بس، نص/حروف كبيرة، مبلغ مالي) — كل
واحدة فيها قيود الصحة (validation) الخاصة بنوع الحقل + سلوكيات مشتركة
(حد أقصى للطول، تحويل تلقائي لحروف كبيرة، تنسيق مبالغ، تحديد جزء بدبل-
كليك، إطار تحويم يميّز الخانة القابلة للكتابة...).

Mixin (مو كلاس مستقل قائم بذاته) لأنها تعتمد بشكل وثيق على حالة الشاشة
نفسها (self.canvas تُرسم الخانات فوقه، self.register لتسجيل دوال Tk
للتحقق من صحة الكتابة) — دمجها بـCDTab عبر وراثة
(class CDTab(ttk.Frame, CDEntryFactoryMixin)) يحافظ على نفس السلوك
بالضبط بلا أي إعادة كتابة، بس بملف منفصل أخف وأسهل نلقى فيه أي حقل بلا
ما نغرق بمنطق الشاشة الثاني (التبويبات، التراجع، التوليد...)."""
import tkinter as tk

from ui.common.widgets import (
    select_all_on_real_focus, bind_triple_click_select_all, bind_enter_advances_focus,
    bind_advance_on_maxlen,
)
from ui.cd.constants import BASE_FONT_SIZE, HOVER_IDLE_COLOR, HOVER_ON_COLOR, EMPTY_BG_COLOR, FILLED_BG_COLOR


class CDEntryFactoryMixin:
    """يفترض إنه مُدمَج بكلاس عنده self.canvas (تُرسم الخانات فوقه) و
    self.register (تسجيل دوال Tk للتحقق من صحة الكتابة) — أي كلاس
    ttk.Frame/tk.Widget عادي يوفّر الاثنين."""

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
        # الخانة (راجع select_all_on_real_focus بـui.common.widgets) —
        # عندها المؤشر والكتابة الجزئية تبقى كما هي بالضبط، نكمّل من نفس
        # المكان.
        e.bind("<FocusIn>", lambda _ev: select_all_on_real_focus(e))
        bind_triple_click_select_all(e)
        bind_enter_advances_focus(e)
        if maxlen is not None:
            bind_advance_on_maxlen(e, var, maxlen)
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
        bind_triple_click_select_all(e)
        bind_enter_advances_focus(e)
        bind_advance_on_maxlen(e, var, maxlen)
        return e

    def _alnum_entry(self, var, allow_space=False, maxlen=None, allow_digits=True):
        """خانة نص تقبل بس حروف لاتينية (إنجليزي/فرنسي بلا حركات)، وتُحوَّل
        تلقائياً لحروف كبيرة أثناء الكتابة (زي "abc" -> "ABC") بدل ما
        ترفضها — أسهل للمستخدم من رفضها ومطالبته يفعّل Caps Lock يدوياً.
        allow_space=True يسمح بمسافة كمان (أسماء بكلمتين وأكثر، زي
        "TEST PASSAGER"). allow_digits=False يمنع الأرقام كلياً (حروف بس
        — زي اسم الوكالة)؛ افتراضياً True (حروف وأرقام معاً، زي اسم
        الراكب ورقم الجواز)."""
        kwargs = self._base_entry_kwargs()

        def char_ok(c):
            if c.isascii() and c.isalpha():
                return True
            if allow_digits and c.isascii() and c.isdigit():
                return True
            return allow_space and c == " "

        def validate(P):
            if maxlen is not None and len(P) > maxlen:
                return False
            return all(char_ok(c) for c in P)

        vcmd = (self.register(validate), "%P")
        e = tk.Entry(self.canvas, textvariable=var, validate="key", validatecommand=vcmd, **kwargs)
        self._add_hover(e, var)
        # ما ينطبق لمجرد Alt+Tab من برنامج آخر (راجع الملاحظة بـ_entry).
        e.bind("<FocusIn>", lambda _ev: select_all_on_real_focus(e))
        bind_triple_click_select_all(e)
        bind_enter_advances_focus(e)
        if maxlen is not None:
            bind_advance_on_maxlen(e, var, maxlen)

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
        bind_triple_click_select_all(e)
        bind_enter_advances_focus(e)

        def format_on_leave(_ev=None):
            raw = var.get().strip()
            if not raw:
                return
            sep = "," if "," in raw else ("." if "." in raw else None)
            int_part, dec_part = raw.split(sep, 1) if sep else (raw, "")
            if (int_part and not int_part.isdigit()) or (dec_part and not dec_part.isdigit()):
                # فيه أكثر من فاصل (زي "1.234,56" منسَّق أصلاً بفاصل آلاف)
                # أو محتوى غير متوقّع — نتجاهله، ما نلمسه.
                return
            int_part = int_part or "0"
            dec_part = (dec_part + "0" * decimals)[:decimals]
            formatted = f"{int(int_part):,}".replace(",", ".") + "," + dec_part
            if formatted == raw:
                # منسَّق أصلاً بالضبط (زي taux تحت الألف اللي ما يحتاج فاصل
                # آلاف إطلاقاً، فيبقى فيه فاصلة عشرية بس بلا نقطة، والفحص
                # القديم كان يفوته) — لازم نتجاهله صراحة، وإلا var.set()
                # يعيد إطلاق trace الكتابة بلا داعي (خطر حقيقي الآن: يعيد
                # حساب Soit/Montant en devise أوتوماتيكياً بمجرد ما تبعد
                # عن حقل taux، حتى لو ما كتبت فيه شي جديد).
                return
            var.set(formatted)
            # Tk يعطّل "validate" أوتوماتيكياً (يرجعه "none") بمجرد ما
            # نغيّر النص برمجياً (var.set) بدل كتابة حقيقية — لازم
            # نرجّعه "key" يدوياً، وإلا القيود (الحد الأقصى...) تنعطّل
            # نهائياً بعد أول تنسيق.
            e.configure(validate="key")

        e.bind("<FocusOut>", format_on_leave, add="+")
        # دبل-كليك يحدّد جزءاً وحيداً بس (الصحيح قبل الفاصلة، أو العشري
        # بعدها) حسب مكان النقرة — نفس مبدأ حقل Obtent بالضبط (راجع
        # MaskedDateEntry._select_segment_at بـui.common.widgets)، مُطبَّق
        # هنا على كل حقول المبالغ (EUR/DZD/taux) لأنها الثلاثة تُبنى من
        # نفس هالدالة.
        e.bind("<Double-Button-1>", lambda ev: self._select_currency_segment(e, e.index(f"@{ev.x}")))
        return e

    def _select_currency_segment(self, entry, idx):
        """دبل-كليك بحقل مبلغ: يحدّد الجزء الصحيح (قبل الفاصلة العشرية)
        أو الجزء العشري (بعدها) بس — حسب مكان النقرة (idx: فهرس الحرف
        الأقرب لمكان النقرة). لو ماكو فاصلة أصلاً بعد (لسا رقم صحيح بلا
        كسور)، يحدد كل شي (ماكو قطعتين نفرّق بينهم أصلاً).

        الفاصلة العشرية دائماً "," (لو موجودة "." كمان فهي فاصل آلاف —
        نستخدم rindex حتى نلقط الفاصلة الأخيرة، الحقيقية، لا أي نقطة
        آلاف قبلها). أثناء الكتابة الخام (قبل التنسيق النهائي) ممكن
        الفاصل يكون "." بدل "," (المستخدم يقدر يكتب بالاثنين) — نتحقق
        من "," أولاً، وإلا نجرّب "."."""
        text = entry.get()
        if "," in text:
            sep = text.rindex(",")
        elif "." in text:
            sep = text.index(".")
        else:
            entry.select_range(0, tk.END)
            entry.icursor(tk.END)
            return "break"
        start, end = (0, sep) if idx <= sep else (sep + 1, len(text))
        entry.select_range(start, end)
        entry.icursor(end)
        return "break"

    def _add_hover(self, widget, var=None):
        """يظهر إطار أزرق ثابت طول ما الفأرة فوق الخانة، ويختفي لما الفأرة
        تبعد — إشارة بصرية بسيطة إنها قابلة للكتابة، بدون وميض.

        var (اختياري): لو انعطى، خلفية الخانة الفاضية تاخذ تلوين خفيف
        دائم (حتى بدون تحويم الفأرة) — يميّز مكان الكتابة قبل التعبئة
        بوضوح (بلون الخلفية نفسه، أوضح من مجرد حد رفيع حول الخانة).
        بمجرد ما تُكتب فيها، الخلفية ترجع بيضاء عادية (تندمج مع الورقة)."""

        def set_idle():
            widget.configure(highlightbackground=HOVER_IDLE_COLOR, highlightcolor=HOVER_IDLE_COLOR)
            if var is not None:
                is_empty = not (var.get() or "").strip()
                widget.configure(bg=EMPTY_BG_COLOR if is_empty else FILLED_BG_COLOR)

        def on_enter(_event):
            widget.configure(highlightbackground=HOVER_ON_COLOR, highlightcolor=HOVER_ON_COLOR)

        def on_leave(_event):
            set_idle()

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        set_idle()
        if var is not None:
            var.trace_add("write", lambda *a: set_idle())
