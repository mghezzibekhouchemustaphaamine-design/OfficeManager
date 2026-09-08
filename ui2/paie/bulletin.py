"""الشاشة — توليد كشف الراتب.

مبنيّة من مكوّنات ``ui2/`` (``Form`` · ``DataTable`` · ``ToolBar``). كل
الحساب في ``programme.payroll`` (``lignes.compute_bulletin`` الذي وحده
يستدعي المحرّك — الشاشة **لا تستدعي ``calc`` مباشرةً أبداً**)، وكل
التخزين في ``programme.payroll.repository``. لا SQL ولا حساب هنا.

جدول أسطر ديناميكي: زرّ [＋ إضافة سطر ▾] بقائمة أنواع مجمَّعة (أساسية /
أخرى / سطر حرّ). عند اختيار النوع تُفتح حقوله فقط، ويُطبَّق منطقه من
``lignes``، ويقفز السطر تلقائياً إلى منطقته (§2.3.2). الأسطر النظامية
‎[A]…[E]‎ مقفلة. الأجر القاعدي يُضاف آلياً ولا يُحذف.
"""
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from programme.payroll import config_loader, lignes, repository
from ui2 import theme
from ui2.form import Field, Form
from ui2.paie._common import fmt_money, info_label, warn
from ui2.screen import Screen
from ui2.table import Column, DataTable
from ui2.toolbar import ToolAction

_RECOMPUTE_MS = 400

# ترتيب القائمة المنسدلة: مجموعة أساسية ثم فاصل «أخرى»
_MENU_BASE = ["salaire_base", "abs_jours", "abs_heures", "retard",
              "hs_50", "hs_100", "iep", "pri", "panier", "transport", "avance"]
_MENU_AUTRES = ["nuit", "syndicat", "conge_paye", "alloc_fam"]
_MENU_LIBRE = ["libre"]


class _LineRow(QWidget):
    """سطر واحد: تسمية النوع + زرّ حذف + :class:`ui2.form.Form` بحقوله،
    ومنطقة ``aux`` اختيارية (يستعملها سطر الأقدمية §1.2.4)."""

    changed = Signal()
    fieldEdited = Signal(str)                 # المستخدم عدّل حقلاً بنفسه
    removeRequested = Signal(object)

    def __init__(self, type_key: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.type_key = type_key
        lt = lignes.LINE_TYPES[type_key]

        title = QLabel(f"● {lt.libelle}")
        title.setStyleSheet("font-weight:600;")
        title.setFixedWidth(150)
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignRight | Qt.AlignTop)

        self.form = Form([Field(f.key, f.label, kind=f.kind, default=f.default,
                                choices=list(f.choices) or None)
                          for f in lt.fields], self)
        for f in lt.fields:
            w = self.form.widget(f.key)
            if hasattr(w, "textChanged"):
                w.textChanged.connect(self.changed)
            if hasattr(w, "textEdited"):
                w.textEdited.connect(lambda _t, k=f.key: self.fieldEdited.emit(k))
            elif hasattr(w, "currentTextChanged"):    # QComboBox
                w.currentTextChanged.connect(self.changed)
                w.activated.connect(lambda _i, k=f.key: self.fieldEdited.emit(k))

        self._aux = QVBoxLayout()
        self._warn = QLabel("")                       # «أدخل القيمة» — سطر بلا قيمة
        self._warn.setWordWrap(True)
        self._warn.setStyleSheet(f"color:{theme.WARNING};")
        self._warn.hide()
        self._aux.addWidget(self._warn)
        self._btn_del = QPushButton("✕")                 # أيقونة صغيرة
        self._btn_del.setToolTip("حذف السطر")
        self._btn_del.setFixedWidth(28)
        self._btn_del.setEnabled(not lt.system)          # الأجر القاعدي لا يُحذف
        self._btn_del.clicked.connect(lambda: self.removeRequested.emit(self))

        # سطر مضغوط: التسمية والحقول في صفّ أفقي واحد، وزرّ الحذف أيقونة.
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE["sm"])
        top.addWidget(title, 0, Qt.AlignTop)
        top.addWidget(self.form, 1)
        if not lt.system:
            top.addWidget(self._btn_del, 0, Qt.AlignTop)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.SPACE["sm"], theme.SPACE["xs"],
                               theme.SPACE["sm"], theme.SPACE["xs"])
        lay.setSpacing(theme.SPACE["xs"])
        lay.addLayout(top)
        lay.addLayout(self._aux)
        self.setStyleSheet(
            f"_LineRow {{ border:1px solid {theme.BORDER}; border-radius:4px; }}")

    def add_aux(self, widget: QWidget):
        self._aux.addWidget(widget)

    def primary_key(self) -> str:
        return lignes.LINE_TYPES[self.type_key].primary_key()

    def is_filled(self) -> bool:
        pk = self.primary_key()
        if not pk:
            return True
        return bool(str(self.form.values().get(pk, "")).strip())

    def set_missing_value(self, missing: bool):
        self._warn.setVisible(missing)
        if missing:
            self._warn.setText("أدخل القيمة — لا يُحتسَب هذا السطر حتى تملأه.")

    def entry(self) -> Dict:
        return {"type": self.type_key, "values": self.form.values()}


class _TwoColForm(QWidget):
    """ترويسة في عمودين: نموذجان :class:`ui2.form.Form` جنباً إلى جنب،
    بواجهة ``Form`` نفسها (``values`` · ``errors`` · ``set_values`` ·
    ``widget``) فيبقى بقيّة الكود دون تغيير."""

    def __init__(self, left: List[Field], right: List[Field], parent=None):
        super().__init__(parent)
        self._l = Form(left, self)
        self._r = Form(right, self)
        self._l.setMaximumWidth(460)
        self._r.setMaximumWidth(460)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.SPACE["lg"])
        lay.addWidget(self._l, 1)
        lay.addWidget(self._r, 1)
        lay.addStretch(2)

    def values(self) -> Dict[str, str]:
        return {**self._l.values(), **self._r.values()}

    def errors(self) -> List[str]:
        return self._l.errors() + self._r.errors()

    def set_values(self, data: Dict):
        self._l.set_values(data)
        self._r.set_values(data)

    def widget(self, key: str) -> QWidget:
        try:
            return self._l.widget(key)
        except KeyError:
            return self._r.widget(key)


class BulletinScreen(Screen):
    """توليد كشف — مبنيّة فوق :class:`ui2.screen.Screen`. ``conn`` اختياري
    (تمرّره الشاشة المضيفة / ``ui2/paie/__main__`` / المعرض).

    الهيكل يأتي من القاعدة (شريط أدوات + ترويسة + شريط تحذير + محتوى +
    شريط حالة) عبر الخطاطيف ``build_toolbar`` / ``build_header`` /
    ``build_body``. الحساب والحفظ/التثبيت وحرّاس V2/V3/V7/V15/V16 دون
    تغيير. خطاطيف المسوّدة (``draft_state`` / ``apply_draft`` / ``is_empty``)
    معرَّفة لكنها **خاملة** حتى تُوصَل (تعديلات المستخدم → ``mark_dirty``)
    في مهمة لاحقة."""

    TITLE = "توليد كشف"
    DRAFT_NAME = "paie"
    DRAFT_VERSION = 1

    bulletinSaved = Signal(int)

    def _build_menu(self):
        """يُعاد بناؤها عند كل إضافة/حذف سطر: نوع فريد مُضاف مسبقاً يظهر
        معطَّلاً (المراجعة الميدانية #5)."""
        self._menu.clear()
        present = {r.type_key for r in getattr(self, "_rows", [])}

        def add_group(keys):
            for key in keys:
                lt = lignes.LINE_TYPES.get(key)
                if lt is None:
                    continue
                act = self._menu.addAction(lt.libelle)
                act.setEnabled(not (lt.unique and key in present))
                act.triggered.connect(
                    lambda _c=False, k=key: self.add_line(k))

        add_group(_MENU_BASE)
        self._menu.addSeparator()
        self._menu.addAction("── أخرى ──").setEnabled(False)
        add_group(_MENU_AUTRES)
        if any(k in lignes.LINE_TYPES for k in _MENU_LIBRE):
            self._menu.addSeparator()
            self._menu.addAction("── سطر حرّ ──").setEnabled(False)
            add_group(_MENU_LIBRE)

    def __init__(self, conn=None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._client_id: Optional[int] = None
        self._bulletin_id: Optional[int] = None
        self._readonly = False
        self._view: Optional[lignes.BulletinView] = None
        self._cfg: Optional[Dict] = None
        self._rows: List[_LineRow] = []
        self._menu = QMenu(self)

        # مؤقّت إعادة الحساب (400ms بعد توقّف الكتابة)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_RECOMPUTE_MS)
        self._timer.timeout.connect(self.recompute)

        self.build_ui()                       # ← يبني الهيكل ويستدعي الخطاطيف
        # شريط التحذير: القاعدة توفّره باسم ``warnbar`` — نُبقي الاسم
        # القديم ``_warnbar`` كاسم بديل (بقيّة الكود والاختبارات تستعمله).
        self._warnbar = self.warnbar
        self.on_activate()                    # اختصارات الشاشة (Ctrl+S) تعمل مستقلّةً
        self.reload_clients()
        self.new_bulletin()

    # ======================= خطاطيف ui2.screen.Screen =======================
    def build_toolbar(self, toolbar):
        self._build_menu()
        add_btn = QToolButton(self)
        add_btn.setText("＋ إضافة سطر ▾")
        add_btn.setPopupMode(QToolButton.InstantPopup)
        add_btn.setMenu(self._menu)
        toolbar.add_widget(add_btn)
        toolbar.addSeparator()
        self._act_promote = toolbar.add(ToolAction(
            "ترقية إلى زبون مسجَّل", self._promote))
        toolbar.add_stretch()
        self._act_save = toolbar.add(ToolAction("حفظ", self.save))
        self._act_fige = toolbar.add(ToolAction("تثبيت", self.fige))
        self._act_pdf = toolbar.add(ToolAction("طباعة PDF", self._print_pdf))

    def build_header(self):
        #  لا قيم افتراضية موحِية: تاريخ الدخول فارغ (فيبقى اقتراح
        #  الأقدمية «حدّد تاريخ الدخول»)، والفترة = الشهر الحالي المحسوب.
        self._header = _TwoColForm(
            [Field("client_registered", "زبون مسجَّل", kind="choice",
                   choices=[]),
             Field("client_transient", "زبون عابر (اسم حرّ)")],
            [Field("employe_nom", "العامل — اللقب والاسم", required=True),
             Field("employe_date_entree", "تاريخ الدخول (YYYY-MM-DD)",
                   placeholder="YYYY-MM-DD"),
             Field("periode", "الفترة (YYYY-MM)", required=True,
                   default=date.today().strftime("%Y-%m"))],
            self)
        self._header.widget("client_registered").currentTextChanged.connect(
            self._on_client_changed)
        self._header.widget("periode").textChanged.connect(self._schedule)
        return self._header

    def build_body(self):
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)

        # ---------- منطقة الأسطر الديناميكية ----------
        self._lines_host = QWidget()
        self._lines_lay = QVBoxLayout(self._lines_host)
        self._lines_lay.setAlignment(Qt.AlignTop)
        scroll = QScrollArea(host)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._lines_host)
        scroll.setMinimumHeight(150)          # ارتفاع متكيّف بين حدّين
        scroll.setMaximumHeight(380)

        # ---------- جدول النتيجة (المخرَج الحقيقي — مساحة أكبر) ----------
        #  ترتيبه ليس اختيارياً (Z1→[A]→[B]→Z2→[C]→[D]→Z3→Z4→[E]) →
        #  الفرز مُعطَّل. الأسطر النظامية مميَّزة بصرياً عبر ``row_style``.
        self._result = DataTable(
            columns=[
                Column("libelle", "السطر"),
                Column("zone", "المنطقة", align=Qt.AlignCenter, width=90,
                       stretch=False),
                Column("montant", "المبلغ", ltr=True,
                       align=Qt.AlignLeft | Qt.AlignVCenter),
            ],
            sortable=False, row_style=self._result_row_style)
        self._result.setMinimumHeight(240)
        self._info = info_label("")

        lay.addWidget(QLabel("الأسطر:"))
        lay.addWidget(scroll, 2)
        lay.addWidget(QLabel("الكشف:"))
        lay.addWidget(self._result, 3)
        lay.addWidget(self._info)
        return host

    def shortcuts(self):
        return {"Ctrl+S": self.save}

    # ---------- المسوّدة: معرَّفة، خاملة حتى تُوصَل mark_dirty لاحقاً ----------
    def draft_state(self):
        return {"header": self._header.values(),
                "lines": [r.entry() for r in self._rows]}

    def apply_draft(self, data):
        self._header.set_values(data.get("header", {}))
        self._clear_lines()
        for e in data.get("lines", []):
            self.add_line(e.get("type"))
            if self._rows:
                self._rows[-1].form.set_values(e.get("values", {}))
        self.recompute()

    def is_empty(self):
        if self._header.values().get("employe_nom", "").strip():
            return False
        return (len(self._rows) == 1
                and self._rows[0].type_key == "salaire_base"
                and not self._rows[0].is_filled())

    # =============================== دورة الحياة ===============================
    def reload_clients(self):
        self._clients = repository.list_entreprises(
            registered_only=True, conn=self._conn)
        combo = self._header.widget("client_registered")
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([c["raison_sociale"] for c in self._clients])
        combo.blockSignals(False)
        if self._clients:
            self._on_client_changed(self._clients[0]["raison_sociale"])

    def new_bulletin(self):
        """استمارة جديدة: فارغة عدا الأجر القاعدي المُضاف آلياً (§2.3.1)."""
        self._bulletin_id = None
        self._readonly = False
        self._clear_lines()
        self.add_line("salaire_base")
        self.recompute()

    # =============================== الزبون ===============================
    def _on_client_changed(self, name: str):
        match = next((c for c in self._clients
                      if c["raison_sociale"] == name), None)
        self._client_id = match["id"] if match else None
        is_transient = bool(match and match.get("transient"))
        self._act_promote.setEnabled(is_transient)
        self.set_company(self._client_id)        # يبثّ companySelected للمضيف
        self._refresh_warnbar()

    def _active_client_row(self) -> Optional[dict]:
        return next((c for c in self._clients
                     if c["id"] == self._client_id), None)

    def _promote(self):
        row = self._active_client_row()
        if not row or not row.get("transient"):
            warn(self, "ترقية", ["اختر زبوناً عابراً أولاً."])
            return
        repository.promote_entreprise(row["id"], conn=self._conn)
        keep = row["id"]
        self.reload_clients()
        for i, c in enumerate(self._clients):
            if c["id"] == keep:
                self._header.widget("client_registered").setCurrentIndex(i)
                break

    # =============================== الأسطر ===============================
    def add_line(self, type_key: str):
        lt = lignes.LINE_TYPES.get(type_key)
        if lt is None:
            return
        # نوع فريد مُضاف مسبقاً → تجاهل بصمت (القائمة تعطّله أصلاً)
        if lt.unique and any(r.type_key == type_key for r in self._rows):
            return
        row = _LineRow(type_key, self._lines_host)
        row.changed.connect(self._schedule)
        row.fieldEdited.connect(
            lambda k, r=row: self._on_line_field_edited(r, k))
        row.removeRequested.connect(self._remove_line)
        self._lines_lay.addWidget(row)
        self._rows.append(row)
        if type_key == "iep":
            self._attach_iep_aux(row)
        elif type_key == "libre":
            self._attach_libre_aux(row)
        self._build_menu()        # نوع فريد صار مُضافاً → عطّله في القائمة
        self.recompute()          # فوري عند الإضافة

    # ------- سطر حرّ: تصنيف صريح إلزامي (V7) -------
    def _attach_libre_aux(self, row: _LineRow):
        row._libre_hint = QLabel(
            "حدّد «خاضع للاشتراك؟» و«خاضع للضريبة؟» — لا قيمة افتراضية "
            "(V7). السطر يقفز تلقائياً إلى منطقته.")
        row._libre_hint.setWordWrap(True)
        row._libre_hint.setStyleSheet(f"color:{theme.WARNING};")
        row.add_aux(row._libre_hint)

    def _libre_unclassified(self) -> List[_LineRow]:
        return [r for r in self._rows if r.type_key == "libre"
                and not lignes.free_line_classified(r.form.values())]

    # ------- سطر الأقدمية §1.2.4 -------
    def _attach_iep_aux(self, row: _LineRow):
        row._iep_manual = False
        row._iep_hint = QLabel("")
        row._iep_hint.setWordWrap(True)
        row._iep_hint.setStyleSheet(f"color:{theme.TEXT_DIM};")
        btn = QPushButton("استعمل النسبة المقترَحة")
        btn.clicked.connect(lambda: self._apply_iep_suggestion(row, force=True))
        row.add_aux(row._iep_hint)
        row.add_aux(btn)
        self._apply_iep_suggestion(row, force=True)

    def _on_line_field_edited(self, row: _LineRow, key: str):
        if row.type_key == "iep" and key == "taux":
            row._iep_manual = True
            row._iep_hint.setText(
                "النسبة معدَّلة يدوياً — اضغط «استعمل النسبة المقترَحة» للعودة.")

    def _matched_employe_taux(self):
        if self._client_id is None:
            return None
        nom = self._header.values().get("employe_nom", "").strip()
        if not nom:
            return None
        for e in repository.list_employes(self._client_id, conn=self._conn):
            if e["nom"] == nom:
                return e.get("taux_iep")
        return None

    def _apply_iep_suggestion(self, row: _LineRow, *, force: bool = False):
        if getattr(row, "_iep_manual", False) and not force:
            return
        v = self._header.values()
        cfg = self._cfg
        if cfg is None:
            try:
                cfg = config_loader.load_params(f"{v.get('periode','')}-01")
            except Exception:                          # noqa: BLE001
                return
        sug = lignes.suggest_iep_taux(
            date_entree=v.get("employe_date_entree", ""),
            periode=v.get("periode", ""), cfg=cfg,
            employe_taux_iep=self._matched_employe_taux())
        if sug.taux is None:
            row._iep_hint.setText(sug.texte_anciennete())
            return
        self._suppress_schedule = True
        try:
            row.form.widget("taux").setText(format(sug.taux, "f"))
        finally:
            self._suppress_schedule = False
        row._iep_manual = False
        tag = {"bareme": "مقترَحة", "employe": "من بطاقة العامل",
               "sous_minimum": "تحت الحدّ الأدنى"}.get(sug.source, "مقترَحة")
        row._iep_hint.setText(
            f"{tag}: {format(sug.taux, 'f')} — {sug.texte_anciennete()} · "
            f"{sug.raison}")
        if force:
            self.recompute()

    def _remove_line(self, row: _LineRow):
        if row not in self._rows:
            return
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._build_menu()        # النوع صار متاحاً من جديد
        self.recompute()          # فوري عند الحذف

    def _clear_lines(self):
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()

    # =============================== الحساب ===============================
    def _schedule(self):
        """إعادة حساب مؤجَّلة 400ms (بعد توقّف الكتابة)."""
        if getattr(self, "_suppress_schedule", False):
            return
        self._timer.start()

    def recompute(self):
        self._timer.stop()
        periode = self._header.values().get("periode", "").strip()
        try:
            cfg = config_loader.load_params(f"{periode}-01")
        except Exception as exc:                       # noqa: BLE001
            self._view = None
            self._cfg = None
            self._result.set_rows([])
            self._info.setText(f"تعذّر تحميل المعاملات: {exc}")
            return
        self._cfg = cfg

        # تحديث اقتراح الأقدمية للأسطر غير المعدَّلة يدوياً (بلا حلقة)
        for row in self._rows:
            # تنبيه «أدخل القيمة» — الأقدمية والسطر الحرّ لهما تلميحهما
            row.set_missing_value(
                not row.is_filled() and row.type_key not in ("iep", "libre"))
            if row.type_key == "iep" and not getattr(row, "_iep_manual", False):
                self._apply_iep_suggestion(row, force=False)
            elif row.type_key == "libre" and hasattr(row, "_libre_hint"):
                vals = row.form.values()
                if lignes.free_line_classified(vals):
                    z = lignes.LINE_TYPES["libre"].zone(vals)
                    row._libre_hint.setStyleSheet(f"color:{theme.TEXT_DIM};")
                    row._libre_hint.setText(f"مصنَّف → المنطقة {z}")
                else:
                    row._libre_hint.setStyleSheet(f"color:{theme.WARNING};")
                    row._libre_hint.setText(
                        "حدّد «خاضع للاشتراك؟» و«خاضع للضريبة؟» — لا قيمة "
                        "افتراضية (V7). لا يُحتسَب حتى يُصنَّف.")

        convention = (repository.get_active_convention(self._client_id,
                                                       conn=self._conn)
                      if self._client_id is not None else None)
        entries = [r.entry() for r in self._rows]
        self._view = lignes.compute_bulletin(entries, cfg, convention)
        self._render(self._view, convention)

    _SYS_LABELS = {
        "A": "[A] الأجر الخاضع للاشتراك",
        "B": "[B] اقتطاع CNAS 9%",
        "C": "[C] الأجر الخاضع للضريبة",
        "D": "[D] اقتطاع IRG",
        "E": "[E] الصافي للدفع",
    }

    def _result_row_style(self, row: dict):
        """الأسطر النظامية ‎[A]…[E]‎: خلفية وخط أثقل وفاصل علوي واضح —
        القفل وحده لا يكفي (‎[C]‎ و‎[E]‎ قد يتساويان فيبدوان مكرَّرين).
        ‎[C]‎ و‎[D]‎ متلاصقان بلا فاصل بينهما (§2.3.1)."""
        code = row.get("_sys")
        if not code:
            return None
        return {"background": theme.SELECTION, "bold": True,
                "separator_above": code != "D",
                "separator_color": theme.PRIMARY}

    def _render(self, view: lignes.BulletinView, convention: Optional[dict]):
        rows: List[dict] = []
        by_zone = {z: [l for l in view.lignes if l.zone == z]
                   for z in ("Z1", "Z2", "Z3", "Z4")}

        def emit_zone(z):
            for l in by_zone[z]:
                amount = fmt_money(l.montant)
                if l.sens == "RETENUE" and l.montant != 0:
                    amount = "−" + amount            # صفرٌ لا يأخذ إشارة
                rows.append({"libelle": l.libelle, "zone": z,
                             "montant": amount})

        def sys_row(code, value, *, negative=False):
            amount = fmt_money(value)
            if negative and value != 0:
                amount = "−" + amount
            rows.append({"libelle": f"🔒 {self._SYS_LABELS[code]}",
                         "zone": f"[{code}]", "_sys": code, "montant": amount})

        # ترتيب إلزامي: Z1 → [A] → [B] → Z2 → [C] → [D] → Z3 → Z4 → [E]
        emit_zone("Z1")
        sys_row("A", view.a)
        sys_row("B", view.b, negative=True)
        emit_zone("Z2")
        sys_row("C", view.c)
        sys_row("D", view.d, negative=True)
        emit_zone("Z3")
        emit_zone("Z4")
        sys_row("E", view.e)
        self._result.set_rows(rows)
        self._info.setText(
            f"عدد الأسطر: {len(view.lignes)}  ·  الصافي: {fmt_money(view.e)}")
        self._warnings = list(view.avertissements)
        self._refresh_warnbar()

    def _refresh_warnbar(self):
        msgs: List[str] = []
        conv = (repository.get_active_convention(self._client_id,
                                                conn=self._conn)
                if self._client_id is not None else None)
        # الاتفاقية «مُراجَعة» فقط إذا أكّدها المستخدم صراحةً (نسخة ≥ 2).
        # الاتفاقية الافتراضية المؤكَّدة تلقائياً (نسخة 1) تُبقي الشريط
        # ظاهراً — قيمها لم يراجعها أحد (المراجعة الميدانية #7).
        reviewed = bool(conv and conv.get("confirme")
                        and int(conv.get("version", 1)) > 1)
        if not reviewed:
            msgs.append(
                "معاملات الاتفاقية لم تُراجَع بعد (قيم افتراضية). تأكّد من "
                "قاعدة احتساب منحة الأقدمية وتنسيب السلة والنقل مع صاحب "
                "العمل قبل اعتماد الكشف.")
        msgs.extend(getattr(self, "_warnings", []))
        if msgs:
            self._warnbar.setText("\n".join("• " + m for m in msgs))
            self._warnbar.show()
        else:
            self._warnbar.hide()

    # =============================== الحفظ / التثبيت ===============================
    def _persist_payload(self, employe_id: int, params_version: str,
                         conv: dict):
        v = self._header.values()
        view = self._view
        bulletin = {
            "employe_id": employe_id,
            "periode": v["periode"],
            "type": "NORMAL",
            "etat": "CALCULE",
            "params_version": params_version,
            "convention_version": int(conv.get("version", 1)),
            "total_a": view.a, "total_b": view.b, "total_c": view.c,
            "total_d": view.d, "net_e": view.e,
            "avertissements_json": list(view.avertissements),
        }
        out_lignes: List[dict] = []
        ordre = 0
        for l in view.lignes:
            out_lignes.append({
                "ordre_affichage": ordre, "zone": l.zone,
                "code_snapshot": l.code or l.key,
                "libelle_snapshot": l.libelle, "sens_snapshot": l.sens,
                "cotisable_snapshot": l.cotisable,
                "imposable_snapshot": l.imposable,
                "regime_irg_snapshot": "BAREME",
                "montant": l.montant,
            })
            ordre += 1
        for code, lib, sens, amount in (
                ("A", "[A] الأجر الخاضع للاشتراك", "GAIN", view.a),
                ("B", "[B] اقتطاع CNAS 9%", "RETENUE", view.b),
                ("C", "[C] الأجر الخاضع للضريبة", "GAIN", view.c),
                ("D", "[D] اقتطاع IRG", "RETENUE", view.d),
                ("E", "[E] الصافي للدفع", "GAIN", view.e)):
            out_lignes.append({
                "ordre_affichage": ordre, "zone": "SYSTEME",
                "ligne_systeme": code, "code_snapshot": f"[{code}]",
                "libelle_snapshot": lib, "sens_snapshot": sens,
                "montant": amount,
            })
            ordre += 1
        return bulletin, out_lignes

    def save(self) -> Optional[int]:
        # ===== مرحلة التحقّق — لا كتابة واحدة قبل اجتيازها كلّها =====
        if self._readonly:
            warn(self, "حفظ", ["الكشف مثبَّت — للقراءة فقط."])
            return None
        errs = self._header.errors()
        if errs:
            warn(self, "حفظ الكشف", errs)
            return None

        v = self._header.values()

        # V16: نسخة المعاملات إلزامية وحقيقية — لا قيمة بديلة («?»).
        #  يُفحَص قبل «لا نتيجة حساب» لأنّ فشل تحميل المعاملات هو سببها.
        try:
            params_version = str(
                config_loader.load_params(f"{v['periode']}-01")["version"])
        except Exception as exc:                        # noqa: BLE001
            warn(self, "نسخة المعاملات غير محدَّدة (V16)", [
                f"تعذّر تحميل معاملات الفترة «{v['periode']}»: {exc}",
                "لا يُحفَظ كشف بلا نسخة معاملات حقيقية — صحّح الفترة."])
            return None

        if self._view is None:
            warn(self, "حفظ الكشف", ["لا نتيجة حساب — أضف أسطراً صحيحة."])
            return None
        if not self._view.lignes:
            warn(self, "حفظ الكشف",
                 ["لا أسطر بقيمة في الكشف — أضف سطراً واحداً على الأقل."])
            return None

        # V3: الصافي للدفع سالب → منع الحفظ (SPEC §6)
        if self._view.e < 0:
            warn(self, "الصافي سالب (V3)", [
                f"الصافي للدفع = {fmt_money(self._view.e)} دج (سالب).",
                "لا يُحفَظ ولا يُثبَّت كشف بصافٍ سالب — راجِع الأسطر."])
            return None

        # V7: سطر حرّ غير مصنَّف صراحةً
        unclassified = self._libre_unclassified()
        if unclassified:
            try:
                for r in unclassified:
                    lignes.validate_free_line(r.form.values())
            except lignes.FreeLineError as exc:
                warn(self, "سطر حرّ غير مصنَّف (V7)", [
                    str(exc),
                    f"عدد الأسطر الحرّة بلا تصنيف: {len(unclassified)}."])
            return None

        # الزبون + اتفاقيته — بلا إنشاء زبون عابر في هذه المرحلة
        free = v.get("client_transient", "").strip()
        if self._client_id is not None:
            client_id, is_new = self._client_id, False
            conv = repository.get_active_convention(client_id, conn=self._conn)
        elif not free:
            client_id = repository.ensure_default_client(conn=self._conn)
            is_new = False
            conv = repository.get_active_convention(client_id, conn=self._conn)
        else:
            client_id, is_new, conv = None, True, None

        # V15 قبل أي كتابة — للزبون المسجَّل/الافتراضي
        if not is_new and (not conv or not conv.get("confirme")):
            warn(self, "الاتفاقية غير مؤكَّدة (V15)", [
                "لا يمكن حفظ كشف لهذا الزبون قبل تأكيد معاملات اتفاقيته.",
                "أكِّد الاتفاقية من إعداداتها ثم أعد المحاولة."])
            return None

        # ===== كل التحقّقات مرّت — من هنا فقط تبدأ الكتابة =====
        if is_new:
            client_id = repository.create_entreprise(
                {"raison_sociale": free, "transient": 1}, conn=self._conn)
            repository.seed_catalogue(client_id, conn=self._conn)
            repository.create_convention(
                client_id, {"confirme": 1}, conn=self._conn)
            conv = repository.get_active_convention(client_id, conn=self._conn)

        employes = repository.list_employes(client_id, conn=self._conn)
        match = next((e for e in employes
                      if e["nom"] == v["employe_nom"]), None)
        if match:
            employe_id = match["id"]
        else:
            employe_id = repository.create_employe(client_id, {
                "nom": v["employe_nom"],
                "date_entree": v["employe_date_entree"] or None,
            }, conn=self._conn)

        bulletin, out_lignes = self._persist_payload(
            employe_id, params_version, conv or {})
        self._bulletin_id = repository.create_bulletin(
            bulletin, out_lignes, conn=self._conn)
        self._client_id = client_id
        self._info.setText(f"حُفِظ الكشف #{self._bulletin_id}.")
        self.bulletinSaved.emit(self._bulletin_id)
        return self._bulletin_id

    def fige(self):
        if self._bulletin_id is None:
            warn(self, "تثبيت", ["احفظ الكشف أولاً."])
            return
        # V3: لا تثبيت لكشف صافيه سالب (SPEC §6)
        if self._view is not None and self._view.e < 0:
            warn(self, "الصافي سالب (V3)", [
                f"الصافي للدفع = {fmt_money(self._view.e)} دج (سالب).",
                "لا يُثبَّت كشف بصافٍ سالب."])
            return
        numero = repository.fige_bulletin(self._bulletin_id, conn=self._conn)
        self._readonly = True
        self._act_save.setEnabled(False)
        self._act_fige.setEnabled(False)
        for row in self._rows:
            row.setEnabled(False)
        self._header.setEnabled(False)
        self._info.setText(f"مثبَّت — رقم السلسلة: {numero}")

    def _print_pdf(self):
        warn(self, "طباعة PDF",
             ["توليد PDF ومسار الأرشفة يُنفَّذان لاحقاً (خارج هذه المرحلة)."])
