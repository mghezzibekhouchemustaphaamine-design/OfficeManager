"""حزمة خدمات الموارد البشرية / الأجور في OfficeManager.

أربع شاشات مستقلّة، كل واحدة خدمة قائمة بذاتها (زي خدمة CD تماماً):

- شهادة عمل            (attestation_travail.AttestationTravailScreen)
- شهادة عطلة            (titre_conge.TitreCongeScreen)
- كشف الراتب الشهري     (bulletin_paie.BulletinPaieScreen)
- كشف الراتب السنوي     (releve_annuel.ReleveAnnuelScreen)  ← مؤجّل، أرضية فقط

كلها ترث الأرضية المشتركة من hr/base.py (HRDocScreen): نموذج إدخال على
اليسار + معاينة ورقة A4 حيّة على اليمين + شريط أدوات (توليد Word / PDF /
السجلّ / مسح). تخطيط المستند نفسه ومحرّك الإخراج (قالب Word/Excel أو صورة
نموذج ممسوحة) يُضافان لاحقاً لمّا تصل موديلات كل وثيقة — راجع hr/render.py.
"""
