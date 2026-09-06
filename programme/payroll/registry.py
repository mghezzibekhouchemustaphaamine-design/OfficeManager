"""سجلّ موديلات كشف الراتب — بيانات وصفية فقط (مفتاح + تسمية).

يعرّف *أيّ* الموديلات متاحة وأيّها الافتراضي، بلا أي اعتماد على طبقة
العرض (tkinter / ui). طبقة الواجهة تربط كل مفتاح بمُصيّره الخاص
(الرسم + توليد Word/PDF) عندها — راجع ``ui/hr/paie/template_simple.py``
(``RENDERERS`` / ``get_renderer``).

يكبر لاحقاً بموديلات أخرى (détaillé، société…) تُختار من الشاشة عبر
قائمة منسدلة.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateMeta:
    key: str
    label: str


TEMPLATES = {
    "simple": TemplateMeta("simple", "Bulletin simple (CNAS)"),
}

DEFAULT_TEMPLATE_KEY = "simple"


def get_template(key=None):
    """يرجّع :class:`TemplateMeta` للمفتاح المطلوب (أو الافتراضي)."""
    return TEMPLATES.get(key or DEFAULT_TEMPLATE_KEY, TEMPLATES[DEFAULT_TEMPLATE_KEY])


def template_choices():
    """``[(key, label), …]`` لملء القائمة المنسدلة."""
    return [(m.key, m.label) for m in TEMPLATES.values()]
