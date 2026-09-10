"""مواصفة تخطيط كشف الراتب — **مليمترات ورقة A4 خالصة**.

بلا Qt، بلا Tk، بلا ReportLab، وبلا أيّ مفهوم زوم أو بكسل. هذا هو المصدر
**الوحيد** لهندسة الوثيقة: الشاشة (``ui2/hr/paie/bulletin_template.py``)
والمُصيِّر (``ui/hr/paie/template_simple.py``) يستهلكانه معاً، فتكون
SCREEN == PDF هندسياً لا بالتقريب البصريّ.

القاعدة الذهبية (Phase E.1 §2): **هندسة الوثيقة لا تعتمد الزوم أبداً**.
الزوم تحويلٌ خارجيّ فقط: ``document_mm → screen_px`` على الشاشة. أيّ
ثابتٍ هنا هو نفسه على 45٪ و100٪ و200٪ و260٪.
"""

# ============================ الصفحة ============================
PAGE_W_MM = 210.0
PAGE_H_MM = 297.0
MARGIN_L_MM = 14.0
MARGIN_R_MM = 14.0
MARGIN_T_MM = 12.0
CONTENT_W_MM = PAGE_W_MM - MARGIN_L_MM - MARGIN_R_MM          # 182.0
#  كلّ الكتل الرئيسية تبدأ من هذا الأصل (§10): الأصل النصّيّ للمحتوى =
#  الحافة اليسرى للورقة + الهامش الأيسر. «x مليمتر» في هذا الملف = مسافةٌ
#  من هذا الأصل.
MAIN_LEFT_MM = 0.0

# ===================== الترويسة (خطوط أساس من أعلى الورقة) =====================
RAISON_BASELINE_MM = 10.5
ADRESSE_BASELINE_MM = 18.5
ADHERENT_BASELINE_MM = 26.5
ADHERENT_LABEL_X_MM = 0.0            # «N° ADHÉRENT» على الأصل تماماً
ADHERENT_VALUE_X_MM = 24.0           # الرقم بعد التسمية (لا يزيح أصل الكتلة، §10)

# ========================= شريط العنوان الأسود =========================
BAND_TITLE_Y_MM = 40.0
BAND_TITLE_H_MM = 8.0
BAND_BASELINE_MM = BAND_TITLE_Y_MM + BAND_TITLE_H_MM / 2.0 + 1.6
BAND_LABEL_X_MM = 3.0                # «BULLETIN DE PAIE»
MOIS_X_MM = CONTENT_W_MM * 0.52      # الشهر — موضعه على الشريط
ANNEE_X_MM = CONTENT_W_MM * 0.52 + 35.0   # السنة — منفصلةٌ عن الشهر (§7)

# ====================== صندوق هوية العامل ======================
IDENT_Y_MM = 50.0
IDENT_ROW0_MM = 9.0                  # أوّل خطّ أساس تحت أعلى الصندوق
#  خطوة الصفوف: كانت ``theme.SPACE["sm"] px / scale`` (تعتمد الزوم — خطأ
#  معماريّ أُزيل في §3). قيمتها المُجمَّدة = 9 + (6px ÷ scale@100٪ = 1.75mm).
IDENT_ROW_STEP_MM = 10.75
IDENT_H_MM = 59.0                    # 52 (القديم) + 4×(STEP − 9) = 52 + 7
IDENT_LABEL_L_X_MM = 4.0
IDENT_VALUE_L_X_MM = 38.0
IDENT_LABEL_R_X_MM = 93.0
IDENT_VALUE_R_X_MM = 124.0
IDENT_LIEU_X_MM = 64.0               # حقل مكان الميلاد (نصف السطر الأيمن)
_DATE_FIELD_W_MM = 20.0
_DATE_BTN_W_MM = 6.0                 # زرّ التقويم على الشاشة — يُحجَز مكانه
#                                     في PDF أيضاً حتى تتطابق مواضع «à»/المكان.

#  (key, label|None, label_x, value_x, value_w, row_index, maxlen, kind)
#  label=None ⇒ خانةٌ تتبع سابقتها (مكان الميلاد).
IDENT_FIELDS = [
    ("nom",                 "NOM",               IDENT_LABEL_L_X_MM, IDENT_VALUE_L_X_MM, 49.0, 0, 24, "upper_alpha"),
    ("prenom",              "PRÉNOM",            IDENT_LABEL_R_X_MM, IDENT_VALUE_R_X_MM, 55.0, 0, 24, "titlecase"),
    ("date_naissance",      "DATE DE NAISSANCE", IDENT_LABEL_L_X_MM, IDENT_VALUE_L_X_MM, 20.0, 1, 10, "date_masked"),
    ("lieu_naissance",      None,                None,               IDENT_LIEU_X_MM,    59.0, 1, 40, "upper_alpha"),
    ("num_ss",              "N° SS",             IDENT_LABEL_L_X_MM, IDENT_VALUE_L_X_MM, 55.0, 2, 13, "num_ss"),
    ("situation_familiale", "SIT. FAMILIALE",    IDENT_LABEL_R_X_MM, IDENT_VALUE_R_X_MM, 14.0, 2, 1,  "famille"),
    ("date_embauche",       "DATE D'ENTRÉE",     IDENT_LABEL_L_X_MM, IDENT_VALUE_L_X_MM, 20.0, 3, 10, "date_masked"),
    ("matricule",           "MATRICULE",         IDENT_LABEL_R_X_MM, IDENT_VALUE_R_X_MM, 49.0, 3, 20, "text"),
    ("fonction",            "FONCTION",          IDENT_LABEL_L_X_MM, IDENT_VALUE_L_X_MM, 84.0, 4, 40, "text"),
]


def ident_row_y(r):
    """خطّ أساس الصفّ ``r`` (0..4) في صندوق الهوية — مليمتر من أعلى الورقة."""
    return IDENT_Y_MM + IDENT_ROW0_MM + r * IDENT_ROW_STEP_MM


def row1_layout():
    """‏``(a_x, lieu_x)`` بالمليمتر لسطر تاريخ الميلاد: نهاية حقل التاريخ
    (+ زرّ التقويم المحجوز) ثمّ «à» ثمّ حقل المكان — ثابتٌ بلا زوم."""
    date_w = _DATE_FIELD_W_MM + _DATE_BTN_W_MM
    a_x = IDENT_VALUE_L_X_MM + date_w + 3.0
    lieu_x = a_x + 6.0
    return a_x, lieu_x


# ======================== جدول الرُبريكات ========================
TABLE_HEAD_Y_MM = 112.0             # 105 (القديم) + 7 (الإزاحة صارت ثابتة)
ROW_H_MM = 6.2
TABLE_HEAD_H_MM = ROW_H_MM + 1.0
BODY_TOP_MM = TABLE_HEAD_Y_MM + ROW_H_MM + 1.0      # 119.2
CELL_PAD_MM = 2.5                   # حشو النصّ داخل الخليّة
MIN_BODY_SLOTS = 5                  # أدنى أسطر مرسومة تحت IRG (فراغ ثابت)

#  (key, f0, f1, align, title) — الحدود نسبةً إلى عرض المحتوى (0..1).
COLS = [
    ("code",    0.000, 0.077, "c", "CODE"),
    ("libelle", 0.077, 0.450, "l", "LIBELLÉ"),
    ("nbase",   0.450, 0.615, "r", "N/BASE"),
    ("taux",    0.615, 0.755, "r", "TAUX"),
    ("gain",    0.755, 0.878, "r", "GAIN"),
    ("retenue", 0.878, 1.000, "r", "RETENUE"),
]


def col_bounds(key):
    """‏``(x0_mm, x1_mm, align)`` لعمودٍ — مليمتر من أصل المحتوى."""
    for k, f0, f1, al, _t in COLS:
        if k == key:
            return f0 * CONTENT_W_MM, f1 * CONTENT_W_MM, al
    raise KeyError(key)


def cell_mm(key, row_idx):
    """‏``(x_mm, y_mm, w_mm)`` لخانة إدخالٍ في الجدول (مع الحشو)."""
    x0, x1, _al = col_bounds(key)
    return (x0 + CELL_PAD_MM,
            body_row_y(row_idx) + 0.7,
            (x1 - x0) - 2 * CELL_PAD_MM)


def body_row_y(i):
    """أعلى الصفّ ``i`` في جسم الجدول — مليمتر من أعلى الورقة."""
    return BODY_TOP_MM + i * ROW_H_MM


def n_body_drawn(n_real, n_zone_c):
    """عدد أسطر الشبكة المرسومة: الفعليّة + حشوٌ فارغ حتى ``MIN_BODY_SLOTS``
    سطراً تحت IRG (§11). الفرق مساحة شبكة، لا صفوف."""
    return n_real + max(0, MIN_BODY_SLOTS - n_zone_c)


def total_y_mm(n_drawn):
    return BODY_TOP_MM + n_drawn * ROW_H_MM


def net_y_mm(n_drawn):
    return total_y_mm(n_drawn) + ROW_H_MM


def table_bottom_mm(n_drawn):
    return net_y_mm(n_drawn) + ROW_H_MM


# ============================ التيبوغرافيا ============================
#  فئة نصّ الوثيقة → (ارتفاع الخط بالمليمتر، Bold). مصدرٌ واحد: Qt يحوّله
#  إلى ``QFont`` (نقطة = mm × scale × K)، وReportLab يحوّله إلى
#  Helvetica[-Bold] + نقطة (mm × PDF_PT_PER_MM). لا قيَم خطّ متناثرة (§9).
FONT_FAMILY = "Helvetica"

TEXT = {
    "header_company": (5.0, True),
    "header_address": (3.4, True),
    "header_title":   (5.0, True),
    "block_labels":   (3.2, True),
    "block_values":   (3.2, False),
    "table_header":   (3.0, True),
    "table_body":     (3.2, False),
    "computed_value": (3.2, False),
    "total_row":      (3.4, True),
    "net_row":        (4.4, True),
}

#  تحويل «ارتفاع الخط بالمليمتر» → نقطة PDF. مُعايَر ليُنتج نفس مقاسات
#  المُصيِّر السابقة (body 8pt ≈ 3.2mm · title/net 11-13pt ≈ 4.4-5.0mm).
PDF_PT_PER_MM = 2.55


def pdf_font(token):
    """‏``(font_name, size_pt)`` لـ ReportLab لفئة نصّ الوثيقة."""
    mm_h, bold = TEXT[token]
    name = FONT_FAMILY + "-Bold" if bold else FONT_FAMILY
    return name, mm_h * PDF_PT_PER_MM


#  ألوان الوثيقة (مشتركة).
INK = "#202124"
COMPUTED = "#1a56b0"
BAND_BLACK = "#111111"
GRID_LINE = "#c8c8c8"
