"""كشف الراتب الشهري / Bulletin de paie — شاشة مستقلّة بنمط CD (سيدي).

الحقول تُكتب فوق الاستمارة مباشرة (لا شريط إدخال جانبي للبيانات):
  - الجزء الثابت (أسود على أبيض): الاستمارة — تسميات، خطوط، شريط
    العنوان، أكواد ومسمّيات الأسطر الثابتة.
  - الجزء الذي يُملأ (خانات فوق الاستمارة): بيانات المكتب والأجير،
    القاعدي، المنح، panier/transport، الاقتطاعات.
  - الجزء المحسوب تلقائياً (أزرق): CNAS 9٪، IRG (خوارزمية DGI الرسمية)،
    TOTAL، NET À PAYER — يتغيّر مع كل حرف.

التنقّل والاختصارات على غرار CD: Tab / Enter للحقل التالي، Shift+Tab
للسابق، تحديد كامل عند الرجوع لحقل ممتلئ، إطار أزرق عند التحويم/التركيز،
انتقال تلقائي عند حسم الحقل (الشهر) أو امتلائه (السنة). شريط جانبي (يمين)
للزوم + الموديل + وضع الزبون + خيار IRG + الأزرار.
"""
import dataclasses
import os
import re
from datetime import date
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from programme import database, paths
from ui.common import alerts
from ui.common.client_picker import ClientPickerEntry
from ui.common.widgets import (
    EMPTY_BG_COLOR, FILLED_BG_COLOR, bind_triple_click_select_all,
)
from ui.hr.constants import MOIS_FR
from ui.hr.paie import calc, registry, template_simple
from ui.hr.render import TemplateNotReady

_HOVER_IDLE = "white"
_HOVER_ON = "#4a90d9"
_BAND_BG = "#111111"   # لون الشريط الأسود (نفسه في template_simple.paint_form)
_INK = "#202124"       # لون كتابة الحقول (نفس لون نص الاستمارة المرسوم)
# نفس خط النموذج المرسوم (لا Courier) حتى تطابق الكتابة مظهر الأصل
_ENTRY_FONT = template_simple.FORM_FONT

_MOIS_UP = [m.upper() for m in MOIS_FR]


# المسافة (بكسل) من أعلى إطار tk.Entry (bd=0، highlightthickness=1) إلى
# خط أساس نصّه، بعد طرح ascent: حلقة التركيز (1) + هامش tk.Entry الرأسي
# الداخلي الثابت YPAD (1) = 2 — قيمة دقيقة من tkEntry.c لا تخمين، ولا
# تتغيّر مع الزوم. تصحّ فقط لو الإطار بارتفاعه الطبيعي؛ فرض ارتفاع أكبر
# يوسّط النص فيه ويزيح خط الأساس للأسفل (والإزاحة تكبر مع الزوم) — لذا
# خانات خط الأساس تأخذ height=0 (طبيعي) في _relayout.
_ENTRY_TOP_CHROME = 2


def _titlecase(s):
    """أول حرف من كل كلمة كبير والباقي صغير — بعد المسافة والشرطة."""
    return re.sub(r"(^|[ \-])([^\W\d_])",
                  lambda m: m.group(1) + m.group(2).upper(), s.lower())


def _num(value):
    s = str(value or "").strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _safe(text):
    out = re.sub(r"[^\w\- ]+", "", str(text or ""), flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", out) or "SN"


def _month_matches(prefix):
    p = prefix.upper()
    return [m for m in _MOIS_UP if m.startswith(p)]


def _resolve_month(text):
    """يرجّع اسم الشهر بأحرف كبيرة لو مُحسَم، وإلا None."""
    t = text.strip()
    if not t:
        return None
    if t.isdigit():
        if len(t) == 1:
            return _MOIS_UP[int(t) - 1] if t in ("2", "3", "4", "5", "6", "7", "8", "9") else None
        if t in ("10", "11", "12"):
            return _MOIS_UP[int(t) - 1]
        return None
    matches = _month_matches(t)
    return matches[0] if len(matches) == 1 else None


def _group_digits(digits, sizes):
    """يقسّم سلسلة أرقام لمجموعات بأحجام sizes (الفائض في مجموعة أخيرة)."""
    out, i = [], 0
    for s in sizes:
        if i >= len(digits):
            break
        out.append(digits[i:i + s])
        i += s
    if i < len(digits):
        out.append(digits[i:])
    return out


# حقول أرقام مجمَّعة بنفس المنطق (رقم خام أثناء الكتابة، صيغة منسَّقة عند
# المغادرة، مفتاح «/XX» اختياري لا يُقبل إلا بعد اكتمال الجزء الأساسي،
# لا نقل أرقام عبر «/»، المسافات و«/» لا تُحسب ضمن الأرقام):
#   (أحجام مجموعات الصيغة الكاملة، طول الجزء الأساسي قبل «/»، أقصى أرقام)
_GROUPED_SPECS = {
    "adherent": ((2, 3, 3, 2),  8, 10),   # N° ADHÉRENT: «XX XXX XXX XX»
    "num_ss":   ((2, 4, 4, 2), 10, 12),   # N° SS:      «XX XXXX XXXX XX»
}

# الحالة العائلية: حرف واحد + شرحه بالقائمة المنبثقة
_FAMILLE_CHOICES = [
    ("C", "Célibataire"), ("D", "Divorcé(e)"), ("V", "Veuf(ve)"), ("M", "Marié(e)"),
]
_FAMILLE_CODES = {c for c, _l in _FAMILLE_CHOICES}


def _format_grouped(text, spec):
    """تنسيق رقم مجمَّع حسب spec (راجع _GROUPED_SPECS).

    عند وجود «/»: ما قبله = الجزء الأساسي (يُجمَّع بأحجام sizes عدا
    المجموعة الأخيرة)، وما بعده = المفتاح (رقمان كحدّ)، مسافة قبل «/»
    وبلا مسافة بعده. بلا «/»: كل الأرقام تُجمَّع بأحجام sizes كاملة.
    """
    sizes, main_len, total = spec
    raw = str(text or "")
    if "/" in raw:
        before, after = raw.split("/", 1)
        main = re.sub(r"\D", "", before)[:main_len]
        cle = re.sub(r"\D", "", after)[:2]
        main_grp = " ".join(_group_digits(main, sizes[:-1]))
        return f"{main_grp} /{cle}" if main_grp else f"/{cle}"
    digits = re.sub(r"\D", "", raw)[:total]
    return " ".join(_group_digits(digits, sizes))


def _format_adherent(text):
    """اختصار توافقي: تنسيق رقم الانتساب بصيغة النموذج «XX XXX XXX XX»."""
    return _format_grouped(text, _GROUPED_SPECS["adherent"])


class BulletinPaieScreen(ttk.Frame):
    SCREEN_KEY = "hr_bulletin_paie"
    SCREEN_TITLE = "كشف راتب شهري"
    DOC_LABEL = "Bulletin de paie"
    OUTPUT_DIRNAME = "Bulletins de paie"

    TARGET_W = 720
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, ZOOM_DEFAULT = 30, 260, 20, 100
    MARGIN = 18

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._template_key = registry.DEFAULT_TEMPLATE_KEY
        self.zoom = self.ZOOM_DEFAULT
        self._built = False

        self._slot_ids = {}
        self._slot_widgets = {}
        self._slot_vars = {}
        self._masked = {}   # key -> MaskedDateEntry (خانات التاريخ نمط CD)
        self._slots_by_key = {s.key: s for s in template_simple.FIELD_SLOTS}
        self._nav_order = [s.key for s in template_simple.FIELD_SLOTS]
        self._suspend = set()  # مفاتيح حقول تُعاد كتابتها برمجياً الآن (تمنع رجع الحدث)

        self._prime_soumis = [tk.BooleanVar(value=True) for _ in range(template_simple.N_PRIME_SLOTS)]
        self._hr_var = tk.BooleanVar(value=False)
        self._mode_var = tk.StringVar(value="walkin")

        # تراجع / إعادة على مستوى الاستمارة (tk.Entry بلا Ctrl+Z مدمج)
        self._undo_stack = []
        self._redo_stack = []
        self._undo_job = None
        self._restoring = False
        self._last_committed = {}

        self._calc_input = calc.PaieInput()
        self._calc_result = calc.compute(self._calc_input)

        self._build_layout()
        self._build_fields()
        self._built = True
        self._last_committed = self._snapshot()
        self.after_idle(self._relayout)
        self._recompute()

    # ---------------- بناء الواجهة ----------------
    def _build_layout(self):
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        holder = ttk.Frame(paned)
        self.canvas = tk.Canvas(holder, bg="#9aa0a6", highlightthickness=0)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(holder, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        paned.add(holder, weight=1)

        self.canvas.bind("<Configure>", lambda _e: self._relayout())
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.canvas.bind("<MouseWheel>",
                         lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        self.sidebar = ttk.Frame(paned, padding=10)
        paned.add(self.sidebar, weight=0)
        self._build_sidebar()

    def _build_sidebar(self):
        sb = self.sidebar
        ttk.Label(sb, text=self.SCREEN_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(sb, text=self.DOC_LABEL, style="Subtitle.TLabel").pack(anchor="w", pady=(0, 8))

        zb = ttk.Frame(sb)
        zb.pack(fill="x", pady=(0, 8))
        ttk.Button(zb, text="－", width=3, command=self.zoom_out).pack(side="left")
        self._zoom_lbl = ttk.Label(zb, text="100%", width=6, anchor="center")
        self._zoom_lbl.pack(side="left")
        ttk.Button(zb, text="＋", width=3, command=self.zoom_in).pack(side="left")
        ttk.Button(zb, text="ملاءمة", command=self.fit_to_window).pack(side="left", padx=(6, 0))

        mf = ttk.LabelFrame(sb, text="الموديل", padding=8)
        mf.pack(fill="x", pady=(0, 8))
        ttk.Label(mf, text=registry.get_template(self._template_key).LABEL).pack(anchor="w")

        cf = ttk.LabelFrame(sb, text="الزبون", padding=8)
        cf.pack(fill="x", pady=(0, 8))
        ttk.Radiobutton(cf, text="زبون مسجّل", value="registered", variable=self._mode_var,
                        command=self._on_mode_change).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(cf, text="زبون عابر", value="walkin", variable=self._mode_var,
                        command=self._on_mode_change).grid(row=0, column=1, sticky="w")
        self._picker = ClientPickerEntry(cf, on_change=lambda *_a: None)
        self._picker.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._picker.grid_remove()

        irgf = ttk.LabelFrame(sb, text="IRG", padding=8)
        irgf.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(irgf, text="Handicapé / Retraité", variable=self._hr_var,
                        command=self._recompute).pack(anchor="w")

        pf = ttk.LabelFrame(sb, text="منح خاضعة للاشتراك (CNAS)", padding=8)
        pf.pack(fill="x", pady=(0, 8))
        for k, var in enumerate(self._prime_soumis, start=1):
            ttk.Checkbutton(pf, text=f"منحة {k}", variable=var,
                            command=self._recompute).pack(anchor="w")

        bf = ttk.LabelFrame(sb, text="إجراءات", padding=8)
        bf.pack(fill="x", pady=(0, 8))
        ttk.Button(bf, text="توليد Word", command=lambda: self._on_generate("docx")).pack(fill="x")
        ttk.Button(bf, text="توليد PDF", command=lambda: self._on_generate("pdf")).pack(fill="x", pady=(4, 0))
        ttk.Button(bf, text="السجلّ", command=self._on_history).pack(fill="x", pady=(4, 0))
        ttk.Button(bf, text="مسح", command=self._on_clear).pack(fill="x", pady=(4, 0))

        ttk.Label(
            sb, style="Subtitle.TLabel", wraplength=200, justify="right",
            text="أبيض = يُملأ يدوياً · أزرق = يُحسب تلقائياً · أسود = جزء ثابت من الاستمارة.",
        ).pack(anchor="w", pady=(4, 0))

    def _build_fields(self):
        today = date.today()
        defaults = {
            "mois": _MOIS_UP[today.month - 1],
            "annee": str(today.year),
            "jours": "30",
        }
        self._band_keys = {s.key for s in template_simple.FIELD_SLOTS if s.on_band}
        for slot in template_simple.FIELD_SLOTS:
            if slot.kind == "date_masked":
                self._build_masked_date(slot)
                continue
            var = tk.StringVar(value=defaults.get(slot.key, ""))
            justify = {"r": "right", "c": "center", "l": "left"}[slot.align]
            ent = tk.Entry(
                self.canvas, textvariable=var, bd=0, relief="flat", justify=justify,
                highlightthickness=1, highlightbackground=_HOVER_IDLE, highlightcolor=_HOVER_IDLE,
                bg=FILLED_BG_COLOR if var.get() else EMPTY_BG_COLOR,
                fg=_INK, insertbackground=_INK,
            )
            validator = self._make_validator(slot)
            if slot.kind in _GROUPED_SPECS:
                ent.configure(validate="key",
                              validatecommand=(self.register(validator), "%P", "%d", "%S"))
            else:
                ent.configure(validate="key",
                              validatecommand=(self.register(validator), "%P"))
            var.trace_add("write", lambda *_a, k=slot.key: self._on_slot_write(k))
            if not slot.on_band:
                self._add_hover(ent, var)
            bind_triple_click_select_all(ent)
            ent.bind("<Return>", lambda e: self._nav(e, +1))
            ent.bind("<KP_Enter>", lambda e: self._nav(e, +1))
            ent.bind("<Tab>", lambda e: self._nav(e, +1))
            ent.bind("<Shift-Tab>", lambda e: self._nav(e, -1))
            ent.bind("<ISO_Left_Tab>", lambda e: self._nav(e, -1))
            ent.bind("<KeyRelease>", lambda e, k=slot.key: self._on_key_release(k, e))
            if slot.kind in _GROUPED_SPECS:
                ent.bind("<FocusIn>", lambda _e, k=slot.key: self._grouped_unformat(k), add="+")
                ent.bind("<FocusOut>", lambda _e, k=slot.key: self._grouped_format(k), add="+")
            if slot.kind == "famille":
                # نقرة يسار أو سهم لأسفل → قائمة اختيار C/D/V/M (+ «تفريغ»)
                ent.bind("<Button-1>",
                         lambda _e, k=slot.key, w=ent: self._popup_famille(k, w))
                ent.bind("<Down>",
                         lambda _e, k=slot.key, w=ent: self._popup_famille(k, w))
                # كتابة حرف جديد وفي الحقل حرف أصلاً: يمسح القديم فيحلّ
                # الجديد محلّه (بلا هذا يرفض التحقّق «MC» ولا يمكن التبديل
                # بالكتابة عبر الفأرة، فقط بعد تحديد كامل بـTab).
                ent.bind("<Key>",
                         lambda e, k=slot.key: self._famille_key(k, e))
            ent.bind("<Control-z>", self._on_undo)
            ent.bind("<Control-Z>", self._on_undo)
            ent.bind("<Control-y>", self._on_redo)
            ent.bind("<Control-Shift-Z>", self._on_redo)
            wid = self.canvas.create_window(0, 0, window=ent, anchor="nw")
            self._slot_vars[slot.key] = var
            self._slot_widgets[slot.key] = ent
            self._slot_ids[slot.key] = wid
            if slot.on_band:
                self._wire_band_field(ent, slot.key)

    def _build_masked_date(self, slot):
        """خانة تاريخ مثل CD بالضبط (MaskedDateEntry) — مركّبة فوق اللوحة،
        بخط الكشف الخشن، خلفية «فارغ/ممتلئ» كبقية الحقول، وانتقال تلقائي
        عند اكتمال السنة (4 أرقام)."""
        from ui.common.widgets import MaskedDateEntry
        mde = MaskedDateEntry(self.canvas, default_today=False)
        mde.configure(bg=EMPTY_BG_COLOR)
        # _validate() الداخلي يعيد ضبط bg للون «الطبيعي» — نجعله ديناميكياً
        # (كريمي فارغ / أبيض ممتلئ) فيتماشى مع بقية الحقول، ويبقى الأحمر
        # للتاريخ المستحيل يفوز.
        mde._NORMAL_BG = EMPTY_BG_COLOR
        mde.entry.configure(fg=_INK, insertbackground=_INK, justify="left",
                            bg=EMPTY_BG_COLOR)
        inner = mde.entry
        inner.bind("<Return>", lambda _e, k=slot.key: self._nav_from(k, +1))
        inner.bind("<KP_Enter>", lambda _e, k=slot.key: self._nav_from(k, +1))
        inner.bind("<Tab>", lambda _e, k=slot.key: self._nav_from(k, +1))
        inner.bind("<Shift-Tab>", lambda _e, k=slot.key: self._nav_from(k, -1))
        inner.bind("<ISO_Left_Tab>", lambda _e, k=slot.key: self._nav_from(k, -1))
        inner.bind("<Control-z>", self._on_undo)
        inner.bind("<Control-Z>", self._on_undo)
        inner.bind("<Control-y>", self._on_redo)
        inner.bind("<Control-Shift-Z>", self._on_redo)
        inner.bind("<KeyRelease>", lambda e, k=slot.key: self._masked_date_maybe_advance(k, e))

        # إطار أزرق عند التحويم/التركيز مثل بقية الحقول. MaskedDateEntry
        # لا تمرّ على _add_hover العام (Frame مركّبة)، فنربطه هنا على
        # خانتها الداخلية — الحدود فقط؛ الخلفية (كريمي/أبيض/أحمر) تبقى
        # بيد _validate + _on_slot_write.
        def _mde_idle(*_a, w=inner):
            w.configure(highlightbackground=_HOVER_IDLE, highlightcolor=_HOVER_IDLE)

        def _mde_active(*_a, w=inner):
            w.configure(highlightbackground=_HOVER_ON, highlightcolor=_HOVER_ON)

        inner.bind("<Enter>", _mde_active)
        inner.bind("<Leave>", _mde_idle)
        inner.bind("<FocusIn>", _mde_active, add="+")
        inner.bind("<FocusOut>", _mde_idle, add="+")
        _mde_idle()

        mde.var.trace_add("write", lambda *_a, k=slot.key: self._on_slot_write(k))
        wid = self.canvas.create_window(0, 0, window=mde, anchor="nw")
        self._slot_vars[slot.key] = mde.var
        self._slot_widgets[slot.key] = mde
        self._masked[slot.key] = mde
        self._slot_ids[slot.key] = wid

    def _masked_date_maybe_advance(self, key, event):
        """اكتمل التاريخ (يوم+شهر+سنة) بضغطة رقم → ينتقل للحقل التالي."""
        if event.keysym not in "0123456789" or len(event.keysym) != 1:
            return
        d = self._masked[key]._digits
        if len(d["day"]) == 2 and len(d["month"]) == 2 and len(d["year"]) == 4:
            self._focus_rel(key, +1)

    # ---------------- التحقق من الصحة حسب نوع الحقل ----------------
    def _make_validator(self, slot):
        kind, maxlen = slot.kind, slot.maxlen

        def v_default(P):
            return len(P) <= maxlen

        def v_upper_alpha(P):
            # حروف + مسافة + «-» فقط (اللقب/المكان بالأحرف الكبيرة)
            return len(P) <= maxlen and all(ch.isalpha() or ch in " -" for ch in P)

        def v_titlecase(P):
            # حروف + مسافة + «-» + «'» (الاسم: أول حرف كل كلمة كبير)
            return len(P) <= maxlen and all(ch.isalpha() or ch in " -'" for ch in P)

        def v_year(P):
            # ≤4 أرقام، وتبدأ بـ1 أو 2 فقط (1000‑2999) — نفس قيد خانات
            # التاريخ، موحّد لكل حقول السنة بالبرنامج.
            return P == "" or (P.isdigit() and len(P) <= 4 and P[0] in "12")

        def v_famille(P):
            # حرف واحد فقط من C/D/V/M (يُحوَّل لكبير في _on_key_release)
            return P == "" or (len(P) == 1 and P.upper() in _FAMILLE_CODES)

        def v_month(P):
            if P == "":
                return True
            if len(P) > maxlen:
                return False
            if P.isdigit():
                return len(P) <= 2 and (P in ("1", "0") or (P[0] != "0" and 1 <= int(P) <= 12))
            return bool(_month_matches(P))

        def v_grouped(P, action, S):
            # أثناء الكتابة: أرقام ملتصقة بلا مسافات (+ «/» اختيارية).
            # الصيغة المنسَّقة تظهر عند مغادرة الحقل فقط. الأحجام/الحدود
            # حسب نوع الحقل (adherent = 10 أرقام والمفتاح بعد 8،
            # num_ss = 12 أرقام والمفتاح بعد 10).
            _sizes, main_len, total = _GROUPED_SPECS[kind]
            if P == "":
                return True
            if not re.fullmatch(r"[0-9/]*", P):
                return False
            if P.count("/") > 1:
                return False
            if "/" in P:
                before, after = P.split("/", 1)
                db, da = len(before), len(after)
                if da > 2 or db > main_len:
                    return False
                # إدراج «/» جديدة يتطلّب اكتمال الجزء الأساسي؛ تعديل الأرقام لاحقاً حرّ
                if action == "1" and "/" in S and db < main_len:
                    return False
                return True
            return len(P) <= total

        return {"year": v_year, "month": v_month, "famille": v_famille,
                "adherent": v_grouped, "num_ss": v_grouped,
                "upper_alpha": v_upper_alpha, "titlecase": v_titlecase}.get(kind, v_default)

    def _on_key_release(self, key, event):
        if event.keysym in ("Tab", "ISO_Left_Tab", "Return", "KP_Enter",
                            "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        slot = self._slots_by_key[key]
        var = self._slot_vars[key]

        if slot.kind in ("upper", "upper_alpha"):
            cur = var.get()
            up = cur.upper()
            if up != cur:
                self._set_var(key, up, cursor="keep", widget=event.widget)

        elif slot.kind == "titlecase":
            cur = var.get()
            tc = _titlecase(cur)
            if tc != cur:
                self._set_var(key, tc, cursor="keep", widget=event.widget)

        elif slot.kind == "month":
            if event.keysym not in ("BackSpace", "Delete"):
                resolved = _resolve_month(var.get())
                if resolved is not None:
                    self._set_var(key, resolved)
                    self._focus_rel(key, +1)

        elif slot.kind == "year":
            if event.keysym not in ("BackSpace", "Delete") and len(var.get()) >= 4:
                self._focus_rel(key, +1)

        elif slot.kind == "famille":
            cur = var.get()
            up = cur.upper()
            if up != cur:
                self._set_var(key, up, cursor="keep", widget=event.widget)
                cur = up
            # حُسِم (حرف صالح) → انتقال تلقائي للحقل التالي
            if event.keysym not in ("BackSpace", "Delete") and cur in _FAMILLE_CODES:
                self._focus_rel(key, +1)

        elif slot.kind == "num_ss":
            # اكتمل الرقم (12 رقماً، أو 10 + مفتاح /رقمين) → انتقال تلقائي
            if event.keysym not in ("BackSpace", "Delete"):
                _sizes, main_len, total = _GROUPED_SPECS["num_ss"]
                raw = var.get()
                if "/" in raw:
                    before, after = raw.split("/", 1)
                    done = (len(re.sub(r"\D", "", before)) == main_len
                            and len(re.sub(r"\D", "", after)) == 2)
                else:
                    done = len(re.sub(r"\D", "", raw)) == total
                if done:
                    self._focus_rel(key, +1)

        # adherent: لا تنسيق أثناء الكتابة — الأرقام ملتصقة، والصيغة
        # المنسَّقة تظهر عند مغادرة الحقل فقط (num_ss مثله + انتقال تلقائي).

    def _grouped_unformat(self, key):
        """عند دخول حقل رقم مجمَّع (adherent/num_ss): تُزال المسافات
        ليُحرَّر الرقم ملتصقاً."""
        var = self._slot_vars[key]
        raw = var.get().replace(" ", "")
        if raw != var.get():
            self._set_var(key, raw, cursor="end")

    def _grouped_format(self, key):
        """عند مغادرة حقل رقم مجمَّع: تظهر الصيغة النهائية المنسَّقة حسب
        نوع الحقل («XX XXX XXX XX» / «XX XXXX XXXX XX» / «… /XX»)."""
        spec = _GROUPED_SPECS[self._slots_by_key[key].kind]
        var = self._slot_vars[key]
        formatted = _format_grouped(var.get(), spec)
        if formatted != var.get():
            self._set_var(key, formatted, cursor="end")

    def _popup_famille(self, key, widget):
        """قائمة منبثقة لاختيار الحالة العائلية (C/D/V/M) بشرحها، مع
        «تفريغ» لإفراغ الحقل — بديل عن كتابة الحرف مباشرة."""
        widget.focus_set()
        menu = tk.Menu(self, tearoff=0)
        for code, label in _FAMILLE_CHOICES:
            menu.add_command(label=f"{code} — {label}",
                             command=lambda c=code, k=key: self._pick_famille(k, c))
        menu.add_separator()
        menu.add_command(label="—  (تفريغ)",
                         command=lambda k=key: self._pick_famille(k, ""))
        try:
            menu.tk_popup(widget.winfo_rootx(),
                          widget.winfo_rooty() + widget.winfo_height())
        finally:
            menu.grab_release()
        return "break"

    def _pick_famille(self, key, code):
        self._set_var(key, code, cursor="end")
        if code:  # التفريغ لا ينقل التركيز — يبقى بالحقل للتعديل
            self._focus_rel(key, +1)

    def _famille_key(self, key, event):
        """قبل إدراج حرف الحالة العائلية: لو الحقل فيه حرف أصلاً وضُغط
        حرف صالح جديد، امسح القديم فيدخل الجديد مكانه."""
        if len(event.char) == 1 and event.char.upper() in _FAMILLE_CODES \
                and self._slot_vars[key].get():
            self._set_var(key, "", cursor="end")

    def _set_var(self, key, value, cursor="end", widget=None):
        self._suspend.add(key)
        var = self._slot_vars[key]
        w = widget or self._slot_widgets[key]
        pos = w.index(tk.INSERT) if cursor == "keep" else None
        var.set(value)
        w.configure(validate="key")  # var.set() يعطّل التحقق — نرجّعه
        if cursor == "keep" and pos is not None:
            try:
                w.icursor(min(pos, len(value)))
            except tk.TclError:
                pass
        elif cursor == "end":
            w.icursor(tk.END)
        self._suspend.discard(key)
        self._on_slot_write(key)

    # ---------------- التنقّل بين الحقول ----------------
    def _nav(self, event, direction):
        key = self._key_of_widget(event.widget)
        if key is None:
            return None
        slot = self._slots_by_key[key]
        # الشهر: لا يغادر إلا إذا حُسِم (أو فارغ)
        if slot.kind == "month" and direction > 0:
            txt = self._slot_vars[key].get().strip()
            if txt and _resolve_month(txt) is None:
                return "break"
            if txt:
                self._set_var(key, _resolve_month(txt))
        self._focus_rel(key, direction)
        return "break"

    def _nav_from(self, key, direction):
        """تنقّل من خانة مركّبة (MaskedDateEntry) لا يصلها _nav العادي."""
        self._focus_rel(key, direction)
        return "break"

    def _focus_rel(self, key, direction):
        try:
            i = self._nav_order.index(key)
        except ValueError:
            return
        j = (i + direction) % len(self._nav_order)
        nkey = self._nav_order[j]
        # خانة التاريخ المركّبة: التركيز يذهب لخانتها الداخلية
        nxt = self._masked[nkey].entry if nkey in self._masked else self._slot_widgets[nkey]
        nxt.focus_set()
        # التحديد الكامل يحدث فقط حين ننقل التركيز بأنفسنا (Tab/Enter/Shift+Tab) —
        # لا في كل <FocusIn>، حتى لا تُحدَّد الحقول عند عودة النافذة من Alt+Tab.
        nxt.after_idle(lambda: self._select_all_if_alive(nxt))

    @staticmethod
    def _select_all_if_alive(widget):
        try:
            if widget.winfo_exists():
                widget.select_range(0, tk.END)
                widget.icursor(tk.END)
        except tk.TclError:
            pass

    def _key_of_widget(self, widget):
        for k, w in self._slot_widgets.items():
            if w is widget:
                return k
        return None

    # ---------------- المظهر (إطار تحويم كـCD) ----------------
    def _add_hover(self, widget, var):
        def set_idle(*_a):
            widget.configure(highlightbackground=_HOVER_IDLE, highlightcolor=_HOVER_IDLE)
            widget.configure(
                bg=EMPTY_BG_COLOR if not (var.get() or "").strip() else FILLED_BG_COLOR)

        widget.bind("<Enter>", lambda _e: widget.configure(
            highlightbackground=_HOVER_ON, highlightcolor=_HOVER_ON))
        widget.bind("<Leave>", lambda _e: set_idle())
        widget.bind("<FocusIn>", lambda _e: widget.configure(
            highlightbackground=_HOVER_ON, highlightcolor=_HOVER_ON), add="+")
        widget.bind("<FocusOut>", lambda _e: set_idle(), add="+")
        set_idle()

    # حقول الشهر/السنة فوق الشريط الأسود:
    #   فارغ + غير مركَّز → يظهر كبقية الحقول الفارغة (كريمي) لينتبه له العامل
    #   ممتلئ + غادره     → يندمج في الشريط (أسود، كتابة بيضاء عريضة)
    #   مركَّز (يُحرَّر)   → صندوق أبيض بكتابة سوداء ليقرأ ما يكتب
    def _wire_band_field(self, widget, key):
        widget.bind("<Enter>", lambda _e: widget.configure(
            highlightbackground=_HOVER_ON, highlightcolor=_HOVER_ON))
        widget.bind("<Leave>", lambda _e, k=key: self._style_band_field(k))
        widget.bind("<FocusIn>", lambda _e, k=key: self._style_band_field(k, True), add="+")
        widget.bind("<FocusOut>", lambda _e, k=key: self._style_band_field(k, False), add="+")
        self._style_band_field(key, False)

    def _style_band_field(self, key, focused=None):
        w = self._slot_widgets[key]
        if focused is None:
            try:
                focused = w.focus_get() is w
            except (KeyError, tk.TclError):
                focused = False
        has_val = bool(self._slot_vars[key].get().strip())
        if focused:
            w.configure(bg=FILLED_BG_COLOR, fg="black", insertbackground="black",
                        highlightbackground=_HOVER_ON, highlightcolor=_HOVER_ON)
        elif has_val:
            w.configure(bg=_BAND_BG, fg="white", insertbackground="white",
                        highlightbackground=_BAND_BG, highlightcolor=_BAND_BG)
        else:
            w.configure(bg=EMPTY_BG_COLOR, fg="black", insertbackground="black",
                        highlightbackground=_HOVER_IDLE, highlightcolor=_HOVER_IDLE)

    # ---------------- الزوم والتخطيط ----------------
    def _page_box(self):
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        sheet_w = self.TARGET_W * self.zoom / 100.0
        scale = sheet_w / 210.0
        sheet_h = scale * 297.0
        x0 = max((cw - sheet_w) / 2, self.MARGIN)
        y0 = max((ch - sheet_h) / 2, self.MARGIN)
        return (x0, y0, x0 + sheet_w, y0 + sheet_h), scale, cw, ch

    def _set_zoom(self, pct):
        self.zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, int(round(pct))))
        self._zoom_lbl.configure(text=f"{self.zoom}%")
        self._relayout()

    def zoom_in(self):
        self._set_zoom(((self.zoom // self.ZOOM_STEP) + 1) * self.ZOOM_STEP)

    def zoom_out(self):
        self._set_zoom((-(-self.zoom // self.ZOOM_STEP) - 1) * self.ZOOM_STEP)

    def _on_ctrl_wheel(self, event):
        self.zoom_in() if event.delta > 0 else self.zoom_out()

    def fit_to_window(self):
        cw = max(self.canvas.winfo_width() - 2 * self.MARGIN, 100)
        ch = max(self.canvas.winfo_height() - 2 * self.MARGIN, 100)
        by_w = cw / self.TARGET_W
        by_h = ch / (self.TARGET_W * 297.0 / 210.0)
        self._set_zoom(min(by_w, by_h) * 100)

    def _paint_all(self, page_box, scale):
        self.canvas.delete("form")
        x0, y0, x1, y1 = page_box
        before = set(self.canvas.find_all())
        self.canvas.create_rectangle(x0 + 3, y0 + 3, x1 + 3, y1 + 3, fill="#5f6368", outline="")
        self.canvas.create_rectangle(x0, y0, x1, y1, fill="white", outline="#3c4043")
        try:
            template_simple.paint_form(
                self.canvas, page_box, scale, self._calc_input, self._calc_result,
                self._employer_data(), self._employee_data(),
            )
        except Exception:  # noqa: BLE001
            pass
        for item in set(self.canvas.find_all()) - before:
            self.canvas.addtag_withtag("form", item)
        for wid in self._slot_ids.values():
            self.canvas.tag_raise(wid)

    def _relayout(self):
        if not self._built:
            return
        page_box, scale, cw, ch = self._page_box()
        self._paint_all(page_box, scale)
        x0, y0 = page_box[0], page_box[1]
        for slot in template_simple.FIELD_SLOTS:
            x, y, w, h = template_simple.slot_px(page_box, scale, slot)
            wid = self._slot_ids[slot.key]
            fs = max(6, int(slot.font_mm * scale * 0.62))
            fnt = (_ENTRY_FONT, fs, "bold") if slot.bold else (_ENTRY_FONT, fs)

            slot_x_mm = slot.x_mm
            if slot.key == "id_lieu_naissance":
                slot_x_mm = template_simple.row1_layout(self.canvas, scale)[1]

            on_baseline = slot.baseline_mm is not None
            if on_baseline:
                # أعلى الإطار = baseline − ascent − (حلقة التركيز + YPAD).
                # يصحّ فقط والإطار بارتفاعه الطبيعي (box_h=0 تحت) — أي فرض
                # ارتفاع أكبر يوسّط النص عمودياً ويهبطه تحت التسمية،
                # والهبوط يكبر مع الزوم.
                ascent = tkfont.Font(root=self.canvas, font=fnt).metrics("ascent")
                x = x0 + (template_simple.MARGIN_L + slot_x_mm) * scale
                y = y0 + slot.baseline_mm * scale - ascent - _ENTRY_TOP_CHROME
            self.canvas.coords(wid, x, y)

            box_h = 0 if on_baseline else int(h)
            if slot.key in self._masked:
                # خانة تاريخ: عرض وارتفاع طبيعيان (قدر «JJ/MM/AAAA»، وسطر
                # واحد بلا فراغ توسيط) فيتطابق خط أساسها مع التسمية.
                self.canvas.itemconfigure(wid, width=0, height=box_h)
                self._masked[slot.key].entry.configure(font=fnt, width=10)
            else:
                w_px = int(w)
                if getattr(slot, "fit_maxlen", False):
                    # حدود الإطار = قدر أوسع محتوى ممكن بالخط الحالي بالضبط
                    # (+ هامش tk.Entry) — لا فراغ ذيلي. للحقول المجمَّعة
                    # نقيس أوسع صيغة منسَّقة (مع المفتاح «/XX») لا maxlen الخام.
                    fm = tkfont.Font(root=self.canvas, font=fnt)
                    if slot.kind in _GROUPED_SPECS:
                        spec = _GROUPED_SPECS[slot.kind]
                        sample = _format_grouped("0" * spec[1] + "/00", spec)
                    else:
                        sample = "M" * slot.maxlen
                    w_px = fm.measure(sample) + 2 * _ENTRY_TOP_CHROME
                self.canvas.itemconfigure(wid, width=w_px, height=box_h)
                self._slot_widgets[slot.key].configure(font=fnt)
        _x0, _y0, x1, y1 = page_box
        self.canvas.configure(scrollregion=(0, 0, max(x1 + self.MARGIN, cw), max(y1 + self.MARGIN, ch)))

    # ---------------- البيانات والحساب ----------------
    def _employer_data(self):
        v = self._slot_vars
        return {
            "raison_sociale": v["emp_raison_sociale"].get(),
            "adresse": v["emp_adresse"].get(),
            # دائماً بالصيغة المنسَّقة مهما كانت حالة تركيز الحقل
            "cnas_employeur": _format_adherent(v["emp_cnas"].get()),
        }

    def _employee_data(self):
        v = self._slot_vars
        return {
            "nom": v["id_nom"].get(),
            "prenom": v["id_prenom"].get(),
            "date_naissance": v["id_date_naissance"].get(),
            "lieu_naissance": v["id_lieu_naissance"].get(),
            "matricule": v["id_matricule"].get(),
            "fonction": v["id_fonction"].get(),
            "situation_familiale": v["id_situation_familiale"].get(),
            # دائماً بالصيغة المنسَّقة «XX XXXX XXXX XX» مهما كانت حالة التركيز
            "num_ss": _format_grouped(v["id_num_ss"].get(), _GROUPED_SPECS["num_ss"]),
            "date_embauche": v["id_date_embauche"].get(),
            "handicape_retraite": bool(self._hr_var.get()),
        }

    def _employee_fullname(self):
        v = self._slot_vars
        return " ".join(x for x in (v["id_nom"].get().strip(),
                                    v["id_prenom"].get().strip()) if x)

    def _build_input(self):
        v = self._slot_vars
        primes = []
        for k in range(template_simple.N_PRIME_SLOTS):
            lib = v[f"prime{k}_lib"].get().strip()
            mnt = v[f"prime{k}_montant"].get().strip()
            if lib or mnt:
                primes.append(calc.Prime(
                    code=v[f"prime{k}_code"].get().strip(), libelle=lib,
                    montant=_num(mnt), soumis_cotisation=bool(self._prime_soumis[k].get()),
                ))
        autres = []
        for k in range(template_simple.N_AUTRE_SLOTS):
            lib = v[f"autre{k}_lib"].get().strip()
            mnt = v[f"autre{k}_montant"].get().strip()
            if lib or mnt:
                autres.append(calc.Retenue(
                    code=v[f"autre{k}_code"].get().strip(), libelle=lib, montant=_num(mnt),
                ))
        return calc.PaieInput(
            mois=v["mois"].get(), annee=v["annee"].get(),
            jours=_num(v["jours"].get()) or 30.0,
            salaire_base=_num(v["salaire_base"].get()),
            panier=_num(v["panier"].get()), transport=_num(v["transport"].get()),
            handicape_retraite=bool(self._hr_var.get()),
            primes=primes, autres_retenues=autres,
        )

    def _on_slot_write(self, key):
        if key in self._suspend:
            return
        if key in self._masked:
            mde = self._masked[key]
            col = EMPTY_BG_COLOR if not self._slot_vars[key].get().strip() else FILLED_BG_COLOR
            mde._NORMAL_BG = col
            mde.configure(bg=col)
            mde.entry.configure(bg=col)
        elif key in self._band_keys:
            self._style_band_field(key)
        else:
            ent = self._slot_widgets[key]
            ent.configure(bg=FILLED_BG_COLOR if self._slot_vars[key].get() else EMPTY_BG_COLOR)
        if not self._restoring:
            self._push_undo_debounced()
        self._recompute()

    # ---------------- تراجع / إعادة ----------------
    def _snapshot(self):
        return {k: v.get() for k, v in self._slot_vars.items()}

    def _push_undo_debounced(self):
        if self._undo_job is not None:
            try:
                self.after_cancel(self._undo_job)
            except (ValueError, tk.TclError):
                pass
        self._undo_job = self.after(450, self._commit_undo)

    def _commit_undo(self):
        self._undo_job = None
        cur = self._snapshot()
        if cur != self._last_committed:
            self._undo_stack.append(self._last_committed)
            del self._undo_stack[:-60]  # سقف معقول
            self._redo_stack.clear()
            self._last_committed = cur

    def _restore(self, state):
        self._restoring = True
        for k, var in self._slot_vars.items():
            self._suspend.add(k)
            var.set(state.get(k, ""))
            if k in self._masked:
                self._masked[k]._resync_from_var()
            else:
                self._slot_widgets[k].configure(validate="key")
                if k in self._band_keys:
                    self._style_band_field(k)
                else:
                    self._slot_widgets[k].configure(
                        bg=FILLED_BG_COLOR if var.get() else EMPTY_BG_COLOR)
            self._suspend.discard(k)
        self._restoring = False
        self._last_committed = self._snapshot()
        self._recompute()

    def _on_undo(self, _event=None):
        if self._undo_job is not None:
            self.after_cancel(self._undo_job)
            self._commit_undo()
        if not self._undo_stack:
            return "break"
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        return "break"

    def _on_redo(self, _event=None):
        if not self._redo_stack:
            return "break"
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        return "break"

    def _recompute(self, *_a):
        if not self._built:
            return
        self._calc_input = self._build_input()
        self._calc_result = calc.compute(self._calc_input)
        page_box, scale, _cw, _ch = self._page_box()
        self._paint_all(page_box, scale)

    # ---------------- الزبون ----------------
    def _on_mode_change(self):
        if self._mode_var.get() == "registered":
            self._picker.grid()
        else:
            self._picker.grid_remove()
            self._picker.clear()

    # ---------------- التوليد ----------------
    def _resolve_out_path(self, ext):
        who = self._employee_fullname()
        stem = f"Bulletin_{_safe(who)}_{_safe(self._slot_vars['mois'].get())}_{_safe(self._slot_vars['annee'].get())}"
        return os.path.join(paths.get_screen_dir(self.OUTPUT_DIRNAME), stem + ext)

    def _on_generate(self, kind):
        if not self._employee_fullname():
            messagebox.showwarning(self.SCREEN_TITLE, "أدخل اسم الأجير أولاً.", parent=self)
            return
        self._recompute()
        tpl = registry.get_template(self._template_key)
        ext = ".docx" if kind == "docx" else ".pdf"
        path = self._resolve_out_path(ext)
        try:
            builder = tpl.build_docx if kind == "docx" else tpl.build_pdf
            builder(path, self._calc_input, self._calc_result,
                    self._employer_data(), self._employee_data())
        except TemplateNotReady as exc:
            messagebox.showinfo(self.SCREEN_TITLE, str(exc), parent=self)
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(self.SCREEN_TITLE, f"تعذّر التوليد:\n{exc}", parent=self)
            return

        try:
            database.log_hr_document(
                {
                    "screen_key": self.SCREEN_KEY,
                    "doc_label": self.DOC_LABEL,
                    "employer_name": self._employer_data().get("raison_sociale", ""),
                    "employee_name": self._employee_fullname(),
                    "doc_date": f"{self._slot_vars['mois'].get()} {self._slot_vars['annee'].get()}".strip(),
                    "client_id": (self._picker.get_client_id()
                                  if self._mode_var.get() == "registered" else None),
                    "file_path": path,
                    "pdf_path": path if kind == "pdf" else None,
                },
                full_data=self.collect_data(),
            )
        except Exception:  # noqa: BLE001
            pass

        if alerts.confirm(self.SCREEN_TITLE, f"تمّ إنشاء الملف:\n{path}\n\nفتحه الآن؟"):
            try:
                os.startfile(path)  # noqa: SIM115
            except OSError:
                pass

    def _on_history(self):
        rows = database.list_hr_documents(screen_key=self.SCREEN_KEY, limit=200)
        win = tk.Toplevel(self)
        win.title(f"سجلّ — {self.DOC_LABEL}")
        win.geometry("760x420")
        tv = ttk.Treeview(win, columns=("date", "employee", "employer", "file"), show="headings")
        for c, w in (("date", 130), ("employee", 200), ("employer", 200), ("file", 220)):
            tv.heading(c, text=c)
            tv.column(c, width=w)
        for row in rows:
            tv.insert("", "end", values=(
                row.get("doc_date", ""), row.get("employee_name", ""),
                row.get("employer_name", ""), os.path.basename(row.get("file_path", "")),
            ), tags=(row.get("file_path", ""),))

        def _open(_e):
            sel = tv.selection()
            if sel:
                p = tv.item(sel[0], "tags")
                if p and os.path.exists(p[0]):
                    try:
                        os.startfile(p[0])
                    except OSError:
                        pass

        tv.bind("<Double-1>", _open)
        tv.pack(fill="both", expand=True, padx=8, pady=8)
        if not rows:
            ttk.Label(win, text="لا سجلّ بعد.", style="Subtitle.TLabel").pack(pady=6)

    def _on_clear(self):
        if not alerts.confirm("تأكيد", "مسح كل الحقول في هذه الشاشة؟"):
            return
        # المسح قابل للتراجع عنه (Ctrl+Z يعيد ما كان)
        if self._undo_job is not None:
            self.after_cancel(self._undo_job)
            self._undo_job = None
        self._undo_stack.append(self._snapshot())
        del self._undo_stack[:-60]
        self._redo_stack.clear()

        today = date.today()
        defaults = {"mois": _MOIS_UP[today.month - 1], "annee": str(today.year), "jours": "30"}
        self._restoring = True
        for key, var in self._slot_vars.items():
            self._suspend.add(key)
            if key in self._masked:
                self._masked[key].clear()
            else:
                var.set(defaults.get(key, ""))
                self._slot_widgets[key].configure(validate="key")
                if key in self._band_keys:
                    self._style_band_field(key)
                else:
                    self._slot_widgets[key].configure(
                        bg=FILLED_BG_COLOR if var.get() else EMPTY_BG_COLOR)
            self._suspend.discard(key)
        self._restoring = False
        for pv in self._prime_soumis:
            pv.set(True)
        self._hr_var.set(False)
        self._picker.clear()
        self._last_committed = self._snapshot()
        self._recompute()

    def collect_data(self):
        pin = self._calc_input
        return {
            "screen_key": self.SCREEN_KEY,
            "doc_label": self.DOC_LABEL,
            "template": self._template_key,
            "mode": self._mode_var.get(),
            "client_id": (self._picker.get_client_id()
                          if self._mode_var.get() == "registered" else None),
            "employer": self._employer_data(),
            "employee": self._employee_data(),
            "paie": {
                "mois": pin.mois, "annee": pin.annee, "jours": pin.jours,
                "salaire_base": pin.salaire_base, "panier": pin.panier,
                "transport": pin.transport, "handicape_retraite": pin.handicape_retraite,
                "primes": [dataclasses.asdict(p) for p in pin.primes],
                "autres_retenues": [dataclasses.asdict(r) for r in pin.autres_retenues],
            },
            "result": dataclasses.asdict(self._calc_result),
        }

    # ---------------- توافق النافذة الرئيسية ----------------
    def activate_shortcuts(self):
        pass

    def deactivate_shortcuts(self):
        pass

    def flush_draft_save(self):
        pass

    def has_unsaved_changes(self):
        skip = {"mois", "annee", "jours"}
        return any(v.get().strip() for k, v in self._slot_vars.items() if k not in skip)
