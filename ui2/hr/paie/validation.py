"""تحقّق مرن لشاشة كشف الراتب (Phase B) — نموذج ``ValidationResult`` محليّ.

المبدأ الحاكم::

    العمل يمكن حفظه ناقصًا. الوثيقة النهائية لا تُصدر ناقصة.

يفصل التحقّق ثلاثة مستويات (لا تُخلَط في صناديق حوار):

* **invalid** — حقلٌ غير صالح شكلياً (صيغة تاريخ مستحيلة، تاريخ في
  المستقبل، علاقة ميلاد/دخول). ``DateField`` يحسب هذا بنفسه؛ هنا نقرأ
  ``error_text()`` فقط.
* **missing** — حقلٌ إلزاميّ للإصدار النهائي تُرك فارغاً.
* **row** — Rubrique اختيارية بدأها المستخدم وتركها ناقصة بما يمنع حسابها.
* **payroll** — الأجر القاعديّ ناقص/غير موجب، أو لا معاملات أجور للفترة،
  أو تعذّر الحساب النهائي.

ليس Framework عامّاً: دالة واحدة (:func:`validate_screen`) تقرأ الشاشة
وتُرجع :class:`ValidationResult`. قابلة للاستخراج لاحقاً إن أثبتت الحاجة.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from programme.payroll.config_loader import PayrollConfigError, load_params
from ui.hr.constants import MOIS_FR

_MOIS_UP = [m.upper() for m in MOIS_FR]

#  الحقول الإلزامية للإصدار النهائي (§2) — (مفتاح widget، تسمية عربية).
REQUIRED_FIELDS = (
    ("emp_raison_sociale", "اسم الشركة"),
    ("emp_adresse", "عنوان الشركة"),
    ("emp_cnas", "رقم انخراط الشركة في CNAS"),
    ("mois", "الشهر"),
    ("annee", "السنة"),
    ("id_nom", "اسم الأجير"),
    ("id_prenom", "لقب الأجير"),
    ("id_date_naissance", "تاريخ الميلاد"),
    ("id_lieu_naissance", "مكان الميلاد"),
    ("id_date_embauche", "تاريخ الدخول"),
    ("id_fonction", "المهنة"),
)

#  صراحةً غير إلزامية (§9) — القيمة الفارغة فيها صحيحة.
OPTIONAL_FIELDS = ("id_matricule", "id_num_ss", "id_situation_familiale")


def _num(value) -> float:
    s = (str(value or "").strip()
         .replace(" ", "").replace(" ", "").replace(",", "."))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


@dataclass
class Problem:
    """مشكلة تحقّق واحدة. ``key`` مفتاح widget أو خلية صفّ
    (‏``r{rid}_{cell}``) للإبراز/التركيز؛ ``""`` = مشكلة عامّة بلا حقل."""

    key: str
    label: str
    kind: str          # "missing" | "invalid" | "row" | "payroll"


@dataclass
class ValidationResult:
    missing_required: list = field(default_factory=list)
    invalid_fields: list = field(default_factory=list)
    incomplete_rows: list = field(default_factory=list)
    payroll_errors: list = field(default_factory=list)

    @property
    def problems(self):
        """كلّ المشاكل — الشكليّة أوّلاً ثمّ النواقص ثمّ الأسطر ثمّ الحساب."""
        return (list(self.invalid_fields) + list(self.missing_required)
                + list(self.incomplete_rows) + list(self.payroll_errors))

    @property
    def is_incomplete(self) -> bool:
        return bool(self.problems)

    @property
    def ready_for_final(self) -> bool:
        return not self.problems

    def keys(self) -> set:
        """مفاتيح الحقول/الخلايا التي عليها مشكلة (للإبراز)."""
        return {p.key for p in self.problems if p.key}

    def first_key(self, nav_order):
        """أوّل مفتاح مشكلة بترتيب التنقّل (للتركيز عند محاولة الإصدار)."""
        ks = self.keys()
        for k in nav_order:
            if k in ks:
                return k
        return next(iter(ks), None)

    def summary_lines(self):
        return [p.label for p in self.problems]


def _dec(value) -> Decimal:
    s = str(value or "").strip().replace(" ", "").replace(",", ".")
    if not s:
        return Decimal("0")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


#  مراجعة عن بعد E4.8 §6: حضورٌ مستحيل يمنع **الإصدار النهائي فقط** —
#  الحفظ يبقى مسموحاً دائماً (§4، ``_on_save`` لا يستشير هذا التحقّق
#  أصلاً). لا تغيير على أيّ صيغة حسابٍ في calc.py/lignes.py، ولا حدّاً
#  قانونياً جديداً للساعات الإضافيّة (تبقى قاعدتها الحالية: موجبة فقط).
def _attendance_problems(screen, cfg) -> list:
    jours_mois = _dec(cfg.get("jours_mois"))
    heures_mois = _dec(cfg.get("heures_mois"))

    def _row(kind):
        return next((r for r in screen._rows if r.kind == kind), None)

    abs_jours_row = _row("abs_jours")
    abs_heures_row = _row("abs_heures")
    retard_row = _row("retard")

    abs_jours = _dec(abs_jours_row.val("qty")) if abs_jours_row else Decimal("0")
    abs_heures = _dec(abs_heures_row.val("qty")) if abs_heures_row else Decimal("0")
    retard = _dec(retard_row.val("qty")) if retard_row else Decimal("0")

    problems = []
    if abs_jours_row is not None and abs_jours > 0:
        if jours_mois <= 0 or abs_jours > jours_mois:
            problems.append(Problem(
                screen._row_problem_key(abs_jours_row),
                f"غياب الأيام ({abs_jours}) يتجاوز أيام الشهر الفعليّة "
                f"({jours_mois}) — قيمةٌ مستحيلة.", "payroll"))
    if abs_heures_row is not None and abs_heures > 0:
        if heures_mois <= 0 or abs_heures > heures_mois:
            problems.append(Problem(
                screen._row_problem_key(abs_heures_row),
                f"غياب الساعات ({abs_heures}) يتجاوز ساعات الشهر الفعليّة "
                f"({heures_mois}) — قيمةٌ مستحيلة.", "payroll"))
    if retard_row is not None and retard > 0:
        if heures_mois <= 0 or retard > heures_mois:
            problems.append(Problem(
                screen._row_problem_key(retard_row),
                f"ساعات التأخّر ({retard}) تتجاوز ساعات الشهر الفعليّة "
                f"({heures_mois}) — قيمةٌ مستحيلة.", "payroll"))

    #  الحالة المُجمَّعة: كسر غياب الأيام/الساعات معاً (§6 «attendance
    #  absence fraction») يجب ألا يتجاوز 1 — منفصلٌ عن سقف كلّ خليّةٍ
    #  بمفردها أعلاه (قد يكون كلٌّ منهما ضمن سقفه الخاصّ لكن مجموعهما
    #  يتجاوز شهراً كاملاً).
    if jours_mois > 0 and heures_mois > 0:
        absence_fraction = (abs_jours / jours_mois) + (abs_heures / heures_mois)
        if absence_fraction > 1:
            problems.append(Problem(
                "", "مجموع نسبة غياب الأيام والساعات معاً يتجاوز 100% من "
                "الشهر — قيمةٌ مستحيلة.", "payroll"))
        total_reducers = ((abs_jours / jours_mois)
                          + ((abs_heures + retard) / heures_mois))
        if total_reducers > 1:
            problems.append(Problem(
                "", "مجموع مُنقِصات وقت الأجر (غياب + تأخّر) معاً يتجاوز "
                "100% من الشهر — قيمةٌ مستحيلة.", "payroll"))
    return problems


def _month_known(text: str) -> bool:
    return text.strip().upper() in _MOIS_UP


def _year_plausible(text: str) -> bool:
    t = text.strip()
    return t.isdigit() and len(t) == 4 and 1900 <= int(t) <= 2200


def validate_screen(screen) -> ValidationResult:
    """يقرأ :class:`~ui2.hr.paie.bulletin_template.BulletinTemplateScreen`
    ويُرجع نتيجة تحقّق كاملة في مرور واحد (§8)."""
    res = ValidationResult()

    # -------- A) حقول غير صالحة شكلياً (DateField يحسبها) --------
    for key, label in REQUIRED_FIELDS:
        msg = screen._field_error(key)
        if msg:
            res.invalid_fields.append(Problem(key, f"{label}: {msg}", "invalid"))
    #  الشهر/السنة: نصّ حرّ — نفحص المعقولية هنا (ليست حقول تاريخ).
    if screen._field_present("mois") and not _month_known(screen._w("mois")):
        res.invalid_fields.append(
            Problem("mois", "الشهر: اسم شهر فرنسيّ غير معروف.", "invalid"))
    if screen._field_present("annee") and not _year_plausible(screen._w("annee")):
        res.invalid_fields.append(
            Problem("annee", "السنة: أدخل سنة من أربعة أرقام.", "invalid"))

    _invalid_keys = {p.key for p in res.invalid_fields}

    # -------- B) حقول إلزامية ناقصة (لا نكرّر ما صُنّف invalid) --------
    for key, label in REQUIRED_FIELDS:
        if key in _invalid_keys:
            continue
        if not screen._field_present(key):
            res.missing_required.append(Problem(key, label, "missing"))

    # -------- C) الأجر القاعديّ (§11) --------
    sr = screen._salaire_row()
    if sr is None or _num(sr.val("gain")) <= 0:
        res.payroll_errors.append(Problem(
            screen._row_problem_key(sr) if sr is not None else "",
            "الأجر القاعديّ مطلوب ويجب أن يكون أكبر من صفر.", "payroll"))

    # -------- C) أسطر Rubrique بدأها المستخدم وتركها ناقصة (§10) --------
    for r in screen._rows:
        if r.role == "system" or r.kind == "salaire":
            continue
        #  E.3 §8/§15: حالات «تحتاج مراجعة» من نسخٍ قديمة معطوبة.
        rev = getattr(r, "_review", "")
        if rev == "duplicate_unique":
            res.invalid_fields.append(Problem(
                screen._row_problem_key(r),
                "نوعٌ فريد مكرَّر (IEP) من نسخةٍ قديمة — راجِع هذا السطر: "
                "حوِّله لنوعٍ آخر أو احذفه. لا يُحتسَب في الأجر.", "invalid"))
        elif rev == "free_retenue_ab":
            res.invalid_fields.append(Problem(
                r.cell_key("retenue"),
                "اقتطاع حرّ في منطقة CNAS/IRG غير مدعوم — حوِّله إلى "
                "Absence/Retard، أو انقله لأسفل IRG. لا يُحتسَب حالياً.",
                "invalid"))
        elif rev == "segment_mismatch":
            #  E.3-Review §7: سطرٌ ذكيّ سلطويّ (IEP/HS/Absence/Retard/
            #  Avance) وُجد في نسخةٍ قديمة بمنطقةٍ لا توافق قاعدته —
            #  نُزِّل إلى «حرّ» بواسطة النموذج نفسه؛ يحتاج مراجعةً بشريّة.
            res.invalid_fields.append(Problem(
                screen._row_problem_key(r),
                "نوعٌ ذكيّ من نسخةٍ قديمة وُجد في منطقةٍ غير متوافقة مع "
                "قاعدته — راجِع هذا السطر: أعِد وضعه في منطقته الصحيحة أو "
                "احذفه. لا يُحتسَب بدلالته الأصلية.", "invalid"))
        #  السطر الحرّ (§37): GAIN و RETENUE معاً، أو RETENUE سالبة ⇒ غير
        #  صالح شكلياً. RETENUE حرّة خارج Zone C ⇒ غير مدعومة (§13).
        if r.kind == "free":
            g, ret = r.val("gain").strip(), r.val("retenue").strip()
            if g and ret:
                res.invalid_fields.append(Problem(
                    r.cell_key("retenue"),
                    "سطر حرّ: قيمة في GAIN و RETENUE معاً — احذف إحداهما.",
                    "invalid"))
            if ret.startswith("-"):
                res.invalid_fields.append(Problem(
                    r.cell_key("retenue"),
                    "سطر حرّ: RETENUE تُكتب موجبةً.", "invalid"))
            if ret and not g and r.zone in ("A", "B") and not rev:
                res.invalid_fields.append(Problem(
                    r.cell_key("retenue"),
                    "اقتطاع حرّ في منطقة CNAS/IRG غير مدعوم (§13) — "
                    "استعمل Absence/Retard أو انقله لأسفل IRG.", "invalid"))
        #  E.3-Review §8: «Autre» القديمة (RETENUE) تخضع لنفس قيد §13 —
        #  اقتطاعٌ عامّ خارج Zone C غير مدعوم في المحرّك.
        if r.kind == "autre" and r.val("sens") == "Retenue" \
                and r.zone in ("A", "B") and not rev:
            res.invalid_fields.append(Problem(
                r.cell_key("montant"),
                "اقتطاع «Autre» في منطقة CNAS/IRG غير مدعوم (§8/§13) — "
                "استعمل Absence/Retard، أو انقله لأسفل IRG.", "invalid"))
        #  E.4 §6/§14: CODE رقميّ جزئيّ (١ أو ٢ خانة) غير مكتمل عند
        #  الإصدار النهائيّ — رمزٌ قديمٌ نصّيّ (غير رقميّ، مثل "ABS") مُعفًى
        #  دائماً (§6 «treat it as legacy until user explicitly edits it»).
        if r.kind in ("iep", "hs_50", "hs_100", "abs_jours", "abs_heures",
                     "retard", "avance"):
            code = r.val("code").strip()
            if code and code.isdigit() and len(code) != 3:
                res.invalid_fields.append(Problem(
                    r.cell_key("code"),
                    f"رمز «{code}» رقميّ غير مكتمل — يجب أن يكون 3 أرقام "
                    "بالضبط (§6)، أو استعمل رمزاً نصّياً.", "invalid"))
        started, complete, label = screen._row_status(r)
        if started and not complete:
            res.incomplete_rows.append(Problem(
                screen._row_problem_key(r),
                f"سطر «{label}» ناقص — أكمِل بياناته أو احذف السطر.", "row"))

    # -------- C) معاملات الأجور للفترة (§12) --------
    cfg = None
    if (screen._field_present("mois") and screen._field_present("annee")
            and "mois" not in _invalid_keys and "annee" not in _invalid_keys):
        try:
            d = date(int(screen._w("annee")),
                     _MOIS_UP.index(screen._w("mois").upper()) + 1, 1)
        except (ValueError, KeyError):
            d = None
        if d is not None:
            try:
                cfg = load_params(d)
            except PayrollConfigError:
                res.payroll_errors.append(Problem(
                    "mois",
                    "لا يوجد ملف معاملات أجور للفترة المحدَّدة "
                    "(‏params_paie).", "payroll"))

    # -------- D) حضورٌ مستحيل يمنع الإصدار النهائي فقط (مراجعة عن بعد
    # E4.8 §6) — يحتاج cfg الفترة الفعليّة (jours_mois/heures_mois)،
    # فيُشترَط توفّره من الخطوة أعلاه.
    if cfg is not None:
        res.payroll_errors.extend(_attendance_problems(screen, cfg))

    # -------- C) تعذّر الحساب النهائي --------
    if getattr(screen, "_bulletin_view", None) is None:
        res.payroll_errors.append(Problem(
            "", "تعذّر حساب الكشف بالمعطيات الحالية.", "payroll"))

    return res
