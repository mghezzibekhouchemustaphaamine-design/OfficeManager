"""شهادة عطلة / Titre de congé — شاشة مستقلّة.

أرضية فقط: النموذج والمعاينة جاهزان؛ تخطيط الوثيقة ومحرّك إخراجها
يُضافان عند وصول الموديل.
"""
from ui.hr.base import HRDocScreen


class TitreCongeScreen(HRDocScreen):
    SCREEN_KEY = "hr_titre_conge"
    SCREEN_TITLE = "شهادة عطلة"
    DOC_LABEL = "Titre de congé"
    OUTPUT_DIRNAME = "Titres de congé"
