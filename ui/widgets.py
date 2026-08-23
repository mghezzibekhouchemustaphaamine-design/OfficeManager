"""
ويدجت مخصصة: حقل تاريخ وحقل وقت "ذكيين" — تكتب الأرقام متتالية بدون
فواصل (/ أو :) وهو يقسّمها أوتوماتيكياً (يوم/شهر/سنة أو ساعة:دقيقة).
بدون أي زر تقويم — الكتابة اليدوية بس.
"""
import re
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime

from tkinter import ttk

from ui.cd_document import FRENCH_MONTHS

# نفس شكل الخانات العادية بالشاشة (بدون إطار ظاهر افتراضياً، Courier صغير)
_ENTRY_STYLE = dict(
    bd=0, relief="flat", bg="white", highlightthickness=1,
    highlightbackground="white", highlightcolor="white",
    font=("Courier New", 9), justify="left",
)


class MaskedDateEntry(tk.Frame):
    """حقل تاريخ يُكتب فيه بالأرقام فقط (تنسيق تلقائي DD/MM/YYYY)."""

    def __init__(self, parent, default_today=True):
        # tk.Frame لا ttk.Frame: خلفية ttk.Frame الافتراضية رمادية (لون
        # النظام SystemButtonFace) وتبين كفاصل رمادي واضح فوق ورقة بيضاء —
        # tk.Frame العادي يقبل bg="white" مباشرة فيندمج تماماً مع الصفحة.
        super().__init__(parent, bg="white", highlightthickness=0)
        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, width=12, **_ENTRY_STYLE)
        self.entry.pack(side="left")
        self.entry.bind("<KeyRelease>", self._on_key)
        # رجوع للخانة بعد ما كانت معبّأة: نُبرز القيمة كاملة بدل ما نمسحها،
        # وأول رقم يُكتب يستبدلها أوتوماتيكياً (Entry عادية، Tk يتكفّل).
        self.entry.bind("<FocusIn>", lambda _ev: (self.entry.select_range(0, tk.END), self.entry.icursor(tk.END)))

        if default_today:
            self.var.set(date.today().strftime("%d/%m/%Y"))

    def _on_key(self, event):
        raw = self.var.get()
        digits = "".join(ch for ch in raw if ch.isdigit())[:8]
        formatted = digits[:2]
        if len(digits) > 2:
            formatted += "/" + digits[2:4]
        if len(digits) > 4:
            formatted += "/" + digits[4:8]
        if formatted != raw:
            self.var.set(formatted)
            self.entry.icursor(tk.END)

    def get_date(self):
        """يرجّع كائن date، أو يرمي ValueError لو التاريخ ناقص/غلط."""
        return datetime.strptime(self.var.get(), "%d/%m/%Y").date()


# فترات دوام العمل المسموحة (بالدقيقة من بداية اليوم): 09:00–11:59
# و13:15–15:47 — أي وقت خارج هالفترتين مرفوض بالكامل (يمنع أي وقت قبل
# 09:00، وفترة الراحة 12:00–13:14، وأي وقت من 15:48 لغاية 09:00 الصبح
# التالي)، حسب طلبك بالضبط.
_ALLOWED_TIME_WINDOWS = [(9 * 60, 11 * 60 + 59), (13 * 60 + 15, 15 * 60 + 47)]


def _time_allowed(hour, minute):
    total = hour * 60 + minute
    return any(lo <= total <= hi for lo, hi in _ALLOWED_TIME_WINDOWS)


class MaskedTimeEntry(tk.Frame):
    """حقل وقت (HH:MM) يقبل فقط أوقات ضمن دوام العمل: 09:00–11:59 أو
    13:15–15:47. أي رقم يؤدي لوقت خارج هالفترتين يُرفض فوراً أثناء
    الكتابة (زي ما اليوم/الشهر يرفضان قيمة غير صالحة)، مو بعد الانتهاء."""

    def __init__(self, parent, default_now=True):
        # tk.Frame لا ttk.Frame: نفس سبب MaskedDateEntry أعلاه (خلفية بيضاء
        # صريحة بدل رمادي النظام الافتراضي لـttk.Frame).
        super().__init__(parent, bg="white", highlightthickness=0)
        self.var = tk.StringVar()
        self._hour_digits = ""
        self._minute_digits = ""
        self._fresh = False  # true بعد الرجوع للخانة: أول رقم يبدأ من جديد
        self.entry = tk.Entry(self, textvariable=self.var, width=5, **_ENTRY_STYLE)
        self.entry.pack(side="left")
        self.entry.bind("<Key>", self._on_key)
        self.entry.bind("<FocusIn>", self._on_focus_in)

        if default_now:
            now = datetime.now()
            if _time_allowed(now.hour, now.minute):
                self._hour_digits = f"{now.hour:02d}"
                self._minute_digits = f"{now.minute:02d}"
                self._refresh()

    def _refresh(self):
        text = self._hour_digits
        if self._minute_digits:
            text += ":" + self._minute_digits
        self.var.set(text)

    def _on_focus_in(self, _event):
        # رجوع للخانة بعد ما كانت معبّأة: نُبرز (نحدّد) القيمة الحالية
        # بدل ما نمسحها — تبقى ظاهرة وما تنفقد لو نقرت بالغلط أو ضغطت
        # Tab بدون كتابة. أول رقم يكتبه بعدها يبدأ قيمة جديدة تلقائياً.
        self.entry.select_range(0, tk.END)
        self.entry.icursor(tk.END)
        self._fresh = True

    def _on_key(self, event):
        if event.keysym == "BackSpace":
            if self._fresh:
                self._hour_digits = ""
                self._minute_digits = ""
            elif self._minute_digits:
                self._minute_digits = self._minute_digits[:-1]
            else:
                self._hour_digits = self._hour_digits[:-1]
            self._fresh = False
            self._refresh()
            return "break"
        if event.keysym == "Delete":
            self._hour_digits = ""
            self._minute_digits = ""
            self._fresh = False
            self._refresh()
            return "break"
        if event.char and event.char.isdigit():
            if self._fresh:
                self._hour_digits = ""
                self._minute_digits = ""
                self._fresh = False
            if len(self._hour_digits) < 2:
                candidate = self._hour_digits + event.char
                if len(candidate) == 1:
                    self._hour_digits = candidate
                else:
                    # ساعة كاملة (رقمين): تُقبل فقط لو فيه دقيقة واحدة
                    # ع الأقل تجعلها ضمن فترات الدوام (زي 13 مقبولة لأن
                    # 13:15+ صالحة، حتى لو 13:00 لحالها مو صالحة).
                    hour = int(candidate)
                    if any(_time_allowed(hour, m) for m in range(60)):
                        self._hour_digits = candidate
                self._refresh()
            elif len(self._minute_digits) < 2:
                hour = int(self._hour_digits)
                candidate = self._minute_digits + event.char
                if len(candidate) == 1:
                    # أول رقم بالدقيقة: يُقبل فقط لو فيه رقم ثاني ممكن
                    # يكمّلها لدقيقة صالحة مع هالساعة بالذات.
                    ok = any(
                        f"{m:02d}"[0] == candidate and _time_allowed(hour, m)
                        for m in range(60)
                    )
                else:
                    ok = _time_allowed(hour, int(candidate))
                if ok:
                    self._minute_digits = candidate
                self._refresh()
            return "break"
        if event.char and event.char.isprintable():
            return "break"
        return None

    def get_time_str(self):
        """يرجّع النص "HH:MM"، أو يرمي ValueError لو الوقت ناقص/خارج
        فترات الدوام المسموحة."""
        val = self.var.get()
        if not re.fullmatch(r"\d{2}:\d{2}", val):
            raise ValueError("وقت غير صحيح")
        hour, minute = (int(part) for part in val.split(":"))
        if not _time_allowed(hour, minute):
            raise ValueError("الوقت خارج فترات الدوام المسموحة")
        return val


class SplitDateEntry(tk.Frame):
    """
    حقل تاريخ مقسّم لـ3 خانات مستقلة (يوم / شهر / سنة)، كل وحدة تتعامل
    لحالها:

    - اليوم: رقمين بالضبط، يقبل قيم 1-31 بس. صفر أول (زي "09") يُكتب
      عادي أثناء الكتابة، ويُشال أوتوماتيكياً لما تبعد عن الخانة (يصير
      "9"). بمجرد ما يكتمل رقمين، التركيز ينتقل أوتوماتيكياً لخانة
      الشهر.
    - الشهر: رقمين، يقبل 1-12 بس. يتحوّل تلقائياً لاسم الشهر بالفرنسية
      بمجرد ما تكتمل قيمة صحيحة وواضحة (رقم واحد لـ2-9، أو رقمين لأي
      شهر) — بدون ما تحتاج تبعد عن الخانة — والتركيز ينتقل أوتوماتيكياً
      لخانة السنة بنفس اللحظة. خانة السنة نفسها تتحرك تلقائياً لتوقف
      مباشرة بعد آخر حرف من اسم الشهر المكتوب، بفاصل مسافتين بالضبط
      (نفس تباعد السطر الحقيقي بالمستند)، بغض النظر عن طول اسم الشهر.
    - Enter أو Tab بأي خانة (يوم/شهر) يتصرفان بنفس الشيء: يثبّتان أفضل
      قيمة ممكنة (زي فقدان التركيز) وينتقلان للخانة اللي بعدها مباشرة.
    - السنة: 4 أرقام بالضبط.
    - لو اليوم/الشهر/السنة الثلاثة معبّأة لكن تركيبتها مستحيلة تقويمياً
      (زي 31 فبراير)، الخانات الثلاث تتلوّن بخلفية حمراء خفيفة كتنبيه
      بصري فوري — بدل ما تختفي بصمت بالمستند النهائي بدون تفسير.
    """

    _NORMAL_BG = "white"
    _INVALID_BG = "#fbe3e3"
    _DAY_MONTH_GAP_PX = 4  # فراغ بكسل بين اليوم والشهر (يقابل مسافة واحدة)

    def __init__(self, parent, default_today=True):
        # tk.Frame لا ttk.Frame: خلفية ttk.Frame الافتراضية رمادية (لون
        # النظام SystemButtonFace) وتبين كفاصل رمادي واضح بين اليوم/الشهر/
        # السنة فوق الورقة البيضاء — tk.Frame العادي يقبل bg="white" مباشرة.
        super().__init__(parent, bg="white", highlightthickness=0)

        # لما ننتقل تلقائياً للخانة اللي بعدها (اكتمال يوم/شهر، أو Enter/
        # Tab) هذا "مرور للأمام" مو "رجوع للتعديل" — ما نفضّي محتوى الخانة
        # الجاية لو كانت معبّأة مسبقاً (مثلاً تصحيح الشهر بتاريخ مكتمل ما
        # يمسح السنة الصحيحة الموجودة أصلاً). قائمة (مو علم واحد) لأن
        # Tk يؤخّر تسليم أحداث FocusIn/Out الحقيقية عن وقت استدعاء
        # focus_set() نفسه (لو صار أكثر من انتقال قبل ما توصل الأحداث
        # المؤجّلة، علم واحد ينستهلك بالخانة الغلط)؛ كل خانة تستهلك فقط
        # إدخالها هي بالذات.
        self._suppress_focus_targets = []

        self.day_var = tk.StringVar()
        self._day_digits = ""
        self._day_fresh = False  # true بعد الرجوع للخانة: أول رقم يبدأ من جديد
        # محاذاة لليمين: رقم واحد (زي "5") لازم يبين ملاصق لنهاية الخانة
        # مباشرة، حتى الفراغ بينه وبين خانة الشهر يبقى مسافة واحدة بالضبط
        # (نفس "5 Mai" بالمستند الحقيقي) — لا مسافتين (خانة فاضية + فراغ).
        day_style = dict(_ENTRY_STYLE, justify="right")
        self.day_entry = tk.Entry(self, textvariable=self.day_var, width=2, **day_style)
        self.day_entry.pack(side="left")
        self.day_entry.bind("<Key>", self._on_day_key)
        self.day_entry.bind("<FocusIn>", self._on_day_focus_in)
        self.day_entry.bind("<FocusOut>", self._on_day_blur)
        self.day_entry.bind("<Return>", self._day_advance)
        self.day_entry.bind("<Tab>", self._day_advance)
        # على ويندوز، Shift+Tab يوصل بنفس keysym تبع Tab العادي (الفرق
        # بس بحالة Shift بالـstate) — فربط <Tab> لحاله كان يمسك Shift+Tab
        # كمان ويفرض التقدّم للأمام دايماً، ويمنع الرجوع للخلف نهائياً.
        # ربط <Shift-Tab> صراحة (أكثر تحديداً) بدالة ما تسوي شي (ترجع
        # None) يخلي Tk يفضّلها بدل <Tab>، فيسمح للتنقّل الافتراضي للخلف
        # يشتغل عادي (وأي رجوع بيوصل عبره يفعّل التحديد الكامل تلقائياً
        # عبر <FocusIn> العادي، بدون أي تدخل إضافي).
        self.day_entry.bind("<Shift-Tab>", lambda _e: None)

        self.month_var = tk.StringVar()
        self._month_digits = ""
        self._month_letters = ""  # الأحرف المكتوبة يدوياً (وضع الكتابة بالاسم، لا بالرقم)
        self._month_fresh = False  # true بعد الرجوع للخانة: أول رقم يبدأ من جديد
        # عرض 3 أحرف افتراضياً (زي "Mai") — يتوسّع أوتوماتيكياً (_set_month_display)
        # لأي اسم شهر أطول فعلاً مكتوب (زي "Septembre")، ويرجع 3 لما تُفرّغ.
        self.month_entry = tk.Entry(self, textvariable=self.month_var, width=3, **_ENTRY_STYLE)
        self.month_entry.pack(side="left", padx=(self._DAY_MONTH_GAP_PX, 0))
        self.month_entry.bind("<Key>", self._on_month_key)
        self.month_entry.bind("<FocusIn>", self._on_month_focus_in)
        self.month_entry.bind("<FocusOut>", self._on_month_blur)
        self.month_entry.bind("<Return>", self._month_advance)
        self.month_entry.bind("<Tab>", self._month_advance)
        self.month_entry.bind("<Shift-Tab>", lambda _e: None)  # راجع شرح اليوم أعلاه

        self.year_var = tk.StringVar()
        year_vcmd = (self.register(lambda P: P == "" or (P.isdigit() and len(P) <= 4)), "%P")
        self.year_entry = tk.Entry(
            self, textvariable=self.year_var, width=4, validate="key", validatecommand=year_vcmd,
            **_ENTRY_STYLE,
        )
        # السنة تتموضع بمكان مطلق (place) بدل التتابع العادي (pack)، حتى
        # تقدر تتحرك حياً حسب طول اسم الشهر الفعلي المكتوب.
        self.year_entry.place(x=0, y=0)
        self.year_entry.bind("<FocusIn>", self._on_year_focus_in)
        self.year_var.trace_add("write", lambda *a: self.reposition_year())
        self.pack_propagate(False)

        # حرف "a" جزء حقيقي من نفس الودجت (سطر/جملة واحدة مع اليوم/الشهر/
        # السنة)، مو عنصر منفصل يُحسب مكانه من الخارج — يمنع أي خلل توقيت
        # أو تصادم، ويضمن يبقى دائماً ملتصق بنهاية التاريخ فعلياً.
        self.a_label = tk.Label(
            self, text="a", bg="white", font=("Courier New", 9), highlightthickness=0,
        )

        # قائمة موحّدة بكل عناصر الكتابة/العرض الداخلية، حتى تنضبط خصائصها
        # (كالخط عند تغيير الزوم) بنفس طريقة باقي حقول الشاشة.
        self.entries = [self.day_entry, self.month_entry, self.year_entry, self.a_label]

        if default_today:
            d = date.today()
            self._day_digits = str(d.day)
            self.day_var.set(self._day_digits)
            self._month_digits = f"{d.month:02d}"
            self._set_month_display(FRENCH_MONTHS[d.month - 1])
            self.year_var.set(f"{d.year:04d}")

        self.after_idle(self.reposition_year)

    def _set_month_display(self, text):
        """يحدّث نص خانة الشهر وعرضها الفعلي معاً: 3 أحرف افتراضياً
        (زي "Mai")، تتوسّع تلقائياً لو النص المكتوب أطول (زي "Septembre")
        وترجع 3 لما يُفرّغ الحقل — بدون أي قصّ أو تمرير مخفي للنص."""
        self.month_var.set(text)
        self.month_entry.configure(width=max(3, len(text)))

    def _advance_focus(self, widget):
        """ينتقل للخانة widget مع تعطيل تفضيتها (مرور للأمام، مو رجوع
        للتعديل) — راجع شرح _suppress_focus_targets بالأعلى."""
        self._suppress_focus_targets.append(widget)
        widget.focus_set()

    def _consume_suppress(self, widget):
        if widget in self._suppress_focus_targets:
            self._suppress_focus_targets.remove(widget)
            return True
        return False

    # ---------- اليوم ----------
    def _on_day_key(self, event):
        if event.keysym == "BackSpace":
            self._day_digits = "" if self._day_fresh else self._day_digits[:-1]
            self._day_fresh = False
            self.day_var.set(self._day_digits)
            self._validate()
            return "break"
        if event.keysym == "Delete":
            self._day_digits = ""
            self._day_fresh = False
            self.day_var.set("")
            self._validate()
            return "break"
        if event.char and event.char.isdigit():
            base = "" if self._day_fresh else self._day_digits
            self._day_fresh = False
            candidate = base + event.char
            if len(candidate) == 1 or (len(candidate) == 2 and 1 <= int(candidate) <= 31):
                self._day_digits = candidate
                self.day_var.set(self._day_digits)
                if len(candidate) == 2:
                    # اليوم اكتمل (رقمين) -> ننتقل أوتوماتيكياً لخانة الشهر
                    self.after_idle(lambda: self._advance_focus(self.month_entry))
            self._validate()
            return "break"
        if event.char and event.char.isprintable():
            return "break"
        return None

    def _on_day_blur(self, _event):
        if len(self._day_digits) == 2 and self._day_digits.startswith("0"):
            self._day_digits = str(int(self._day_digits))
            self.day_var.set(self._day_digits)

    def _on_day_focus_in(self, _event):
        # رجوع للخانة بعد ما كانت معبّاة: نُبرز (نحدّد) القيمة الحالية
        # بدل ما نمسحها فوراً — تبقى ظاهرة وواضحة إنها قابلة للاستبدال،
        # وما تنفقد لو المستخدم بس نقر بالغلط أو ضغط Tab/Enter بدون
        # كتابة. أول رقم يكتبه بعدها يبدأ قيمة جديدة تلقائياً (بدون
        # حاجة لحذف بالسهم يدوياً). ما ينطبق لو التركيز جالها بانتقال
        # تلقائي للأمام (راجع شرح _suppress_focus_targets).
        if self._consume_suppress(self.day_entry):
            return
        self.day_entry.select_range(0, tk.END)
        self.day_entry.icursor(tk.END)
        self._day_fresh = True

    def _day_advance(self, _event):
        """Enter أو Tab بخانة اليوم: ثبّت القيمة وانتقل لخانة الشهر."""
        self._on_day_blur(None)
        self._advance_focus(self.month_entry)
        return "break"

    # ---------- الشهر ----------
    def _on_month_key(self, event):
        if event.keysym == "BackSpace":
            if self._month_fresh:
                self._month_digits = ""
                self._month_letters = ""
            elif self._month_letters:
                # بوضع الكتابة بالاسم: نحذف آخر حرف من الاسم
                self._month_letters = self._month_letters[:-1]
            else:
                self._month_digits = self._month_digits[:-1]
            self._month_fresh = False
            if self._month_letters:
                self._refresh_month_letters()
            else:
                self._refresh_month()
            return "break"
        if event.keysym == "Delete":
            self._month_digits = ""
            self._month_letters = ""
            self._month_fresh = False
            self._set_month_display("")
            self.reposition_year()
            return "break"
        if event.char and event.char.isdigit():
            base = "" if self._month_fresh else self._month_digits
            self._month_fresh = False
            self._month_letters = ""
            candidate = base + event.char
            if len(candidate) == 1 or (len(candidate) == 2 and 1 <= int(candidate) <= 12):
                self._month_digits = candidate
                complete = self._refresh_month()
                if complete:
                    # الشهر تحدد ووضح (رقم وحيد غير ملتبس أو رقمين) ->
                    # ننتقل أوتوماتيكياً لخانة السنة فوراً.
                    self.after_idle(lambda: self._advance_focus(self.year_entry))
            return "break"
        if event.char and event.char.isalpha():
            # كتابة اسم الشهر مباشرة بالحروف (زي "se" -> "Septembre")،
            # بديل عن الكتابة بالرقم: كل حرف يضيّق قائمة الأشهر المطابقة
            # لبدايته، وبمجرد ما يبقى شهر وحيد ممكن، يكتمل اسمه أوتوماتيكياً
            # وينتقل التركيز للسنة — نفس سلوك الرقم بالضبط. حرف يخلي القائمة
            # فاضية كلياً (ما فيه شهر يبدأ بيه) يُرفض فوراً ولا يُكتب.
            base = "" if self._month_fresh else self._month_letters
            self._month_fresh = False
            self._month_digits = ""
            candidate = base + event.char
            if any(m.lower().startswith(candidate.lower()) for m in FRENCH_MONTHS):
                self._month_letters = candidate
                complete = self._refresh_month_letters()
                if complete:
                    self.after_idle(lambda: self._advance_focus(self.year_entry))
            return "break"
        if event.char and event.char.isprintable():
            return "break"
        return None

    def _refresh_month(self):
        digits = self._month_digits
        # رقم واحد يكفي لـ2-9 (ما فيه شهر يبدأ بيهم غيرهم)، و0/1 ينتظرون
        # رقم ثاني (01-09 أو 10-12).
        complete = len(digits) == 2 or (len(digits) == 1 and digits in "23456789")
        if complete:
            self._set_month_display(FRENCH_MONTHS[int(digits) - 1])
        else:
            self._set_month_display(digits)
        self.reposition_year()
        return complete

    def _refresh_month_letters(self):
        """يضيّق قائمة الأشهر المطابقة للأحرف المكتوبة، ويكمّل الاسم
        أوتوماتيكياً بمجرد ما يبقى احتمال وحيد (زي "se" -> "Septembre"،
        أو "juin" لازم 4 أحرف لأنها تشترك بـ"jui" مع "Juillet")."""
        letters = self._month_letters
        matches = [m for m in FRENCH_MONTHS if m.lower().startswith(letters.lower())]
        if len(matches) == 1 and letters:
            month_name = matches[0]
            self._month_digits = f"{FRENCH_MONTHS.index(month_name) + 1:02d}"
            self._set_month_display(month_name)
            self.reposition_year()
            return True
        self._set_month_display(letters.capitalize())
        self.reposition_year()
        return False

    def _on_month_blur(self, _event):
        if self._month_digits and self.month_var.get() == self._month_digits:
            # لسا رقم خام (ما كمّل لحالة واضحة)، نثبّته كأحسن تخمين ممكن
            month_num = int(self._month_digits)
            if 1 <= month_num <= 12:
                self._set_month_display(FRENCH_MONTHS[month_num - 1])
                self.reposition_year()

    def _month_advance(self, _event):
        """Enter أو Tab بخانة الشهر: أظهر اسم الشهر وانتقل لخانة السنة."""
        self._on_month_blur(None)
        self._advance_focus(self.year_entry)
        return "break"

    def _on_month_focus_in(self, _event):
        # نفس مبدأ اليوم: نُبرز القيمة الحالية بدل ما نمسحها، وأول رقم
        # يبدأ قيمة جديدة. ما ينطبق لانتقال تلقائي للأمام (راجع الشرح).
        if self._consume_suppress(self.month_entry):
            return
        self.month_entry.select_range(0, tk.END)
        self.month_entry.icursor(tk.END)
        self._month_fresh = True

    def _on_year_focus_in(self, _event):
        # ما ينطبق لو التركيز جالها بانتقال تلقائي للأمام (راجع الشرح).
        # خانة السنة Entry عادية — تحديد كامل النص يكفي؛ Tk نفسه يستبدل
        # المحدَّد أوتوماتيكياً بأول رقم يُكتب (بدون أي مسح يدوي منا).
        if self._consume_suppress(self.year_entry):
            return
        self.year_entry.select_range(0, tk.END)
        self.year_entry.icursor(tk.END)

    def reposition_year(self):
        """يحرّك خانة السنة لتوقف مباشرة بعد آخر حرف من نص الشهر الحالي
        (بغض النظر عن طوله)، بفاصل مسافتين بالضبط — نفس التباعد المستخدم
        بسطر التاريخ الحقيقي بالمستند. وبعدها حرف "a" (جزء من نفس الودجت،
        مو عنصر منفصل) يتموضع مباشرة بعد آخر حرف من نص السنة المكتوب
        فعلياً، بفاصل مسافة واحدة — كل هذا سطر/جملة واحدة متماسكة."""
        self.update_idletasks()
        month_font = tkfont.Font(font=self.month_entry.cget("font"))
        # نأخذ الأكبر بين عرض النص المكتوب فعلاً وعرض الخانة المرسومة
        # (max، بالاعتماد على winfo_reqwidth لا winfo_width — الأول يرجّع
        # الحجم الصحيح دائماً حتى قبل ما تُرسم النافذة فعلياً على الشاشة،
        # بينما الثاني يرجّع 1px وهمي أول ما تُفتح الشاشة قبل ما تُرسم،
        # وهذا بالضبط كان يخلي السنة تتموضع فوق خانة الشهر الفاضية —
        # تظهر ملتصقة بيها — لحد ما تكتب أول حرف ويصحح نفسه). قبل ما تُكتب
        # أي حروف يكون قياس النص صفر، فلو اعتمدنا عليه لحاله كانت السنة
        # تتموضع فوق الخانة الفاضية نفسها؛ بعد ما تُكتب، القياسان يتقاربون
        # فيبقى التتبّع الحي لطول اسم الشهر شغّال متل ما هو.
        text_w = max(month_font.measure(self.month_var.get()), self.month_entry.winfo_reqwidth())
        gap_w = month_font.measure("  ")
        # موضع بداية خانة الشهر نفسه نحسبه تحليلياً من عرض خانة اليوم
        # المطلوب (reqwidth) + فراغ اليوم-الشهر الثابت، بدل الاعتماد على
        # month_entry.winfo_x() — لأن إحداثي X الفعلي لعنصر مرتّب بـpack()
        # ما يستقر إلا بعد ما تُرسم النافذة فعلياً على الشاشة (متل مشكلة
        # winfo_width أعلاه بالضبط)، فأول فتحة للتبويب (قبل أي كتابة) كان
        # يُقرأ 0 دائماً ويخلي كل شيء يتراكب فوق بعضه.
        month_x = self.day_entry.winfo_reqwidth() + self._DAY_MONTH_GAP_PX
        year_x = month_x + text_w + gap_w
        self.year_entry.place_configure(x=year_x, y=0)

        year_font = tkfont.Font(font=self.year_entry.cget("font"))
        year_w = max(year_font.measure(self.year_var.get()), self.year_entry.winfo_reqwidth())
        a_x = year_x + year_w + year_font.measure(" ")
        self.a_label.place_configure(x=a_x, y=0)

        a_font = tkfont.Font(font=self.a_label.cget("font"))
        total_w = a_x + a_font.measure("a")
        height = self.day_entry.winfo_reqheight()
        self.configure(width=int(total_w) + 4, height=height)

        self._validate()

    def _validate(self):
        """يتحقق لو اليوم/الشهر/السنة الثلاثة معبّأة تشكّل تاريخاً ممكناً
        فعلياً تقويمياً، ويلوّن الخانات الثلاث بالأحمر الخفيف لو لا —
        مو خطأ بالكتابة (كل رقم لحاله صالح)، بس التركيبة نفسها مستحيلة
        (زي يوم 31 بشهر فبراير)."""
        year_s = self.year_var.get()
        complete = bool(self._day_digits) and bool(self._month_digits) and len(year_s) == 4
        invalid = False
        if complete:
            try:
                date(int(year_s), int(self._month_digits), int(self._day_digits))
            except ValueError:
                invalid = True
        bg = self._INVALID_BG if invalid else self._NORMAL_BG
        for entry in (self.day_entry, self.month_entry, self.year_entry):
            entry.configure(bg=bg)

    def a_right_edge_px(self):
        """أقصى نقطة يمين (بالبكسل الحقيقي) لحرف "a" — تُستخدم من الشاشة
        الخارجية فقط لمعرفة أين يبدأ حقل الوقت (اللي بعده مباشرة بمسافة)،
        بدون ما تحتاج الشاشة الخارجية تعيد حساب مكان "a" بنفسها."""
        self.update_idletasks()
        font = tkfont.Font(font=self.a_label.cget("font"))
        return self.a_label.winfo_x() + font.measure("a")

    # ---------- الجمع النهائي ----------
    def get_date(self):
        """يرجّع كائن date، أو يرمي ValueError لو التاريخ ناقص/غلط."""
        year_s = self.year_var.get()
        if not self._day_digits or not self._month_digits or len(year_s) != 4:
            raise ValueError("تاريخ غير صحيح")
        return date(int(year_s), int(self._month_digits), int(self._day_digits))
