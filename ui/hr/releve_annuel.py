"""كشف الراتب السنوي / Relevé annuel des émoluments — شاشة مستقلّة.

مؤجّلة (آخر شاشة): يبقى مفتوحاً للنقاش هل تكون مستقلّة بالكامل مثل باقي
الشاشات، أم تتولّد فقط من كشوف الراتب الشهرية المخزّنة (متعلّقة بها).
الأرضية موجودة الآن حتى تكون جاهزة عند حسم القرار.
"""
from ui.hr.base import HRDocScreen


class ReleveAnnuelScreen(HRDocScreen):
    SCREEN_KEY = "hr_releve_annuel"
    SCREEN_TITLE = "كشف راتب سنوي"
    DOC_LABEL = "Relevé annuel des émoluments"
    OUTPUT_DIRNAME = "Relevés annuels"
