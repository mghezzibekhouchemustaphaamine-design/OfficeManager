"""سجلّ موديلات كشف الراتب.

يكبر لاحقاً بموديلات أخرى (détaillé، société…) وتُختار من الشاشة عبر
قائمة منسدلة. حالياً موديل واحد افتراضي.
"""
from ui.hr.paie.template_simple import SimpleBulletinTemplate

TEMPLATES = {
    SimpleBulletinTemplate.KEY: SimpleBulletinTemplate,
}
DEFAULT_TEMPLATE_KEY = SimpleBulletinTemplate.KEY


def get_template(key=None):
    return TEMPLATES.get(key or DEFAULT_TEMPLATE_KEY, SimpleBulletinTemplate)


def template_choices():
    """[(key, label), …] لملء القائمة المنسدلة لاحقاً."""
    return [(k, t.LABEL) for k, t in TEMPLATES.items()]
