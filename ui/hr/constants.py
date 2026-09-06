"""ثوابت مشتركة لكل شاشات خدمات الموارد البشرية / الأجور.

ملف واحد بلا اعتماد على باقي ملفات hr/ (تفادي الاستيراد الدائري) — كل
ملف بالحزمة يستورد منه ما يحتاجه فقط. نفس فلسفة ui/cd/constants.py.
"""

# --- ورقة A4 ---
# A4 = 210 مم × 297 مم. المعاينة على الشاشة تحافظ على هذي النسبة بالضبط،
# والتكبير (زوم) يضرب العرض الأساسي فقط. القيَم بالمليمتر تُستعمل لاحقاً
# لتحويل مواضع الحقول (لمّا تصل موديلات الوثائق) لبكسل على أي تكبير.
A4_W_MM = 210
A4_H_MM = 297
A4_RATIO = A4_H_MM / A4_W_MM  # ارتفاع / عرض ≈ 1.414

PREVIEW_BASE_W = 640   # عرض الورقة بالبكسل عند زوم 100%
PREVIEW_MARGIN = 18    # أقل مسافة بين الورقة وحواف منطقة المعاينة
# هامش الطباعة الافتراضي داخل الورقة (مم) — يُرسم كدليل خفيف في المعاينة،
# ويصير لاحقاً حدود منطقة النص عند بناء المستند النهائي.
PAGE_MARGIN_MM = 20

# --- التكبير (زوم) ---
ZOOM_MIN = 40
ZOOM_MAX = 220
ZOOM_STEP = 20
ZOOM_DEFAULT = 100

# --- ملف إعدادات المكتب المشترك بين شاشات hr (تُتذكَّر بين الجلسات) ---
# بيانات صاحب العمل (الشركة) غالباً تتكرّر لنفس الزبون، فنحفظ آخر إدخال
# كمسودة يدوية قابلة للاستدعاء — بجذر المشروع جنب باقي ملفات الحالة.
# هذا الملف بـui/hr/constants.py (3 مستويات تحت الجذر) → 3 dirname.
import os as _os
_APP_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
HR_SETTINGS_PATH = _os.path.join(_APP_ROOT, "hr_settings.json")

# --- حقول كتلة "صاحب العمل" (الشركة) — مشتركة بين الوثائق الأربع ---
# (key, نص التسمية على الشاشة, نوع الودجت, عرض تقريبي بالأحرف)
# نوع الودجت: "text" خانة نصّية عادية · "date" خانة تاريخ مقنّعة
EMPLOYER_FIELDS = [
    ("raison_sociale",   "التسمية / Raison sociale",     "text", 42),
    ("forme_juridique",  "الشكل القانوني / Forme jur.",  "text", 18),
    ("adresse",          "العنوان / Adresse",            "text", 42),
    ("rc",               "السجل التجاري / N° RC",        "text", 24),
    ("nif",              "NIF",                          "text", 20),
    ("nis",              "NIS",                          "text", 20),
    ("art_imposition",   "رقم المادة / Art. imposition", "text", 20),
    ("cnas_employeur",   "رقم الانتساب CNAS",            "text", 20),
    ("gerant_nom",       "المسيّر / Gérant",             "text", 30),
    ("gerant_qualite",   "صفة المسيّر / Qualité",        "text", 20),
    ("tel",              "الهاتف / Tél",                 "text", 20),
]

# --- حقول كتلة "الأجير" — مشتركة بين الوثائق الأربع ---
EMPLOYEE_FIELDS = [
    ("civilite",             "الصفة / Civilité (M./Mme)",   "text", 10),
    ("nom",                  "اللقب / Nom",                 "text", 26),
    ("prenom",               "الاسم / Prénom",              "text", 26),
    ("date_naissance",       "تاريخ الميلاد / Né(e) le",    "date", 12),
    ("lieu_naissance",       "مكان الميلاد / à",            "text", 26),
    ("fonction",             "الوظيفة / Fonction",          "text", 26),
    ("date_embauche",        "تاريخ التوظيف / Embauché le",  "date", 12),
    ("type_contrat",         "نوع العقد / Contrat (CDI…)",  "text", 12),
    ("num_ss",               "الضمان الاجتماعي / N° SS",     "text", 20),
    ("matricule",            "الرقم / Matricule",           "text", 12),
    ("situation_familiale",  "الحالة العائلية / Sit. fam.", "text", 12),
    ("salaire_base",         "الأجر القاعدي / Salaire base", "text", 14),
]

# المفاتيح التي يُبنى منها عنوان الشاشة الكبير (اسم الأجير الحقيقي، لا
# عنوان عام) — راجع HRDocScreen._refresh_header.
EMPLOYEE_NAME_KEYS = ("prenom", "nom")


# --- كشف الراتب (Bulletin de paie) ---
MOIS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

# أكواد الرُّبريكات الافتراضية (كما في نموذج كشف CNAS المرجعي) — قابلة
# للتعديل من الشاشة، ليست بيانات ثابتة.
PAIE_DEFAULT_CODES = {
    "salaire_base": "030",
    "prime":        "222",
    "cnas":         "510",
    "irg":          "660",
    "panier":       "522",
    "transport":    "533",
}

# نسبة اشتراك الضمان الاجتماعي (حصة الأجير)
TAUX_CNAS = 0.09

# عدد أسطر المنح / الاقتطاعات الحرّة المتاحة في شاشة الكشف
PAIE_MAX_PRIMES = 6
PAIE_MAX_RETENUES = 4
