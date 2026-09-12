"""Shell Metrics — كل القيم البنيوية الثابتة لِـShell في مكانٍ واحد (P2.2 §1).

**ليس Design System** — فقط الأرقام البنيوية المستخدَمة فعلياً (أحجام/
حدود/عتبات استجابة) التي كانت مبعثرة عبر ``main_window.py``/``top_bar.py``/
``workspace.py``/``work_status_bar.py``/``home.py``. القيَم نفسها لم
تتغيّر عن P0–P2.1 إلا حيث يذكر التعليق ذلك صراحةً (Explorer dynamic max
الجديد، ونافذة الحدّ الأدنى الجديدة).

الوحدات كلّها بكسل (px) ما لم يُذكَر خلاف ذلك."""

# ------------------------------------------------ نافذة الحدّ الأدنى (P2.2 §2)
#  ‏قياسٌ واقعيّ من مجموع الحدود الدنيا الفعلية لعناصر Shell (Explorer
#  الأدنى + Workspace الأدنى تقريباً، زائد هامشٌ لِـTopBar/الأشرطة) —
#  ليس رقماً تحكّمياً. البرنامج يرفض الانكماش تحته (setMinimumSize)
#  بدل الاعتماد على sizeHint التلقائي غير الموثوق.
WINDOW_MIN_WIDTH = 860
WINDOW_MIN_HEIGHT = 600

# --------------------------------------------------------------- Explorer
EXPLORER_MIN_WIDTH = 180
EXPLORER_DEFAULT_WIDTH = 220
#  ‏الحدّ الأقصى المطلق — سقفٌ صلب بصرف النظر عن عرض النافذة.
EXPLORER_ABSOLUTE_MAX_WIDTH = 460
#  ‏P2.2 §3: الحدّ الفعليّ الديناميكي = min(المطلق، عرض_النافذة × النسبة)
#  — يمنع Explorer من ابتلاع Workspace في نوافذ ضيّقة، حتى دون الوصول
#  للحدّ المطلق. Workspace لها الأولوية دائماً.
EXPLORER_MAX_RATIO = 0.30

WORKSPACE_MIN_WIDTH = 600

# ------------------------------------------------------------- Brand Zone
BRAND_MIN_WIDTH = 180
BRAND_DEFAULT_WIDTH = 220
BRAND_MAX_WIDTH = 320

# ----------------------------------------------------------- أشرطة ثابتة
TOP_BAR_HEIGHT = 52
COMMAND_BAR_HEIGHT = 40
COMMAND_ICON_SIZE = 18
WORK_TAB_HEIGHT = 34
#  ‏P2.1 §1: عرضٌ موحَّد لكلّ Work Tab (لا يتغيّر تلقائياً مع resize —
#  P2.2 §12: الثبات مقصود، لا استجابة له).
WORK_TAB_WIDTH = 180
WORK_STATUS_BAR_HEIGHT = 30

# ------------------------------------------------------------------ Home
#  ‏عرضٌ أقصى لمحتوى Home/ServiceStartView (P0.2 §2 → P2.2 §9: موحَّدٌ
#  بينهما الآن) — يمنع تمدّد المحتوى على كامل عرض Workspace الواسع.
CONTENT_MAX_WIDTH = 960

#  ‏P2.2 §7: عتبتا عدد أعمدة Home — على عرض *Workspace المتاح*، لا
#  عرض الشاشة: تحت BREAKPOINT_MEDIUM عمودٌ واحد، تحت BREAKPOINT_WIDE
#  عمودان، وإلا ثلاثة.
BREAKPOINT_MEDIUM = 560
BREAKPOINT_WIDE = 760

SERVICE_CARD_MIN_WIDTH = 180
SERVICE_CARD_MIN_HEIGHT = 110
SERVICE_CARD_ICON_SIZE = 20
SERVICE_CARD_PADDING = 10

# --------------------------------------------------------------- TopBar
#  ‏P2.1 §13 → P2.2 §10/§11: حقل بحث placeholder — يتقلّص هو أوّلاً عند
#  ضيق TopBar (بلا دفع Home/Settings/Lock خارج الشاشة).
SEARCH_MIN_WIDTH = 120
SEARCH_MAX_WIDTH = 320
