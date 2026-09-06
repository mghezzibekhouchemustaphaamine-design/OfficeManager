"""شهادة عمل / Attestation de travail — شاشة مستقلّة.

أرضية فقط: النموذج والمعاينة جاهزان؛ تخطيط الشهادة نفسها ومحرّك إخراجها
يُضافان عند وصول الموديل.
"""
from ui.hr.base import HRDocScreen


class AttestationTravailScreen(HRDocScreen):
    SCREEN_KEY = "hr_attestation_travail"
    SCREEN_TITLE = "شهادة عمل"
    DOC_LABEL = "Attestation de travail"
    OUTPUT_DIRNAME = "Attestations de travail"
