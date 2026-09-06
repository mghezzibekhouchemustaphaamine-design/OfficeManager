"""موديلات كشف الراتب (Bulletin de paie) — طبقة العرض والتفاعل فقط.

كل موديل هنا = تخطيط ثابت + معاينة على اللوحة + إخراج Word/PDF. حالياً
موديل واحد:
  - «Bulletin simple (CNAS)» (``template_simple.py``) — على غرار كشف
    CNAS القصير (جدول CODE/LIBELLÉ/N-BASE/TAUX/GAIN/RETENUE، سطر TOTAL،
    خانة NET À PAYER).

طبقة الحساب انتقلت خارج الواجهة إلى ``programme/payroll/`` (لا تعتمد على
tkinter):
  - ``programme.payroll.calc``     — سلسلة الحساب (Decimal).
  - ``programme.payroll.irg``      — دالة IRG المرجعية.
  - ``programme.payroll.registry`` — سجلّ الموديلات (مفتاح + تسمية).

ربط المفتاح بصنف المُصيّر: ``template_simple.RENDERERS`` / ``get_renderer``.

لا يُنقل أي محتوى من نماذج المكتب المرجعية — القياسات والترتيب فقط.
"""
