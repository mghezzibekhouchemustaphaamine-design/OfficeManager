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
        started, complete, label = screen._row_status(r)
        if started and not complete:
            res.incomplete_rows.append(Problem(
                screen._row_problem_key(r),
                f"سطر «{label}» ناقص — أكمِل بياناته أو احذف السطر.", "row"))

    # -------- C) معاملات الأجور للفترة (§12) --------
    if (screen._field_present("mois") and screen._field_present("annee")
            and "mois" not in _invalid_keys and "annee" not in _invalid_keys):
        try:
            d = date(int(screen._w("annee")),
                     _MOIS_UP.index(screen._w("mois").upper()) + 1, 1)
        except (ValueError, KeyError):
            d = None
        if d is not None:
            try:
                load_params(d)
            except PayrollConfigError:
                res.payroll_errors.append(Problem(
                    "mois",
                    "لا يوجد ملف معاملات أجور للفترة المحدَّدة "
                    "(‏params_paie).", "payroll"))

    # -------- C) تعذّر الحساب النهائي --------
    if getattr(screen, "_bulletin_view", None) is None:
        res.payroll_errors.append(Problem(
            "", "تعذّر حساب الكشف بالمعطيات الحالية.", "payroll"))

    return res
