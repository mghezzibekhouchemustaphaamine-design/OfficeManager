"""تحميل ملف معاملات الأجور المؤرَّخ المطابق لتاريخ الكشف.

قوانين المالية تتغيّر كل سنة، والبرنامج يجب أن يحسب كشوف سنوات سابقة
بمعاملات تلك السنة — لذا لا رقم قانوني في الكود، والملف يُختار حسب نافذة
صلاحيته (``en_vigueur_du`` / ``en_vigueur_au``).

المسار يُشتق من :func:`programme.paths.get_params_paie_dir` — لا يُكتب
حرفياً هنا.

كل الأرقام تُقرأ كـ :class:`~decimal.Decimal` مباشرة (``parse_float=Decimal``)
فلا يُنشأ ``float`` إطلاقاً على طول سلسلة الحساب.
"""
import json
import os
from datetime import date, datetime
from decimal import Decimal

from programme import paths


class PayrollConfigError(Exception):
    """لا يوجد ملف معاملات أجور يغطّي تاريخ الكشف المطلوب، أو الملف تالف،
    أو أكثر من ملف يغطّي نفس التاريخ (تداخل نوافذ الصلاحية)."""


def _parse_iso_date(value):
    """يقبل كائن ``date`` أو نصاً بصيغة ``YYYY-MM-DD``."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _fichier_couvre(params, d):
    """هل نافذة صلاحية ``params`` تحتوي التاريخ ``d`` ؟
    ``en_vigueur_au = null`` تعني «سارٍ إلى أجل غير مسمّى»."""
    debut = _parse_iso_date(params["en_vigueur_du"])
    if d < debut:
        return False
    fin = params.get("en_vigueur_au")
    if fin is None:
        return True
    return d <= _parse_iso_date(fin)


def params_dir():
    """مجلد ملفات المعاملات — من programme.paths (لا مسار حرفي)."""
    return paths.get_params_paie_dir()


def load_params(date_paie):
    """يرجّع قاموس المعاملات الساري بتاريخ الكشف ``date_paie`` (كائن
    ``date`` أو نص ``YYYY-MM-DD``).

    يفحص كل ``params_*.json`` في :func:`params_dir`، ويختار الوحيد الذي
    تحتوي نافذة صلاحيته هذا التاريخ. يرفع :class:`PayrollConfigError` إن
    لم يوجد أيّ ملف مطابق، أو إن تطابق أكثر من ملف (تداخل نوافذ).
    """
    d = _parse_iso_date(date_paie)
    directory = params_dir()
    try:
        noms = sorted(
            n for n in os.listdir(directory)
            if n.startswith("params_") and n.endswith(".json")
        )
    except OSError as exc:
        raise PayrollConfigError(
            f"تعذّر قراءة مجلد معاملات الأجور: {directory} — {exc}"
        ) from exc

    correspondants = []
    for nom in noms:
        chemin = os.path.join(directory, nom)
        try:
            with open(chemin, encoding="utf-8") as f:
                params = json.load(f, parse_float=Decimal)
        except (OSError, json.JSONDecodeError) as exc:
            raise PayrollConfigError(
                f"ملف معاملات تالف أو غير مقروء: {nom} — {exc}"
            ) from exc
        if _fichier_couvre(params, d):
            correspondants.append((nom, params))

    if not correspondants:
        raise PayrollConfigError(
            f"لا يوجد ملف معاملات أجور يغطّي تاريخ الكشف {d.isoformat()} "
            f"في {directory} (V9)."
        )
    if len(correspondants) > 1:
        liste = "، ".join(n for n, _ in correspondants)
        raise PayrollConfigError(
            f"أكثر من ملف معاملات يغطّي {d.isoformat()}: {liste} — "
            "راجع en_vigueur_du / en_vigueur_au."
        )
    return correspondants[0][1]
