"""أنواع أسطر كشف الراتب — الجسر بين واجهة الإدخال والمحرّك.

منطق نطاق، لا منطق عرض (لا PySide6). المحرّك (``calc.py`` / ``irg.py``)
لا يُلمَس — يُستدعى فقط. الشاشة تستدعي هذه الوحدة **حصراً** ولا تبني
:class:`SequenceInput` بنفسها.

كل نوع سطر يعرف:
  • حقوله (ماذا يُدخِل المستخدم)،
  • كيف يطوى في :class:`programme.payroll.calc.SequenceInput` (``fold``)،
  • كم يُعرَض على السطر بعد الحساب (``resolve``)،
  • خصائصه الجبائية ومنها تُشتقّ منطقته آلياً (§2.3.2) — المستخدم لا
    يختار الموقع.

منحتا الأقدمية IEP والمردودية PRI تُمرَّران للمحرّك كـ:class:`Prime`
خاضعة للاشتراك (لا عبر مسار ``anciennete_annees`` الداخلي) حتى تبقى
النسبة **مقترَحة وقابلة للتعديل** (§1.2.4) — القيمة العددية للسطر
مطابقة تماماً لمسار المحرّك في ‎[A]/[B]/[C]/[E]‎.
"""
import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

from programme.payroll.calc import (
    HeureSupp, Prime, Retenue, SequenceInput, SequenceResult, _d, da,
    compute_sequence,
)

_ZERO = Decimal("0")


# ------------------------------------------------------------------ المناطق

def zone_of(*, sens: str, cotisable: bool, imposable: bool) -> str:
    """منطقة السطر (§2.3.2). يوافق **جدول** §2.3.2 والمحرّك:

      • ``RETENUE`` خاضعة للاشتراك (اقتطاع الغياب/التأخّر) → ``Z1``
        بإشارة سالبة، لأنها تُطرح داخل ‎[A] = ΣZ1‎.
      • ``RETENUE`` غير خاضعة (تسبيق، حكم، نقابة، تعاضدية) → ``Z4``.
      • ``GAIN`` خاضعة → ``Z1`` · معفاة وخاضعة لـIRG → ``Z2`` · معفاة
        وغير خاضعة → ``Z3`` (تحت ‎[D]‎).

    (مقتطف الكود المبسّط في §2.3.2 يُرجِع Z4 لكل ``RETENUE`` غير
    CNAS/IRG؛ الجدول والنصّ والمحرّك يخصّون اقتطاع الغياب بـZ1.)"""
    if sens == "RETENUE":
        return "Z1" if cotisable else "Z4"
    if cotisable:
        return "Z1"
    return "Z2" if imposable else "Z3"


ZONE_ORDER = {"Z1": 0, "Z2": 1, "Z3": 2, "Z4": 3}

_TRUTHY = {"1", "true", "نعم", "oui", "yes", "on"}


def _truthy(v) -> bool:
    return str(v).strip().lower() in _TRUTHY


# ------------------------------------------------------------------ الأقدمية (§1.2.4)

@dataclass
class IepSuggestion:
    taux: Optional[Decimal]          # None → لا اقتراح (بلا تاريخ دخول)
    annees: int = 0
    mois: int = 0
    depuis: str = ""                 # تاريخ الدخول كما أُدخِل
    source: str = "sans_date"        # bareme | employe | sous_minimum | sans_date
    raison: str = ""

    def texte_anciennete(self) -> str:
        if not self.depuis:
            return "حدّد تاريخ الدخول للحصول على اقتراح"
        return (f"{self.annees} سنوات و{self.mois} شهر "
                f"(منذ {self.depuis})")


def _period_end(periode: str) -> Optional[date]:
    """``"YYYY-MM"`` → آخر يوم في الشهر (الأقدمية تُحسب حتى نهاية فترة
    الدفع). يقبل ``"YYYY-MM-DD"`` كما هو."""
    parts = str(periode).split("-")
    try:
        y, m = int(parts[0]), int(parts[1])
        d = int(parts[2]) if len(parts) > 2 else calendar.monthrange(y, m)[1]
        return date(y, m, d)
    except (ValueError, IndexError):
        return None


def _annees_mois(debut: date, fin: date) -> Tuple[int, int]:
    months = (fin.year - debut.year) * 12 + (fin.month - debut.month)
    if fin.day < debut.day:
        months -= 1
    months = max(months, 0)
    return months // 12, months % 12


def suggest_iep_taux(*, date_entree: str, periode: str, cfg: Dict,
                     employe_taux_iep=None) -> IepSuggestion:
    """يقترح نسبة الأقدمية (§1.2.4). الطبقات **بالترتيب**:

      أ) ``employe.taux_iep`` مضبوطة → تُستعمل مباشرةً، وتعلو على كلّ
         شيء (قرار صريح في بطاقة العامل، حتى تحت الحدّ الأدنى)،
      ب) وإلا والأقدمية < ``cfg.iep.anciennete_minimale_annees`` → 0%
         مع السبب،
      ج) وإلا → السنوات الكاملة × ``cfg.iep.taux_par_annee``.

    النسبة **مقترَحة لا مفروضة** — الشاشة تعرضها والمستخدم حرّ يعدّلها."""
    debut = _period_end(str(date_entree)) if date_entree else None
    fin = _period_end(periode)
    if debut is None or fin is None:
        return IepSuggestion(taux=None, source="sans_date", depuis="",
                             raison="حدّد تاريخ الدخول للحصول على اقتراح")

    annees, mois = _annees_mois(debut, fin)
    depuis = debut.strftime("%d-%m-%Y")
    min_an = int(_d(cfg["iep"]["anciennete_minimale_annees"]))
    par_an = _d(cfg["iep"]["taux_par_annee"])

    # أ) بطاقة العامل تعلو على كلّ شيء
    if employe_taux_iep not in (None, ""):
        return IepSuggestion(
            taux=_d(employe_taux_iep), annees=annees, mois=mois, depuis=depuis,
            source="employe", raison="من بطاقة العامل (employe.taux_iep)")
    # ب) تحت الحدّ الأدنى → 0%
    if annees < min_an:
        return IepSuggestion(
            taux=_ZERO, annees=annees, mois=mois, depuis=depuis,
            source="sous_minimum",
            raison=(f"الأقدمية ({annees} سنة و{mois} شهر) دون الحدّ الأدنى "
                    f"({min_an} سنة) — المقترَح 0%"))
    # ج) البارِم
    return IepSuggestion(
        taux=annees * par_an, annees=annees, mois=mois, depuis=depuis,
        source="bareme",
        raison=f"{annees} سنة كاملة × {par_an} (نسبة مقترَحة — عدّلها إن لزم)")


# ------------------------------------------------------------------ السياق

@dataclass
class _Ctx:
    cfg: Dict
    convention: Dict
    base_iep_val: Decimal
    base_pri_val: Decimal


# ------------------------------------------------------------------ الأنواع

@dataclass(frozen=True)
class LineField:
    key: str
    label: str
    kind: str                       # ui2.form: amount | number | date | choice | text
    default: str = ""
    choices: Tuple[str, ...] = ()


FoldFn = Callable[[SequenceInput, Dict, "_Ctx", Dict], None]
ResolveFn = Callable[[SequenceResult, Dict, Dict], Decimal]


@dataclass(frozen=True)
class LineType:
    key: str
    libelle: str
    sens: str                       # "GAIN" | "RETENUE" | "" (سطر حرّ)
    cotisable: Optional[int]
    imposable: Optional[int]
    proratisable: bool
    group: str                      # "base" | "autres" | "libre"
    fields: Tuple[LineField, ...]
    fold: FoldFn
    resolve: ResolveFn
    code: str = ""
    system: bool = False            # الأجر القاعدي: يُضاف آلياً، لا يُحذف
    unique: bool = True             # نوع لا يُضاف مرّتين (الاستثناء: التسبيق والسطر الحرّ)
    value_key: str = ""             # الحقل الذي يُعدّ السطر «فارغاً» إن خلا (افتراضاً fields[0])

    # ------- الحقل الحامل للقيمة -------
    def primary_key(self) -> str:
        return self.value_key or (self.fields[0].key if self.fields else "")

    # ------- المنطقة تُشتقّ، لا تُختار -------
    def zone(self, values: Dict) -> str:
        sens = self.sens
        cot = self.cotisable
        imp = self.imposable
        if not sens:                                    # سطر حرّ
            sens = "RETENUE" if _truthy(values.get("est_retenue")) else "GAIN"
        if cot is None:
            cot = 1 if _truthy(values.get("cotisable")) else 0
        if imp is None:
            imp = 1 if _truthy(values.get("imposable")) else 0
        return zone_of(sens=sens, cotisable=bool(cot), imposable=bool(imp))


def _v(values: Dict, key: str) -> Decimal:
    return _d(values.get(key))


# ---- طيّات بسيطة -----------------------------------------------------

def _fold_salaire_base(si, v, ctx, m):
    si.salaire_base = _d(si.salaire_base) + _v(v, "montant")


def _fold_abs_jours(si, v, ctx, m):
    si.jours_absence = _d(si.jours_absence) + _v(v, "jours")


def _fold_abs_heures(si, v, ctx, m):
    si.heures_absence_irreguliere = (
        _d(si.heures_absence_irreguliere) + _v(v, "heures"))


def _fold_retard(si, v, ctx, m):
    si.heures_retard = _d(si.heures_retard) + _v(v, "heures")


def _fold_hs(coef_key, defaut):
    def _f(si, v, ctx, m):
        coef = _d(ctx.convention.get(coef_key) or defaut)
        si.heures_supp.append(HeureSupp(coef=coef, heures=_v(v, "heures")))
        m["hs"] = len(si.heures_supp) - 1
    return _f


def _fold_iep(si, v, ctx, m):
    montant_exact = ctx.base_iep_val * _v(v, "taux")
    si.primes.append(Prime(code="IEP", libelle="منحة الأقدمية",
                           montant=montant_exact,
                           soumis_cotisation=True, imposable=True))
    m["montant"] = da(montant_exact)


def _fold_pri(si, v, ctx, m):
    montant_exact = ctx.base_pri_val * _v(v, "taux")
    si.primes.append(Prime(code="PRI", libelle="منحة المردودية",
                           montant=montant_exact,
                           soumis_cotisation=True, imposable=True))
    m["montant"] = da(montant_exact)


def _fold_transport(si, v, ctx, m):
    si.transport_mensuel = _d(si.transport_mensuel) + _v(v, "montant_mensuel")


def _fold_alloc_fam(si, v, ctx, m):
    si.alloc_familiales = _d(si.alloc_familiales) + _v(v, "montant")


def _fold_prime(code, libelle, cot, imp):
    def _f(si, v, ctx, m):
        si.primes.append(Prime(code=code, libelle=libelle,
                               montant=_v(v, "montant"),
                               soumis_cotisation=bool(cot),
                               imposable=bool(imp)))
    return _f


def _fold_retenue(code, libelle):
    def _f(si, v, ctx, m):
        si.autres_retenues.append(Retenue(code=code, libelle=libelle,
                                          montant=_v(v, "montant")))
    return _f


def _fold_libre(si, v, ctx, m):
    montant = _v(v, "montant")
    if _truthy(v.get("est_retenue")):
        si.autres_retenues.append(Retenue(code="LIBRE",
                                          libelle=v.get("libelle", "سطر حرّ"),
                                          montant=montant))
    else:
        si.primes.append(Prime(
            code="LIBRE", libelle=v.get("libelle", "سطر حرّ"), montant=montant,
            soumis_cotisation=_truthy(v.get("cotisable")),
            imposable=_truthy(v.get("imposable"))))


# ---- حلول العرض ----------------------------------------------------

def _r_input(key):
    return lambda res, v, m: _v(v, key)


def _r_input_round(key):
    return lambda res, v, m: da(_v(v, key))


def _r_meta(res, v, m):
    return m.get("montant", _ZERO)


def _r_hs(res, v, m):
    i = m.get("hs")
    lignes = res.heures_supp_lignes
    return lignes[i] if i is not None and 0 <= i < len(lignes) else _ZERO


#  أسطر الغياب: كل سطر يعرض **حصّته هو** — لا مجموع رُبريكته. يُحسَب من
#  قيمة السطر بنفس معادلة المحرّك ([2b]/[2c]) وبنفس قاعدة عدم التقريب
#  الوسيط (§5.4): معدّل بدقّة كاملة × كمّية السطر، ثم ``da`` مرّة واحدة.
#  (أنواع الغياب فريدة — سطر واحد لكل نوع — فحصّة السطر = مجموع الرُبريكة،
#  لكن الصيغة الصحيحة هي حصّة السطر لا قراءة المجموع.)

def _r_abs_jours(res, v, m):
    return da(res.taux_journalier * _v(v, "jours"))


def _r_abs_heures(res, v, m):
    return da(res.taux_horaire * _v(v, "heures"))


def _r_retard(res, v, m):
    return da(res.taux_horaire * _v(v, "heures"))


LINE_TYPES: Dict[str, LineType] = {
    "salaire_base": LineType(
        "salaire_base", "الأجر القاعدي", "GAIN", 1, 1, True, "base",
        (LineField("montant", "المبلغ الشهري", "amount"),),
        _fold_salaire_base, _r_input("montant"), code="1000", system=True),

    "abs_jours": LineType(
        "abs_jours", "اقتطاع أيام غياب", "RETENUE", 1, 1, False, "base",
        (LineField("jours", "عدد الأيام", "amount"),),
        _fold_abs_jours, _r_abs_jours, code="4000"),

    "abs_heures": LineType(
        "abs_heures", "اقتطاع ساعات غياب", "RETENUE", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_abs_heures, _r_abs_heures, code="4010"),

    "retard": LineType(
        "retard", "اقتطاع ساعات تأخّر", "RETENUE", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_retard, _r_retard, code="4020"),

    "hs_50": LineType(
        "hs_50", "ساعات إضافية 50%", "GAIN", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_hs("taux_hs_jour", "1.5"), _r_hs, code="1010"),

    "hs_100": LineType(
        "hs_100", "ساعات إضافية 100%", "GAIN", 1, 1, False, "base",
        (LineField("heures", "عدد الساعات", "amount"),),
        _fold_hs("taux_hs_nuit", "2.0"), _r_hs, code="1010"),

    "iep": LineType(
        "iep", "منحة الأقدمية IEP", "GAIN", 1, 1, True, "base",
        (LineField("taux", "النسبة (مثلاً 0.09)", "amount"),),
        _fold_iep, _r_meta, code="1020"),

    "pri": LineType(
        "pri", "منحة المردودية PRI", "GAIN", 1, 1, True, "base",
        (LineField("taux", "النسبة (مثلاً 0.15)", "amount"),),
        _fold_pri, _r_meta, code="1030"),

    "panier": LineType(
        "panier", "منحة السلة", "GAIN", 0, 1, True, "base",
        (LineField("montant_mensuel", "المبلغ الشهري", "amount"),),
        lambda si, v, ctx, m: setattr(
            si, "panier_mensuel", _d(si.panier_mensuel) + _v(v, "montant_mensuel")),
        lambda res, v, m: res.panier, code="2000"),

    "transport": LineType(
        "transport", "منحة النقل", "GAIN", 0, 1, True, "base",
        (LineField("montant_mensuel", "المبلغ الشهري", "amount"),),
        _fold_transport, lambda res, v, m: res.transport, code="2010"),

    "avance": LineType(
        "avance", "تسبيق على الراتب", "RETENUE", 0, 0, False, "base",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_retenue("AVANCE", "تسبيق على الراتب"),
        _r_input_round("montant"), code="5010", unique=False),

    # ---------------- أخرى ----------------
    #  حُذفت نهائياً (المراجعة الميدانية): منحة المنطقة · منحة إنابة/معلّم
    #  تمهين · اقتطاع تعاضدية · اقتطاع بحكم قضائي — يغطّيها السطر الحرّ.
    "nuit": LineType(
        "nuit", "منحة ليلية", "GAIN", 1, 1, True, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_prime("NUIT", "منحة ليلية", 1, 1),
        _r_input_round("montant"), code="1070"),

    "syndicat": LineType(
        "syndicat", "الاشتراك النقابي", "RETENUE", 0, 0, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_retenue("SYND", "الاشتراك النقابي"),
        _r_input_round("montant"), code="5030"),

    "conge_paye": LineType(
        "conge_paye", "تعويض عطلة (تصفية)", "GAIN", 1, 1, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_prime("CP", "تعويض عطلة", 1, 1),
        _r_input_round("montant"), code="1060"),

    "alloc_fam": LineType(
        "alloc_fam", "المنح العائلية", "GAIN", 0, 0, False, "autres",
        (LineField("montant", "المبلغ", "amount"),),
        _fold_alloc_fam, _r_input("montant"), code="3010"),

    # --------------------------- السطر الحرّ ---------------------------
    #  تسمية ومبلغ حرّان + تصنيف صريح. ``cotisable``/``imposable``
    #  إلزاميان بلا قيمة افتراضية (V7 / SPEC §2.1) — تُفرَض بـ
    #  :func:`validate_free_line`. المنطقة تُشتقّ من التصنيف عبر
    #  :meth:`LineType.zone` (§2.3.2) — أربع حالات.
    "libre": LineType(
        "libre", "سطر حرّ", "", None, None, False, "libre",
        (
            LineField("libelle", "التسمية", "text"),
            LineField("montant", "المبلغ", "amount"),
            LineField("est_retenue", "اقتطاع؟", "choice",
                      choices=("لا", "نعم")),
            LineField("cotisable", "خاضع للاشتراك؟ (إلزامي)", "choice",
                      choices=("—", "نعم", "لا")),
            LineField("imposable", "خاضع للضريبة؟ (إلزامي)", "choice",
                      choices=("—", "نعم", "لا")),
        ),
        _fold_libre, _r_input_round("montant"), code="LIBRE",
        unique=False, value_key="montant"),
}


class FreeLineError(ValueError):
    """سطر حرّ بلا تصنيف صريح (V7)."""


_UNSET = ("", "—")


def free_line_classified(values: Dict) -> bool:
    """صحيح إن صُنِّف السطر الحرّ صراحةً (خاضع/غير خاضع لكلٍّ من
    الاشتراك والضريبة)."""
    return (str(values.get("cotisable", "")).strip() not in _UNSET
            and str(values.get("imposable", "")).strip() not in _UNSET)


def validate_free_line(values: Dict) -> None:
    """يرفع :class:`FreeLineError` إن لم يُصنَّف السطر الحرّ صراحةً."""
    for k, label in (("cotisable", "خاضع للاشتراك"),
                     ("imposable", "خاضع للضريبة")):
        if str(values.get(k, "")).strip() in _UNSET:
            raise FreeLineError(
                f"السطر الحرّ: حدِّد «{label}؟» صراحةً — لا قيمة افتراضية "
                f"(V7 / SPEC §2.1).")


# ------------------------------------------------------------------ النتيجة

@dataclass
class LineView:
    key: str
    libelle: str
    zone: str
    sens: str
    montant: Decimal
    code: str = ""
    cotisable: Optional[int] = None
    imposable: Optional[int] = None
    #  معدّلٌ دقيق اختياريّ للعرض فقط (مراجعة عن بعد E4.8 §4) — hs_50/
    #  hs_100 حالياً: taux_horaire × coef **بلا تقريب**، مستقلٌّ عن مبلغ
    #  السطر المقرَّب. ``None`` لبقيّة الأنواع؛ لا يدخل أيّ حساب مالي —
    #  العرض (Qt/PDF/Word) يُنسِّقه فقط، لا يعيد اشتقاقه.
    taux: Optional[Decimal] = None


@dataclass
class BulletinView:
    lignes: List[LineView] = field(default_factory=list)
    a: Decimal = _ZERO
    b: Decimal = _ZERO
    c: Decimal = _ZERO
    d: Decimal = _ZERO
    e: Decimal = _ZERO
    avertissements: List[str] = field(default_factory=list)
    result: Optional[SequenceResult] = None


def _convention_kwargs(convention: Dict) -> Dict:
    out: Dict = {}
    for k in ("base_iep", "base_pri", "prorata_panier_transport"):
        if convention.get(k):
            out[k] = convention[k]
    if convention.get("retard_reduit_heures_presence") is not None:
        out["retard_reduit_heures_presence"] = bool(
            convention["retard_reduit_heures_presence"])
    return out


_RATE_PRIMES = ("iep", "pri")

#  أنواع تُطوى كـ:class:`Prime` عامّ مصنَّف (``soumis_cotisation`` /
#  ``imposable`` حرّان يقرآن من كتالوج الزبون). ``panier``/``transport``
#  ضمنها، لكن لهما مسار خاصّ في المحرّك (``si.panier_mensuel``) يُستعمل
#  **فقط** عند التصنيف الافتراضي ``(0, 1)`` (غير خاضع اشتراك / خاضع ضريبة
#  → Z2) للحفاظ على تنسيب §1.2.3؛ عند إعادة تصنيفهما من الكتالوج يُطويان
#  كـ Prime عامّ **بلا تنسيب §1.2.3** (قيد موثَّق — تنسيب §1.2.3 مقصور
#  على المسار الخاصّ في المحرّك، وتغييره يمسّ calc.py).
_ENGINE_PRIME_KEYS = {"nuit", "conge_paye", "panier", "transport"}
_PT_KEYS = {"panier", "transport"}
_PT_DEFAULT_CLASS = (0, 1)

# نوع الكتالوج المُمرَّر: ``{code: {"cotisable": bool, "imposable": bool}}``
CatalogueClass = Optional[Dict[str, Dict[str, bool]]]


def _effective_class(lt: LineType, catalogue: CatalogueClass):
    """تصنيف السطر الفعلي: ``(cotisable, imposable, matched)``.

    كتالوج الزبون (``rubrique_catalogue``) يُعلو على الثابت في
    :data:`LINE_TYPES` لكلّ نوع له ``code`` مطابق — سياسة مؤسسة ثابتة
    (§2.1 من المواصفة)، لا تُعاد كل كشف. السطر الحرّ (‏``cotisable`` =
    ``None``) لا يمسّه الكتالوج (مصدره تصنيف السطر نفسه، V7). ``matched``
    = «لا حاجة لتحذير» (وُجد في الكتالوج، أو سطر حرّ، أو لا كتالوج أصلاً)."""
    if lt.cotisable is None:                          # سطر حرّ
        return None, None, True
    if catalogue is None:                             # لا زبون / لم يُحمَّل
        return lt.cotisable, lt.imposable, True
    row = catalogue.get(lt.code)
    if row is not None:
        return (int(bool(row.get("cotisable"))),
                int(bool(row.get("imposable"))), True)
    return lt.cotisable, lt.imposable, False          # لا صفّ لهذا الرمز → تحذير


def compute_bulletin(entries: List[Dict], cfg: Dict,
                     convention: Optional[Dict] = None,
                     catalogue: CatalogueClass = None) -> BulletinView:
    """``entries`` = ``[{"type": <clé>, "values": {...}}, …]``.

    يطوي كل الأسطر في :class:`SequenceInput` واحد، يستدعي المحرّك، ثم
    يبني عرضاً مُصنَّفاً بالمناطق + ‎[A]…[E]‎ + التحذيرات.

    ``catalogue`` (اختياري): ``{code: {"cotisable", "imposable"}}`` —
    تصنيف كل رمز حسب كتالوج الزبون النشط. حين يُمرَّر، تصنيف الرمز المطابق
    يُعلو على الثابت في :data:`LINE_TYPES` (المنطقة تُشتقّ منه ثم تُقفَل)؛
    رمز بلا صفّ في الكتالوج → الثابت + تحذير غير حاجب.

    تمريرتان فقط عندما تكون قاعدة IEP/PRI = ``SAL_BASE_APRES_ABSENCES``
    (نحتاج ``retenue_absence`` أولاً)؛ وإلا تمريرة واحدة."""
    convention = convention or {}
    parsed: List[Tuple[LineType, Dict]] = []
    for e in entries:
        lt = LINE_TYPES.get(e.get("type"))
        if lt is None:
            continue
        v = e.get("values", {})
        # سطر بحقل القيمة فارغاً → لا يُطوى ولا يُعرَض (لا احتساب صامت
        # بـ0,00)؛ الشاشة تُنبّه «أدخل القيمة» في منطقة الأسطر.
        pk = lt.primary_key()
        if pk and str(v.get(pk, "")).strip() == "":
            continue
        # سطر حرّ غير مصنَّف (V7) → لا يُطوى ولا يُعرَض؛ الشاشة تمنع الحفظ
        if lt.key == "libre" and not free_line_classified(v):
            continue
        parsed.append((lt, v))
    eff = [_effective_class(lt, catalogue) for lt, _ in parsed]
    kw = _convention_kwargs(convention)
    sb_total = sum((_v(v, "montant") for lt, v in parsed
                    if lt.key == "salaire_base"), _ZERO)

    base_iep_mode = convention.get("base_iep") or "SAL_BASE_BRUT"
    base_pri_mode = convention.get("base_pri") or "SAL_BASE_BRUT"
    has_rate = any(lt.key in _RATE_PRIMES for lt, _ in parsed)
    needs_ra = has_rate and "SAL_BASE_APRES_ABSENCES" in (
        base_iep_mode, base_pri_mode)

    def build(include_rate: bool, ctx: _Ctx):
        si = SequenceInput()
        metas: List[Dict] = []
        for (lt, v), (cot, imp, _matched) in zip(parsed, eff):
            m: Dict = {}
            metas.append(m)
            if lt.key in _RATE_PRIMES and not include_rate:
                continue
            # نوع «prime عامّ مصنَّف» — يُطوى بتصنيف الكتالوج/الثابت،
            # ما لم يكن panier/transport بالتصنيف الافتراضي (0,1) فيمرّ
            # عبر مساره الخاصّ في المحرّك (تنسيب §1.2.3).
            if lt.key in _ENGINE_PRIME_KEYS and not (
                    lt.key in _PT_KEYS and (cot, imp) == _PT_DEFAULT_CLASS):
                montant = _v(v, lt.primary_key())
                si.primes.append(Prime(
                    code=lt.code, libelle=lt.libelle, montant=montant,
                    soumis_cotisation=bool(cot), imposable=bool(imp)))
                m["prime_montant"] = da(montant)
            else:
                lt.fold(si, v, ctx, m)
        return si, metas

    ctx0 = _Ctx(cfg, convention, sb_total, sb_total)
    ra = _ZERO
    if needs_ra:
        si0, _ = build(False, ctx0)
        ra = compute_sequence(si0, cfg, **kw).retenue_absence

    ctx = _Ctx(
        cfg, convention,
        sb_total if base_iep_mode == "SAL_BASE_BRUT" else sb_total - ra,
        sb_total if base_pri_mode == "SAL_BASE_BRUT" else sb_total - ra,
    )
    si, metas = build(True, ctx)
    res = compute_sequence(si, cfg, **kw)

    views: List[LineView] = []
    for (lt, v), m, (cot, imp, _matched) in zip(parsed, metas, eff):
        sens = lt.sens or (
            "RETENUE" if _truthy(v.get("est_retenue")) else "GAIN")
        libelle = lt.libelle
        if lt.key == "libre" and v.get("libelle"):
            libelle = str(v["libelle"])
        if cot is None:                              # سطر حرّ → من قيَم السطر
            zone = lt.zone(v)
            cot = int(_truthy(v.get("cotisable")))
            imp = int(_truthy(v.get("imposable")))
        else:
            # §2.3.2: المنطقة تُشتقّ من التصنيف الفعلي (كتالوج أو ثابت)
            # ثم تُقفَل — لا تُستنتَج من موضع السطر (نفس مبدأ V7).
            zone = zone_of(sens=sens, cotisable=bool(cot), imposable=bool(imp))
        montant = m["prime_montant"] if "prime_montant" in m else lt.resolve(
            res, v, m)
        #  مراجعة عن بعد E4.8 §4: معدّلٌ دقيق للعرض لأنواع hs_50/hs_100 —
        #  من res.heures_supp_taux (نفس فهرس res.heures_supp_lignes)، لا
        #  اشتقاقاً من montant المقرَّب أعلاه.
        taux_exact = (res.heures_supp_taux[m["hs"]]
                      if "hs" in m and 0 <= m["hs"] < len(res.heures_supp_taux)
                      else None)
        views.append(LineView(
            key=lt.key, libelle=libelle, zone=zone, sens=sens,
            montant=montant, code=lt.code, cotisable=cot, imposable=imp,
            taux=taux_exact))
    views.sort(key=lambda x: ZONE_ORDER.get(x.zone, 9))

    # تحذير غير حاجب: رمز لا صفّ له في كتالوج الزبون → تصنيف افتراضي.
    # مرّة واحدة لكل رمز غير مطابق (لا لكل سطر ولا لكل إعادة حساب).
    avertissements = list(res.avertissements)
    warned: set = set()
    for (lt, _v0), (_c, _i, matched) in zip(parsed, eff):
        if not matched and lt.code not in warned:
            warned.add(lt.code)
            avertissements.append(
                f"الرُبريكة «{lt.libelle}» تستعمل تصنيفاً افتراضياً — لا "
                f"كتالوج مخصَّص لهذا الزبون لهذا الرمز ({lt.code}).")

    # حارس القيد الموثَّق: سلة/نقل بتصنيف مُعاد (غير الافتراضي (0,1))
    # **مع وجود غياب في نفس الكشف** → مبلغها لم يُنسَّب على الغياب (تنسيب
    # §1.2.3 مقصور على المسار الافتراضي في المحرّك). تحذير غير حاجب حتى لا
    # يمرّ فرق حقيقي في الصافي بصمت قبل توسيع calc.py. (التأخّر مستثنى —
    # §1.2.3 لا يطرحه من ساعات الحضور أصلاً.)
    a_absence = (_d(si.jours_absence) + _d(si.heures_absence_irreguliere)
                 + _d(si.heures_absence_justifiee))
    if a_absence > _ZERO:
        for (lt, _v1), (cot, imp, _m2) in zip(parsed, eff):
            if lt.key in _PT_KEYS and (cot, imp) != _PT_DEFAULT_CLASS:
                avertissements.append(
                    f"منحة «{lt.libelle}» بتصنيف مخصَّص لا تُنسَّب على "
                    f"الغياب في هذا الإصدار (§1.2.3 مقصورة على المسار "
                    f"الافتراضي) — المبلغ المعروض كامل غير منسَّب.")

    return BulletinView(
        lignes=views, a=res.assiette_cnas, b=res.retenue_cnas,
        c=res.assiette_irg, d=res.irg, e=res.net_a_payer,
        avertissements=avertissements, result=res)
