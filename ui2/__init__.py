"""مكتبة مكوّنات واجهة PySide6 قابلة لإعادة الاستعمال — لا شاشات عمل.

قواعد الحزمة:
  - لا تستورد أي شيء من ``ui/`` القديمة (Tkinter).
  - لا SQL ولا منطق حساب — عرض وتفاعل فقط.
  - اتجاه التخطيط (RTL) والخط والألوان تُضبط مركزياً في ``ui2.theme``
    عبر ``apply_theme(app)`` — لا مكوّن يستدعي ``setLayoutDirection``.

الوحدات: theme · table · form · dialog · toolbar · tabs · shortcuts · window.
"""
