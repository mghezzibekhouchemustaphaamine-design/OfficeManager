"""محرّك إخراج وثائق hr — تجريد يسمح بالطريقتين المتّفق عليهما:

1. قالب Word / Excel (.docx / .xlsx) بتصميم المكتب → البرنامج يملأ
   الفراغات (placeholders) ويصدّر الملف النهائي.
2. صورة نموذج ممسوحة (ترويسة المكتب) → البرنامج يكتب فوقها بمواضع دقيقة
   (نفس أسلوب خدمة CD).

كل الشيء هنا حالياً هيكل فقط: الشاشات جاهزة كأرضية، وتُختار طريقة كل
وثيقة ويُكتمل محرّكها لمّا يصل موديلها. لذلك كل render() يرمي
TemplateNotReady برسالة عربية واضحة تعرضها الشاشة للمستخدم.
"""


class TemplateNotReady(Exception):
    """يُرمى لمّا تُطلب وثيقة لم يصل موديلها / لم يُكتمل محرّك إخراجها بعد."""


class DocxTemplateRenderer:
    """يملأ فراغات قالب .docx (أو ورقة .xlsx) ثم يحفظ نسخة نهائية.

    template_path: مسار القالب الذي يعطيه المكتب لاحقاً.
    field_map: {مفتاح البيانات: اسم الفراغ في القالب} — يُحدَّد مع الموديل.
    """

    def __init__(self, template_path=None, field_map=None):
        self.template_path = template_path
        self.field_map = field_map or {}

    def render(self, context, out_path):  # noqa: ARG002
        raise TemplateNotReady(
            "قالب Word لهذه الوثيقة لم يُضَف بعد.\n"
            "أرسل الموديل (ملف .docx/.xlsx) ليُربط بهذه الشاشة."
        )


class ImageOverlayRenderer:
    """يكتب البيانات فوق صورة نموذج ممسوحة بمواضع بالبكسل (أسلوب CD).

    background_path: صورة ترويسة المكتب.
    field_layout: {مفتاح البيانات: (x_mm, y_mm, أقصى عدد أحرف)} — يُحدَّد
    مع الموديل بقياس الورقة الحقيقي.
    """

    def __init__(self, background_path=None, field_layout=None):
        self.background_path = background_path
        self.field_layout = field_layout or {}

    def render(self, context, out_path):  # noqa: ARG002
        raise TemplateNotReady(
            "صورة النموذج لهذه الوثيقة لم تُضَف بعد.\n"
            "أرسل صورة الترويسة الممسوحة لتُربط بهذه الشاشة."
        )
