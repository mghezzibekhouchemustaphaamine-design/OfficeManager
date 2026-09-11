"""سلسلة حساب كشف الراتب — التسلسل [1]→[13] من §3 من
docs/specs/SPEC_PAIE_DZ.md، حرفياً وبنفس ترقيم الخطوات.

قواعد صارمة:
  - Decimal حصراً (ممنوع float في حساب المال).
  - **لا تقريب وسيط (§5.4):** المعدلات (الساعي، اليومي، النِّسب) تُحفظ
    بدقة كاملة داخل الحساب؛ يُقرَّب مبلغ كل سطر عند إسناده فقط، و[A]
    وحده يُجمَع من القيم غير المقرّبة.
  - كل رقم قانوني (نسبة CNAS، سلّم IRG، SNMG…) من ملف المعاملات المؤرَّخ
    (programme.payroll.config_loader) — لا شيء مكتوب هنا.
  - قاعدة IEP و PRI من معامل الاتفاقية (base_iep / base_pri) — تُمرَّر
    كوسيط، لا تُثبَّت في الكود. الافتراضي SAL_BASE_BRUT.
  - تنسيب السلة والنقل حسب §1.2.3؛ ساعات التأخّر لا تُخصم من ساعات
    الحضور (retard_reduit_heures_presence=False افتراضياً).

النطاق: العامل الأجير في الحالة العادية فقط — لا منطق متقاعد / معاق.

الدالتان العامّتان:
  - compute_sequence(si, cfg, ...) → SequenceResult   (التسلسل الكامل)
  - compute(data, cfg) → PaieResult                   (مُهايئ شاشة كشف
    الراتب: يبني SequenceInput من PaieInput ويستدعي compute_sequence)
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List

from programme.payroll.irg import calcul_irg, da

_ZERO = Decimal("0")


def _d(value) -> Decimal:
    """أي إدخال (نص/عدد) → Decimal. فارغ أو غير صالح → 0. يقبل الفاصلة
    العشرية الفرنسية والفراغ كفاصل آلاف."""
    if isinstance(value, Decimal):
        return value
    s = str(value if value is not None else "").strip()
    s = s.replace(" ", "").replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not s:
        return _ZERO
    try:
        return Decimal(s)
    except InvalidOperation:
        return _ZERO


def _pos(value) -> Decimal:
    v = _d(value)
    return v if v > _ZERO else _ZERO


# ============================ نموذج البيانات ============================

@dataclass
class Prime:
    """منحة GAIN. cotisable/imposable يحدّدان المنطقة (§2.3.2):
    Z1 (cotisable) · Z2 (!cotisable & imposable) · Z3 (!cotisable & !imposable)."""
    code: str = ""
    libelle: str = ""
    montant: Decimal = _ZERO
    soumis_cotisation: bool = True   # = cotisable (يدخل وعاء CNAS)
    imposable: bool = True           # يدخل وعاء IRG


@dataclass
class Retenue:
    """اقتطاع Z4 (غير CNAS/IRG): تسبيق، حكم قضائي، اشتراك نقابي…"""
    code: str = ""
    libelle: str = ""
    montant: Decimal = _ZERO


@dataclass
class HeureSupp:
    coef: Decimal = _ZERO      # 1.50 نهار · 2.00 ليل/عطلة … (من الاتفاقية)
    heures: Decimal = _ZERO


@dataclass
class SequenceInput:
    """مدخلات التسلسل الكامل [1]→[13]."""
    salaire_base: Decimal = _ZERO
    jours_absence: Decimal = _ZERO
    heures_absence_irreguliere: Decimal = _ZERO
    heures_absence_justifiee: Decimal = _ZERO
    heures_retard: Decimal = _ZERO
    heures_supp: List[HeureSupp] = field(default_factory=list)
    anciennete_annees: Decimal = _ZERO
    taux_pri: Decimal = _ZERO                     # نسبة PRI (0..1)
    primes: List[Prime] = field(default_factory=list)
    panier_mensuel: Decimal = _ZERO
    transport_mensuel: Decimal = _ZERO
    alloc_familiales: Decimal = _ZERO             # Z3
    autres_retenues: List[Retenue] = field(default_factory=list)   # Z4
    temps_plein: bool = True                      # لتطبيق حدّ SNMG
    prorata_jours: Decimal = Decimal("1")         # نسبة أيام العقد (لحدّ SNMG)


@dataclass
class SequenceResult:
    taux_horaire: Decimal = _ZERO            # [1]  (دقة كاملة)
    taux_journalier: Decimal = _ZERO         # [2a] (دقة كاملة)
    retenue_absence: Decimal = _ZERO         # [2]  (مبلغ السطر، مقرّب)
    heures_supp_lignes: List[Decimal] = field(default_factory=list)   # [3] مبالغ مقرّبة بترتيب الإدخال
    heures_supp_total: Decimal = _ZERO       # [3]  (مجموع المبالغ المقرّبة)
    retenue_jours_abs: Decimal = _ZERO       # [2b] سطر مقرّب
    retenue_abs_irreguliere: Decimal = _ZERO # [2c] رُبريكة منفصلة، سطر مقرّب (§2.2)
    retenue_abs_justifiee: Decimal = _ZERO   # [2c] رُبريكة منفصلة، سطر مقرّب
    retenue_retard: Decimal = _ZERO          # [2c] رُبريكة منفصلة، سطر مقرّب
    base_primes: Decimal = _ZERO             # [3b] salaire_base − retenue_absence
    iep: Decimal = _ZERO                     # [4]  (مبلغ السطر، مقرّب)
    prime_rendement: Decimal = _ZERO         # [5]  (مبلغ السطر، مقرّب)
    total_gains: Decimal = _ZERO             # [6]
    assiette_cnas: Decimal = _ZERO           # [7]  = [A] SALAIRE DE POSTE
    retenue_cnas: Decimal = _ZERO            # [8]  = [B]
    assiette_irg: Decimal = _ZERO            # [9]  = [C] BRUT IMPOSABLE
    irg: Decimal = _ZERO                     # [10] = [D]
    total_retenues: Decimal = _ZERO          # [11]
    net_a_payer: Decimal = _ZERO             # [12] = [E]
    cout_employeur: Decimal = _ZERO          # [13]
    heures_presence: Decimal = _ZERO         # §1.2.3
    panier: Decimal = _ZERO                  # Z2 (منسَّب)
    transport: Decimal = _ZERO               # Z2 (منسَّب)
    avertissements: List[str] = field(default_factory=list)   # تحذيرات مراجعة (V2…)


# ============================ التسلسل [1]→[13] ============================

def compute_sequence(
    si: SequenceInput,
    cfg: dict,
    *,
    base_iep: str = "SAL_BASE_BRUT",
    base_pri: str = "SAL_BASE_BRUT",
    prorata_panier_transport: str = "PRORATA_HEURES",
    retard_reduit_heures_presence: bool = False,
) -> SequenceResult:
    heures_mois = _d(cfg["heures_mois"])
    jours_mois = _d(cfg["jours_mois"])
    taux_cnas_sal = _d(cfg["cnas"]["taux_salarie"])
    taux_cnas_emp = _d(cfg["cnas"]["taux_employeur"])
    taux_oeuvres = _d(cfg["cnas"]["taux_oeuvres_sociales"])
    taux_iep_an = _d(cfg["iep"]["taux_par_annee"])
    snmg = _d(cfg["snmg_mensuel"])
    plancher_on = bool(cfg["cnas"].get("appliquer_plancher_snmg"))

    avertissements: List[str] = []
    sb = _pos(si.salaire_base)

    # [1] الأجر الساعي — دقة كاملة، لا تقريب
    taux_horaire = sb / heures_mois if heures_mois else _ZERO

    # [2a] الأجر اليومي — دقة كاملة
    taux_journalier = sb / jours_mois if jours_mois else _ZERO
    # [2b] اقتطاع أيام الغياب · [2c] اقتطاعات ساعات الغياب: أربع رُبريكات
    # منفصلة (§2.2 — «لا تدمجها في رُبريكة واحدة»). كلٌّ يُقرَّب عند إسناده
    # كسطر (§5.4)، ثم تُجمَع السطور المقرّبة.
    ret_jours_abs = da(taux_journalier * _pos(si.jours_absence))
    ret_abs_irreguliere = da(taux_horaire * _pos(si.heures_absence_irreguliere))
    ret_abs_justifiee = da(taux_horaire * _pos(si.heures_absence_justifiee))
    ret_retard = da(taux_horaire * _pos(si.heures_retard))
    retenue_absence = (ret_jours_abs + ret_abs_irreguliere
                       + ret_abs_justifiee + ret_retard)      # مجموع السطور المقرّبة

    # [3] الساعات الإضافية = Σ (taux_horaire × coef × nb_heures)
    hs_exacts = [taux_horaire * _d(h.coef) * _pos(h.heures) for h in si.heures_supp]
    hs_lignes = [da(x) for x in hs_exacts]                    # مبالغ السطور (مقرّبة)

    # [3b] BASE_PRIMES = salaire_base − retenue_absence  (وسيط موثَّق)
    base_primes = sb - retenue_absence
    base_iep_val = sb if base_iep == "SAL_BASE_BRUT" else base_primes
    base_pri_val = sb if base_pri == "SAL_BASE_BRUT" else base_primes

    # [4] IEP · [5] PRI — دقة كاملة ثم تقريب السطر
    iep_exact = base_iep_val * (_pos(si.anciennete_annees) * taux_iep_an)
    pri_exact = base_pri_val * _pos(si.taux_pri)
    iep = da(iep_exact)
    pri = da(pri_exact)

    # ---- تصنيف المنح في المناطق (§2.3.2) ----
    z1_primes_exact = sum((_d(p.montant) for p in si.primes if p.soumis_cotisation), _ZERO)
    z2_primes = sum((da(_d(p.montant)) for p in si.primes
                     if not p.soumis_cotisation and p.imposable), _ZERO)
    z3_primes = sum((da(_d(p.montant)) for p in si.primes
                     if not p.soumis_cotisation and not p.imposable), _ZERO)

    # تنسيب السلة والنقل (§1.2.3)
    abs_hors_retard = (_pos(si.heures_absence_irreguliere)
                       + _pos(si.heures_absence_justifiee))
    if retard_reduit_heures_presence:
        abs_hors_retard += _pos(si.heures_retard)
    heures_presence = heures_mois - abs_hors_retard
    jours_presence = jours_mois - _pos(si.jours_absence)
    if prorata_panier_transport == "AUCUN":
        facteur = Decimal("1")
    elif prorata_panier_transport == "PRORATA_JOURS":
        facteur = (jours_presence / jours_mois) if jours_mois else Decimal("1")
    elif prorata_panier_transport == "PRORATA_MIXTE":
        #  E.4 §3: وضعٌ جديدٌ صريح — غياب الأيام **و** غياب الساعات معاً
        #  يُنقصان الاستحقاق (نسبةً لا حالة تراكميّة)؛ التأخّر مستثنًى
        #  افتراضياً (نفس علم retard_reduit_heures_presence أعلاه). لا
        #  تُغيَّر صيغة خصم الغياب نفسها (يومٌ يبقى salaire_base/jours_mois،
        #  ساعةٌ salaire_base/heures_mois) — هذا حصراً لعامل الحضور
        #  المُستهلَك في تنسيب السلة/النقل.
        fraction_jours = ((_pos(si.jours_absence) / jours_mois)
                          if jours_mois else _ZERO)
        heures_abs_mixte = (_pos(si.heures_absence_irreguliere)
                            + _pos(si.heures_absence_justifiee))
        if retard_reduit_heures_presence:
            heures_abs_mixte += _pos(si.heures_retard)
        fraction_heures = ((heures_abs_mixte / heures_mois)
                           if heures_mois else _ZERO)
        absence_fraction = fraction_jours + fraction_heures
        facteur = max(_ZERO, min(Decimal("1"), Decimal("1") - absence_fraction))
        #  عرضٌ موحَّد لساعات الحضور المكافئة لهذا الوضع فقط — **لا** تُستعمَل
        #  لحساب خصم الغياب (يبقى من heures_absence_* الفعليّة أعلاه، §2).
        heures_presence = heures_mois * facteur
    else:  # PRORATA_HEURES (افتراضي)
        facteur = (heures_presence / heures_mois) if heures_mois else Decimal("1")
    panier = da(_pos(si.panier_mensuel) * facteur)
    transport = da(_pos(si.transport_mensuel) * facteur)

    # [7] ASSIETTE_CNAS = [A]  — §5.4: مكوّنات Z1 غير الغياب (القاعدي،
    # الساعات الإضافية، IEP، PRI، منح Z1) تُجمَع بدقة كاملة؛ أسطر الغياب
    # (رُبريكات منفصلة §2.2) مقرّبة مسبقاً؛ ثم يُقرَّب [A] مرة واحدة.
    a_exact = (sb + sum(hs_exacts, _ZERO) + iep_exact + pri_exact
               + z1_primes_exact - retenue_absence)
    assiette_cnas = da(a_exact)
    # حدّ SNMG (§3 [7]): يُنسَّب على **نسبة العقد فقط** (temps partiel) —
    # لا على الحضور. الغياب لا يخفّض الأرضية إطلاقاً (params.cnas:
    # plancher_prorata = CONTRAT_SEULEMENT). الغياب مخصوم أصلاً في [A]،
    # فتنسيب الأرضية عليه أيضاً خصمٌ مزدوج؛ والأرضية غرضها حماية تمويل
    # CNAS لا معاقبة الغياب.
    #
    # استمارة بلا أجر قاعدي (sb = 0): الأرضية لا تُطبَّق إطلاقاً. الأرضية
    # تحمي أجراً منخفضاً *موجوداً*، ولا تخترع وعاءً من العدم — وإلا لخرج
    # كشفٌ فارغ بصافٍ سالب (‎[A]=24 000 → [B]=2 160 → [E]=−2 160‎).
    if plancher_on and si.temps_plein and sb > _ZERO:
        plancher = da(snmg * _pos(si.prorata_jours))
        # القدرة على الكسب قبل خصم الغياب (نفس معادلة [A] بلا −retenue_absence):
        a_hors_absence = da(sb + sum(hs_exacts, _ZERO) + iep_exact
                            + pri_exact + z1_primes_exact)
        if a_hors_absence < plancher:
            # أجر منخفض فعلاً (لا بسبب غياب) → يُرفَع الوعاء للأرضية
            assiette_cnas = max(assiette_cnas, plancher)
        elif assiette_cnas < plancher:
            # الأرضية لم تُخرَق إلا بسبب غيابات ثقيلة → تحذير V2 (لا رفع،
            # لا منع) حتى يراجعه المستخدم بدل أن يمرّ صامتاً.
            avertissements.append(
                f"V2 (تحذير): وعاء CNAS {assiette_cnas} دون أرضية SNMG "
                f"{plancher} بسبب غيابات مخصومة (فرق {da(plancher - assiette_cnas)}). "
                f"لم يُرفَع تلقائياً — تنسيب الأرضية على الغياب غير محسوم "
                f"بنصّ صريح؛ راجِع مع CNAS."
            )

    # [8] RETENUE_CNAS = [B]
    retenue_cnas = da(assiette_cnas * taux_cnas_sal)

    # [9] ASSIETTE_IRG = [C] = ([A] − [B]) + Σ Z2
    assiette_irg = da((assiette_cnas - retenue_cnas) + panier + transport + z2_primes)

    # [10] IRG = [D]
    irg = calcul_irg(assiette_irg, cfg)

    # [6] TOTAL_GAINS = Σ كل رُبريكات GAIN بمبالغ السطور المقرّبة
    #     (Z1 يتضمّن −retenue_absence، وهو أصلاً مجموع أسطر مقرّبة)
    total_gains = da(
        da(sb) + sum(hs_lignes, _ZERO) + iep + pri + da(z1_primes_exact)
        - retenue_absence
        + panier + transport + z2_primes
        + z3_primes + da(_pos(si.alloc_familiales))
    )

    # [11] TOTAL_RETENUES = [B] + [D] + Σ Z4
    z4_total = sum((da(_d(r.montant)) for r in si.autres_retenues), _ZERO)
    total_retenues = da(retenue_cnas + irg + z4_total)

    # [12] NET_A_PAYER = [E]
    net_a_payer = da(total_gains - total_retenues)

    # [13] COUT_EMPLOYEUR = TOTAL_GAINS + [A]×taux_employeur + [A]×taux_oeuvres_sociales
    cout_employeur = da(total_gains
                        + da(assiette_cnas * taux_cnas_emp)
                        + da(assiette_cnas * taux_oeuvres))

    return SequenceResult(
        taux_horaire=taux_horaire,
        taux_journalier=taux_journalier,
        retenue_absence=retenue_absence,
        retenue_jours_abs=ret_jours_abs,
        retenue_abs_irreguliere=ret_abs_irreguliere,
        retenue_abs_justifiee=ret_abs_justifiee,
        retenue_retard=ret_retard,
        heures_supp_lignes=hs_lignes,
        heures_supp_total=sum(hs_lignes, _ZERO),
        base_primes=da(base_primes),
        iep=iep,
        prime_rendement=pri,
        total_gains=total_gains,
        assiette_cnas=assiette_cnas,
        retenue_cnas=retenue_cnas,
        assiette_irg=assiette_irg,
        irg=irg,
        total_retenues=total_retenues,
        net_a_payer=net_a_payer,
        cout_employeur=cout_employeur,
        heures_presence=da(heures_presence),
        panier=panier,
        transport=transport,
        avertissements=avertissements,
    )


# ==================== مُهايئ شاشة كشف الراتب ====================

@dataclass
class PaieInput:
    mois: str = ""
    annee: str = ""
    jours: Decimal = Decimal("30")
    salaire_base: Decimal = _ZERO
    panier: Decimal = _ZERO
    transport: Decimal = _ZERO
    primes: List[Prime] = field(default_factory=list)
    autres_retenues: List[Retenue] = field(default_factory=list)
    # مهجور: السلة والنقل صارتا دائماً في وعاء IRG (Z2 §2.3.2)
    panier_transport_in_irg: bool = False


@dataclass
class PaieResult:
    salaire_poste: Decimal = _ZERO
    base_cnas: Decimal = _ZERO
    retenue_cnas: Decimal = _ZERO
    base_irg: Decimal = _ZERO
    retenue_irg: Decimal = _ZERO
    primes_soumises: Decimal = _ZERO
    primes_non_soumises: Decimal = _ZERO
    autres_retenues_total: Decimal = _ZERO
    panier: Decimal = _ZERO
    transport: Decimal = _ZERO
    total_gain: Decimal = _ZERO
    total_retenue: Decimal = _ZERO
    net_a_payer: Decimal = _ZERO
    avertissements: List[str] = field(default_factory=list)


def compute(data: PaieInput, cfg: dict) -> PaieResult:
    """مُهايئ: يبني SequenceInput من PaieInput (بلا غيابات/أقدمية/ساعات
    إضافية — ما لا تجمعه شاشة كشف الراتب حالياً) ويستدعي التسلسل الكامل،
    ثم يعيد التعيين إلى PaieResult الذي يستهلكه القالب. ``cfg`` إلزامي."""
    primes = [
        Prime(code=p.code, libelle=p.libelle, montant=_d(p.montant),
              soumis_cotisation=p.soumis_cotisation,
              imposable=getattr(p, "imposable", True))
        for p in data.primes
    ]
    si = SequenceInput(
        salaire_base=_d(data.salaire_base),
        primes=primes,
        panier_mensuel=_d(data.panier),
        transport_mensuel=_d(data.transport),
        autres_retenues=list(data.autres_retenues),
    )
    r = compute_sequence(si, cfg)   # الافتراضات: SAL_BASE_BRUT، PRORATA_HEURES، بلا غيابات → facteur=1

    p_soum = sum((_pos(p.montant) for p in data.primes if p.soumis_cotisation), _ZERO)
    p_nsoum = sum((_pos(p.montant) for p in data.primes if not p.soumis_cotisation), _ZERO)
    autres = sum((_pos(x.montant) for x in data.autres_retenues), _ZERO)

    return PaieResult(
        salaire_poste=r.assiette_cnas,
        base_cnas=r.assiette_cnas,
        retenue_cnas=r.retenue_cnas,
        base_irg=r.assiette_irg,
        retenue_irg=r.irg,
        primes_soumises=da(p_soum),
        primes_non_soumises=da(p_nsoum),
        autres_retenues_total=da(autres),
        panier=r.panier,
        transport=r.transport,
        total_gain=r.total_gains,
        total_retenue=r.total_retenues,
        net_a_payer=r.net_a_payer,
        avertissements=list(r.avertissements),
    )


def fmt_montant(x) -> str:
    """تنسيق فرنسي موحّد للمبالغ: فاصلة عشرية، فراغ لآلاف — «49 505,71».
    صفر يُطبَع «0,00» بلا إشارة سالبة.

    **المصدر الوحيد لتنسيق المبالغ في المشروع** — تستعمله شاشة الأجور
    الجديدة (``ui2/paie``) والطبقة القديمة (``ui/hr/paie/template_simple``)
    معاً. (``_d`` يردّ أيّ إدخال غير صالح/فارغ إلى صفر، فلا استثناء.)"""
    d = _d(x)
    if d == 0:
        d = abs(d)                       # يمنع «-0,00»
    return f"{d:,.2f}".replace(",", " ").replace(".", ",")
