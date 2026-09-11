"""طبقة العرض المشتركة لكشف الراتب (Phase E.3 §10/§11 · مُحدَّثة —
مراجعة E.3 §1-§4/§11).

تحوّل :class:`programme.payroll.lignes.BulletinView` (+ لقطة صفوف الشاشة
الاختيارية) إلى **صفوفٍ معروضة ومجاميع معروضة موحّدة** يستهلكها الرسمُ على
الشاشة والمُصيِّر PDF والمُصيِّر DOCX معاً — لا تكرار لمنطق «Gain سالب» ولا
لترتيب الشرائح.

بلا Qt/Tk/ReportLab. تعتمد فقط :func:`programme.payroll.calc.fmt_montant`
(مُنسِّق العرض الموحَّد) و :data:`ui.hr.constants.PAIE_DEFAULT_CODES`.

**فصل المسؤوليّات (مراجعة E.3 §2):**

* المحرّك (``BulletinView``) هو مصدر **المال المحسوب** وحده — لا يعرف
  الموضع البصريّ (segment/order).
* نموذج صفوف الشاشة (:class:`RowSnapshot`، تبنيه ``ui2`` من ``_Row``) هو
  مصدر **الموضع البصريّ وقيَم العرض** (CODE/LIBELLÉ/N-BASE/TAUX كما يراها
  المستخدم، بما فيها تعديلات CODE اليدويّة) — لا يعرف صيغ الحساب.
* :func:`build` يدمج الاثنين: يمشي بترتيب ``rows`` (= ترتيب الشاشة
  الحقيقيّ بالضبط: A → CNAS → B1 → PANIER → B2 → TRANSPORT → B3 → IRG →
  C) ويقرأ **المبلغ المحسوب** لكلّ صفٍّ من ``snapshot.amount`` (يُسنِده
  ``ui2`` عبر مطابقة ``entry()["type"]`` بنفس ترتيب الإرسال للمحرّك —
  See ``BulletinTemplateScreen._assign_computed_amounts``).

بلا ``rows`` (توافقٌ خلفيّ لاختباراتٍ واستدعاءاتٍ تفحص المحرّك مباشرةً)
يعود :func:`build` إلى تجميع الشرائح **تقريبياً** من مناطق ``BulletinView``
فحسب (Salaire → Z1 → CNAS → Panier → Transport → Z2 → IRG → Z3/Z4) — وهو
تحديداً ما يفقد ترتيب B1/B2/B3 الدقيق؛ لا يُستعمَل هذا المسار من الشاشة
الحيّة بعد اليوم.

**المبدأ (§9/§30):** المحرّك يطرح Absence/Retard داخل Z1
(‏``total_gains``) عمداً — لا يُغيَّر. هنا تُعرَض **اقتطاعاً موجباً** في
عمود RETENUE، وتُصالَح المجاميع::

    base_reducers_total   = Σ (مبالغ Absence/Retard المعروضة موجبةً)
    display_total_gain     = engine.total_gains    + base_reducers_total
    display_total_retenue  = engine.total_retenues + base_reducers_total
    display_net            = engine.net_a_payer              (بلا تغيير)

العقد:  ``display_total_gain − display_total_retenue == display_net``.

أرقام المحرّك (وعاء CNAS · اقتطاع CNAS · وعاء IRG · IRG · الصافي) لا تتغيّر.

**نسبة CNAS (مراجعة E.3 §11):** لم تعد تُكتب "9,00" ثابتةً في الكود — تُمرَّر
``cnas_taux`` (القيمة الفعليّة من ``params_paie`` المُحمَّلة) وتُنسَّق هنا
فقط بـ :func:`fmt_rate_pct` (يعيد استعمال ``fmt_montant`` — لا مصدر قانونيّ
ثانٍ). غيابها ⇒ عمودٌ فارغ، لا رقمٌ مخترَع.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from programme.payroll.calc import fmt_montant
from ui.hr.constants import PAIE_DEFAULT_CODES

#  أنواع Z1 المُنقِصة — تُعرَض اقتطاعاً موجباً (§9).
BASE_REDUCERS = ("abs_jours", "abs_heures", "retard")

#  أدنى أسطر تحت IRG (فراغٌ ثابت — SCREEN = PDF).
MIN_ZONE_C_ROWS = 5

_FR_LIBELLE = {
    "salaire_base": "SALAIRE DE BASE",
    "iep": "IND. EXPÉRIENCE PROF.", "pri": "PRIME DE RENDEMENT",
    "hs_50": "HEURES SUPP. 50 %", "hs_100": "HEURES SUPP. 100 %",
    "abs_jours": "ABSENCE (JOURS)", "abs_heures": "ABSENCE (HEURES)",
    "retard": "RETARD", "panier": "PANIER", "transport": "(R+) TRANSPORT",
    "avance": "AVANCE / ACOMPTE", "syndicat": "COTISATION SYNDICALE",
    "nuit": "PRIME DE NUIT", "conge_paye": "CONGÉ PAYÉ",
    "alloc_fam": "ALLOCATIONS FAMILIALES", "libre": "",
}

_ZONE_OF = {"Z1": "A", "Z2": "B", "Z3": "C", "Z4": "C"}

#  أنواع صفوفٍ ذكيّة أصيلة تُعرَض دائماً في GAIN (المبلغ من ``amount``).
#  E.4 §B: hs_50/hs_100 نوعان مستقلّان (كانا "hs" واحداً بمُنتقي).
_GAIN_KINDS = {"salaire", "iep", "hs_50", "hs_100", "panier", "transport"}
#  أنواع تُعرَض دائماً في RETENUE (موجبةً — Absence/Retard §9، Avance).
#  E.4 §B: abs_jours/abs_heures نوعان مستقلّان (كانا "absence" واحداً بمُنتقي).
_RETENUE_KINDS = {"abs_jours", "abs_heures", "retard", "avance"}


@dataclass
class RowSnapshot:
    """لقطة صفّ شاشةٍ واحد — بلا Qt (مراجعة E.3 §2). يبنيها
    ``BulletinTemplateScreen._row_snapshots()`` بترتيب الشاشة الحقيقيّ
    (‏``_visible_body_rows()``)؛ هذا الترتيب هو ما يُستهلَك حرفياً هنا —
    لا يُعاد استنتاجه من ``BulletinView``."""
    rid: int = 0
    kind: str = ""
    role: str = "optional"        # "basic" | "optional" | "system"
    segment: str = ""             # "A"|"B1"|"B2"|"B3"|"C" — "" للثابت
    order: float = 0.0
    zone: str = ""                # "A"|"B"|"C" (مشتقّة) — "" للثابت
    code: str = ""                # CODE المعروض (يشمل التعديل اليدويّ)
    libelle: str = ""             # LIBELLÉ المعروض
    nbase: str = ""                # نصّ خام كما يظهر في عمود N/BASE
    taux: str = ""                 # نصّ خام كما يظهر في عمود TAUX
    gain_input: str = ""          # نصّ خام لخليّة GAIN المُحرَّرة (إن وُجدت)
    retenue_input: str = ""       # نصّ خام لخليّة RETENUE المُحرَّرة (إن وُجدت)
    amount: object = None         # Decimal مبلغٌ محسوبٌ من المحرّك، أو None
    review: str = ""              # "" | "duplicate_unique" | "free_retenue_ab" | …


@dataclass
class PRow:
    """صفٌّ معروض واحد بأعمدة الجدول الستّة."""
    code: str = ""
    libelle: str = ""
    nbase: str = ""
    taux: str = ""
    gain: str = ""
    retenue: str = ""
    key: str = ""            # مفتاح المحرّك (تشخيص)
    zone: str = ""           # A|B|C — فارغٌ للثابت/الفراغ
    kind: str = "line"       # "line" | "system" | "blank"
    rid: int = 0             # rid صفّ الشاشة الأصليّ — 0 للثابت/الفراغ
    review: str = ""         # حالة مراجعة موروثة من RowSnapshot (§9)

    def as_cols(self):
        return {"code": self.code, "libelle": self.libelle,
                "nbase": self.nbase, "taux": self.taux,
                "gain": self.gain, "retenue": self.retenue}


@dataclass
class Presented:
    rows: list = field(default_factory=list)
    total_gain: Decimal = Decimal(0)
    total_retenue: Decimal = Decimal(0)
    net: Decimal = Decimal(0)
    base_reducers_total: Decimal = Decimal(0)

    @property
    def total_gain_str(self):
        return fmt_montant(self.total_gain)

    @property
    def total_retenue_str(self):
        return fmt_montant(self.total_retenue)

    @property
    def net_str(self):
        return fmt_montant(self.net)


def _lib(lv):
    return (_FR_LIBELLE.get(lv.key)
            or (lv.libelle or "").strip().upper() or lv.key.upper())


def _dec(x):
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x).replace(" ", "").replace(",", ".")) if x not in (None, "") \
            else Decimal(0)
    except Exception:                                        # noqa: BLE001
        return Decimal(0)


def fmt_rate_pct(rate) -> str:
    """نسبة (مثلاً ``Decimal("0.09")``) → نصّ عرضٍ بأسلوب :func:`fmt_montant`
    (‏"9,00"). ``None``/غير صالح ⇒ ``""`` — لا رقمٌ مخترَع (§11)."""
    if rate is None or rate == "":
        return ""
    return fmt_montant(_dec(rate) * 100)


def _fmt_display(raw: str) -> str:
    """نصّ خليّةٍ خام → عرضٌ موحَّد: رقمٌ صالح يُنسَّق بـ ``fmt_montant``؛
    أيّ نصٍّ آخر (خيار Absence/HS، أو غير رقميّ) يمرّ كما هو حرفياً — لا
    فقدان بيانات (§5)."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        #  ``_dec`` متساهلة (ترجع صفراً بدل رفع استثناء) — هنا نريد
        #  بالضبط العكس: أيّ نصٍّ ليس رقماً صِرفاً يمرّ كما هو حرفياً
        #  (خيار Absence/HS، أو نسبة كتبها المستخدم بعلامة "%").
        return fmt_montant(Decimal(raw.replace(" ", "").replace(",", ".")))
    except Exception:                                        # noqa: BLE001
        return raw


def _target_col(snap: RowSnapshot):
    """أيّ عمودٍ (GAIN/RETENUE) يحمل مال هذا الصفّ — من نوعه، أو من أيّ
    خليّةٍ فعلاً مملوءة للسطر الحرّ (§3)."""
    if snap.kind in _GAIN_KINDS:
        return "gain"
    if snap.kind in _RETENUE_KINDS:
        return "retenue"
    if snap.gain_input.strip():
        return "gain"
    if snap.retenue_input.strip():
        return "retenue"
    return None


def _row_from_snapshot(snap: RowSnapshot, *, reducers_total: Decimal):
    """‏``RowSnapshot`` (+ مبلغه المحسوب مسبقاً من ``ui2``) → ``PRow``
    واحد. مراجعة E.3 §3/§4/§5: CODE/LIBELLÉ/N-BASE/TAUX من العرض دائماً؛
    GAIN/RETENUE من المبلغ المحسوب حين يوجد، وإلا من القيمة الخام المحفوظة
    (حالات المراجعة القديمة غير المدعومة — §9: لا إخفاء صامت)."""
    col = _target_col(snap)
    gain = retenue = ""
    added_reducer = Decimal(0)
    if col == "gain":
        if snap.amount is not None:
            gain = fmt_montant(abs(_dec(snap.amount)))
        else:
            gain = _fmt_display(snap.gain_input)
    elif col == "retenue":
        if snap.kind in ("abs_jours", "abs_heures", "retard"):
            #  §9: Absence/Retard تُنقِص Z1 داخل المحرّك عمداً (لا يُغيَّر) —
            #  هنا تُعرَض اقتطاعاً **موجباً** دائماً وتُصالَح المجاميع.
            amt = abs(_dec(snap.amount)) if snap.amount is not None else Decimal(0)
            added_reducer = amt
            retenue = fmt_montant(amt)                      # §9: موجبٌ دائماً
        elif snap.amount is not None:
            retenue = fmt_montant(abs(_dec(snap.amount)))
        else:
            #  اقتطاعٌ حرّ غير مدعوم (Zone A/B) أو «Autre» قديم مماثل —
            #  يُعرَض كما كان بالضبط، للمراجعة، لا يدخل الحساب (§9/§13).
            retenue = _fmt_display(snap.retenue_input)
    #  N/BASE · TAUX: نصّ الشاشة كما هو — لا إعادة صياغة لخيارات
    #  Absence/HS، وتنسيقٌ موحَّد للأرقام الصِّرفة فقط.
    nbase = snap.nbase if snap.kind == "free" else _fmt_display(snap.nbase)
    taux = snap.taux if snap.kind == "free" else _fmt_display(snap.taux)
    row = PRow(code=snap.code, libelle=snap.libelle, nbase=nbase, taux=taux,
               gain=gain, retenue=retenue, key=snap.kind, zone=snap.zone,
               rid=snap.rid, review=snap.review)
    return row, added_reducer


def _build_from_rows(view, rows, *, jours, pad_zone_c, cnas_taux):
    c = PAIE_DEFAULT_CODES
    res = view.result
    rate_str = fmt_rate_pct(cnas_taux)
    reducers_total = Decimal(0)
    out = []
    for snap in rows:
        if snap.role == "system" and snap.kind == "cnas":
            out.append(PRow(code=snap.code or c["cnas"],
                            libelle=snap.libelle or "RETENUE SÉCU. SOCIALE",
                            nbase=fmt_montant(res.assiette_cnas), taux=rate_str,
                            retenue=fmt_montant(res.retenue_cnas),
                            kind="system", rid=snap.rid))
            continue
        if snap.role == "system" and snap.kind == "irg":
            out.append(PRow(code=snap.code or c["irg"], libelle=snap.libelle
                            or "RETENUE IRG", nbase=fmt_montant(res.assiette_irg),
                            retenue=fmt_montant(res.irg), kind="system",
                            rid=snap.rid))
            continue
        if snap.kind in ("panier", "transport") and snap.amount is None \
                and not (snap.gain_input or "").strip():
            #  لا سطر محرّك لهذا النوع (صفرٌ لم يُرسَل كـ entry) — صفرٌ
            #  معروضٌ صراحةً (سلوكٌ قديمٌ محفوظ).
            out.append(PRow(code=snap.code, libelle=snap.libelle,
                            gain=fmt_montant(0), zone=snap.zone,
                            rid=snap.rid))
            continue
        prow, added = _row_from_snapshot(snap, reducers_total=reducers_total)
        reducers_total += added
        out.append(prow)

    if pad_zone_c:
        n_c = sum(1 for p in out if p.zone == "C")
        out += [PRow(kind="blank")
               for _ in range(max(0, MIN_ZONE_C_ROWS - n_c))]

    dg = _dec(res.total_gains) + reducers_total
    dr = _dec(res.total_retenues) + reducers_total
    return Presented(rows=out, total_gain=dg, total_retenue=dr,
                     net=_dec(view.e), base_reducers_total=reducers_total)


def _build_from_view_only(view, *, jours, pad_zone_c, cnas_taux):
    """المسار الاحتياطيّ (بلا ``rows``) — تجميعٌ تقريبيّ من مناطق المحرّك
    فحسب. يفقد ترتيب B1/B2/B3 الدقيق (لا يستعمله المسار الحيّ). محفوظٌ
    لتوافق اختباراتٍ تفحص ``BulletinView`` مباشرةً بلا شاشة."""
    c = PAIE_DEFAULT_CODES
    res = view.result
    rate_str = fmt_rate_pct(cnas_taux)
    by_zone = {"Z1": [], "Z2": [], "Z3": [], "Z4": []}
    salaire, pt = None, {}
    for lv in view.lignes:
        if lv.key == "salaire_base":
            salaire = lv
            continue
        if lv.key in ("panier", "transport"):
            pt[lv.key] = lv
            continue
        by_zone.get(lv.zone, by_zone["Z3"]).append(lv)

    reducers_total = Decimal(0)

    def prow(lv):
        nonlocal reducers_total
        row = PRow(code=(lv.code or "").strip(), libelle=_lib(lv),
                   nbase=(fmt_montant(jours)
                          if lv.key == "salaire_base" and jours is not None
                          else ""),
                   key=lv.key, zone=_ZONE_OF.get(lv.zone, "C"))
        if lv.key in BASE_REDUCERS:
            amt = abs(_dec(lv.montant))
            reducers_total += amt
            row.retenue = fmt_montant(amt)          # §9: موجبٌ في RETENUE
        elif lv.sens == "RETENUE":
            row.retenue = fmt_montant(_dec(lv.montant))
        else:
            row.gain = fmt_montant(_dec(lv.montant))
        return row

    rows = []
    if salaire is not None:
        rows.append(prow(salaire))
    rows += [prow(lv) for lv in by_zone["Z1"]]                  # Zone A
    rows.append(PRow(code=c["cnas"], libelle="RETENUE SÉCU. SOCIALE",
                     nbase=fmt_montant(res.assiette_cnas), taux=rate_str,
                     retenue=fmt_montant(res.retenue_cnas), kind="system"))
    for key, lab in (("panier", "PANIER"), ("transport", "(R+) TRANSPORT")):
        if key in pt:
            rows.append(prow(pt[key]))
        else:
            rows.append(PRow(code=c[key], libelle=lab, gain=fmt_montant(0)))
    rows += [prow(lv) for lv in by_zone["Z2"]]                  # Zone B
    rows.append(PRow(code=c["irg"], libelle="RETENUE IRG",
                     nbase=fmt_montant(res.assiette_irg),
                     retenue=fmt_montant(res.irg), kind="system"))
    zc = [prow(lv) for lv in by_zone["Z3"] + by_zone["Z4"]]     # Zone C
    if pad_zone_c:
        zc += [PRow(kind="blank")
               for _ in range(max(0, MIN_ZONE_C_ROWS - len(zc)))]
    rows += zc

    dg = _dec(res.total_gains) + reducers_total
    dr = _dec(res.total_retenues) + reducers_total
    return Presented(rows=rows, total_gain=dg, total_retenue=dr,
                     net=_dec(view.e), base_reducers_total=reducers_total)


def build(view, *, rows=None, jours=None, pad_zone_c=True, cnas_taux=None):
    """‏``BulletinView`` (+ لقطة صفوف الشاشة الاختياريّة ``rows``) →
    :class:`Presented`.

    مع ``rows`` (المسار الحيّ — ``ui2``): يمشي بترتيب الشاشة **الحقيقيّ
    بالضبط** (segment/order)، فيُحافَظ على B1/B2/B3 كما وضعها المستخدم
    (مراجعة E.3 §1/§6). بلا ``rows``: مسارٌ احتياطيّ تقريبيّ من مناطق
    المحرّك فقط (توافقٌ خلفيّ لاختباراتٍ لا تملك شاشة)."""
    if rows is not None:
        return _build_from_rows(view, rows, jours=jours,
                                pad_zone_c=pad_zone_c, cnas_taux=cnas_taux)
    return _build_from_view_only(view, jours=jours, pad_zone_c=pad_zone_c,
                                 cnas_taux=cnas_taux)
