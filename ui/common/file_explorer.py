"""
شريط شجرة الملفات (يسار الشاشة): يعرض ملفات/مجلدات "الشغل" الحقيقي
(مجلد travail بسطح المكتب — حالياً travail/CD، ولاحقاً أي خدمة ثانية
بنفس الاصطلاح) بشكل شجرة قابلة للتصفح، زي مستكشف ملفات ويندوز — بلا أي
وصول لباقي جهاز المستخدم (محصور بمجلد travail فقط، بطلب صريح: أبسط وأأمن).

ودجت مستقل تماماً (FileExplorerPanel) قابل للتضمين بأي تبويب — حالياً
مفعّل بـCD بس (بطلب صريح)، لكن جاهز يُستعمل بأي شاشة ثانية لاحقاً بلا أي
تعديل عليه، بس استدعاءه من هناك.

العمليات المتوفرة: تصفّح (تحميل كسول لكل مجلد لما يُفتح أول مرة — أسرع من
مسح الشجرة كاملة مقدّماً)، فتح ملف بالبرنامج الافتراضي، فتح مجلد بمستكشف
ويندوز الحقيقي، إنشاء مجلد جديد، حذف (بتأكيد حقيقي دائماً — حذف ملف فعلي
من القرص خطر مختلف تماماً عن تنبيهات بيانات CD المؤقتة الموقوفة حالياً،
فما نربطه بنفس مفتاح CONFIRM_DIALOGS_ENABLED)، إعادة تسمية، بحث سريع
(بالاسم، بكل الشجرة)، ونقل ملف/مجلد بالسحب والإفلات (Drag & Drop) — منفَّذ
يدوياً بأحداث الفأرة (Tk القياسي ما فيه دعم سحب/إفلات جاهز لملفات حقيقية
بين صفوف Treeview، ولا حبينا نضيف مكتبة خارجية إضافية لهذا وحده).

يتذكّر آخر مكان كنت واقف فيه بين الجلسات عبر ملف تفضيلات محلي بسيط
(file_explorer_prefs.json) — نفس اصطلاح ملفات التفضيلات الموجودة أصلاً
بالمشروع (cd_settings.json، cd_ui_prefs.json...)، ما يحتاج قاعدة بيانات
حقيقية لمجرد هالتفصيل.
"""
import json
import os
import shutil
import tkinter as tk
from datetime import datetime
from tkinter import ttk, simpledialog

from ui.common import alerts

from programme.utils import open_path
from programme.paths import get_travail_root

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# جذر الشريط: كل travail/ (بكل الخدمات — CD حالياً، وأي خدمة ثانية لاحقاً
# تتبع نفس الاصطلاح) — مو مجلد CD لحاله، حتى الشريط يفيد أي تبويب يُضاف له لاحقاً.
EXPLORER_ROOT = get_travail_root()
PREFS_PATH = os.path.join(_APP_ROOT, "file_explorer_prefs.json")

_INVALID_NAME_CHARS = '\\/:*?"<>|'

# منطق ويندوز لإعادة التسمية: نقرة ثانية على عنصر محدَّد أصلاً بعد هالمدة
# (أطول من حد Double-1 القياسي بويندوز، ~500ms) تُحسب "نقرة تعديل" لا
# جزء من دبل كليك — راجع _maybe_schedule_rename/_on_double_click.
_RENAME_CLICK_DELAY_MS = 550

_RECENT_PREFS_KEY = "recent"
_RECENT_MAX = 8


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass  # حفظ تفضيل ثانوي — فشل الكتابة ما يوقف الشريط


class FileExplorerPanel(ttk.Frame):
    def __init__(
        self, parent, root_dir=None, width=220, is_path_active=None, on_open_file=None,
        on_toggle_lock=None,
    ):
        """is_path_active (اختياري): دالة (مسار) -> True/False تحدّد
        "شغل جاري" (True) مقابل "شغل منتهي" (False) — تُستخدم لحماية
        إضافية (تأكيد أوضح) قبل نقل/حذف/إعادة تسمية ملف منتهي، بلا أي
        منع كامل. بلا تمرير (استخدام عام مستقبلي بشاشة ثانية)، كل شي
        يُعتبر "جارٍ" دائماً (بلا أي حماية إضافية — نفس السلوك القديم
        بالضبط)، حتى ما نفرض هذا المفهوم على خدمة ما تحتاجه.

        on_open_file (اختياري): دالة (مسار) -> True/False تُستدعى قبل
        الفتح الافتراضي بالنظام (نقرة مزدوجة أو "📂 فتح") — لو رجعت
        True (تكفّلت هي بفتحه، زي تحميله باستمارة CD للقراءة فقط)، ما
        نفتحه بالنظام كمان؛ لو رجعت False أو ما انعطت أصلاً، نفتحه
        عادي بالنظام (نفس السلوك القديم بالضبط) — راجع _open_file.

        on_toggle_lock (اختياري): دالة (مسار) -> بلا رجعة، تُستدعى عند
        دبل كليك على أيقونة 🔒 الظاهرة على ملف "شغل منتهي" **تحديداً**
        (لا أي مكان ثاني بنفس الصف — راجع _on_double_click). الودجت
        نفسه ما يعرف شي عن معنى "فتح/فك القفل" — بس يبلّغ الطلب؛ CD
        تمرّر دالة تفتح/تفك التبويب المرتبط بهذا الملف."""
        super().__init__(parent, padding=(4, 4))
        self.root_dir = root_dir or EXPLORER_ROOT
        os.makedirs(self.root_dir, exist_ok=True)
        self._width = width
        self.configure(width=width)
        self.pack_propagate(False)  # يبقى بعرضه المحدَّد بغض النظر عن محتواه
        self._is_path_active = is_path_active or (lambda _path: True)
        self._on_open_file = on_open_file
        self._on_toggle_lock = on_toggle_lock

        self._paths = {}  # tree item id -> مسار حقيقي بالقرص
        self._drag_iid = None
        self._drag_started = False
        self._drop_target_iid = None
        self._drag_ghost = None  # نافذة عائمة صغيرة تتبع الفأرة أثناء السحب
        self._drop_line = None  # خط رفيع بصري لما الهدف "بين ملفين" (فوق ملف لا مجلد)

        # إعادة تسمية مباشرة بالسطر (منطق ويندوز: نقرة تحدّد، نقرة ثانية
        # على نفس العنصر المحدَّد بعد فترة كافية تدخل تعديل) — راجع
        # _maybe_schedule_rename/_begin_inline_rename.
        self._rename_after_id = None
        self._last_clicked_iid = None
        self._editing_iid = None
        self._rename_entry = None
        self._rename_entry_var = None

        # تظليل الصف تحت الفأرة (hover) — يتبع <Motion> الموجودة أصلاً للتلميح.
        self._hover_iid = None
        self._hover_original_tags = ()

        # تعارض أسماء بالسحب: أول محاولة على تعارض معيّن = ومضة بلا نافذة؛
        # نفس المحاولة بالضبط مرة ثانية متتالية = تنبيه صريح.
        self._last_conflict = None

        self._recent_paths = []  # فهرس صف بقائمة "الأخيرة" -> مسار حقيقي

        self._lock_icon_locked = None
        self._lock_icon_unlocked = None
        self._build_lock_icons()

        self._build_ui()
        self._populate_root()
        self._restore_last_location()
        self._refresh_recent_list()

    # ---------- بناء الواجهة ----------
    def _build_ui(self):
        # شريط الأزرار العلوي انحذف كليّاً (بطلب صريح) — كل عملياته
        # صارت بقائمة كليك يمين (راجع _show_context_menu)، أوضح وأسرع
        # من دوران الفأرة لزر صغير، وتوفّر مساحة رأسية للشريط الضيّق.
        recent_frame = ttk.LabelFrame(self, text="🕘 الأخيرة")
        recent_frame.pack(fill="x", pady=(0, 4))
        self.recent_listbox = tk.Listbox(
            recent_frame, height=4, activestyle="none", exportselection=False,
            font=("Segoe UI", 9), relief="flat", highlightthickness=0,
        )
        self.recent_listbox.pack(fill="x")
        self.recent_listbox.bind("<<ListboxSelect>>", self._on_recent_select)

        search_bar = ttk.Frame(self)
        search_bar.pack(fill="x", pady=(0, 4))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._on_search_change())

        tree_holder = ttk.Frame(self)
        tree_holder.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_holder, show="tree", selectmode="browse")
        vsb = ttk.Scrollbar(tree_holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("drop_target", background="#cde8ff")
        # وضوح بصري للتعشيش (بدل خطوط اتصال — راجع _node_for_path/_depth_of):
        # مسافة بادئة أوضح + تظليل خفيف متدرّج حسب العمق، يبيّن وين
        # بالضبط مكان الملف بلمحة بلا تدقيق كثير. نمط خاص بهذا الشريط
        # بس (اسم مختلف عن "Treeview" العام) حتى ما يأثر على أي شجرة
        # ثانية بالبرنامج (زي جدول نافذة السجل).
        style = ttk.Style(self)
        style.configure("FileExplorer.Treeview", indent=28)
        self.tree.configure(style="FileExplorer.Treeview")
        for level, shade in enumerate(("#ffffff", "#f5f7fa", "#eaeef3", "#dde3ea", "#cfd7e0")):
            self.tree.tag_configure(f"depth{level}", background=shade)

        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release)
        self.tree.bind("<Button-3>", self._show_context_menu)
        # اختصارات لوحة مفاتيح (بدل الاعتماد على أزرار الشريط بالفأرة بس) —
        # مربوطة على عناصر الشريط نفسه (tree/بحث)، لا bind_all، حتى ما
        # تتصادم مع اختصارات شاشة CD نفسها (الودجت مستقل تماماً، راجع شرح الملف).
        self.tree.bind("<Delete>", lambda _e: self._delete_selected())
        self.tree.bind("<F2>", lambda _e: self._rename_selected())
        self.tree.bind("<Return>", lambda _e: self._open_focused())
        self.tree.bind("<Control-f>", self._focus_search)
        self.tree.bind("<Control-F>", self._focus_search)
        self.bind("<Control-f>", self._focus_search)
        self.bind("<Control-F>", self._focus_search)
        # تلميح (Tooltip) يعرض الاسم كامل عند تمرير الفأرة — الشريط عرضه
        # ثابت والشجرة تقصّ أي اسم أطول منه بلا أي طريقة تشوف الباقي،
        # بطلب صريح (لاحظ المستخدم إنه ما يقدر يقرأ أسماء طويلة كاملة).
        self._tooltip = None
        self._tooltip_after_id = None
        self._tooltip_row = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)

        self.path_label = ttk.Label(
            self, text="", anchor="w", wraplength=self._width if isinstance(self._width, int) else 200,
            font=("Segoe UI", 8), foreground="#555",
        )
        self.path_label.pack(fill="x", pady=(4, 0))

    def _focus_search(self, _event=None):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
        return "break"

    # ---------- تلميح الاسم الكامل عند التمرير + تظليل الصف تحت الفأرة ----------
    def _on_tree_motion(self, event):
        if self._drag_iid and self._drag_started:
            return  # أثناء السحب الفعلي: مؤشر السحب والنافذة المتتبِّعة كافيين
        row = self.tree.identify_row(event.y)
        self._update_hover_highlight(row)
        if row != self._tooltip_row:
            self._hide_tooltip()
            self._tooltip_row = row
            if row:
                # تأخير بسيط قبل الظهور (بدل فوري) — يمنع وميض مزعج لو
                # الفأرة بس عابرة، مو واقفة فعلاً فوق العنصر.
                self._tooltip_after_id = self.after(500, lambda: self._show_tooltip(row, event.x_root, event.y_root))

    def _on_tree_leave(self, _event):
        self._hide_tooltip()
        self._update_hover_highlight(None)

    def _update_hover_highlight(self, row):
        if row == self._hover_iid:
            return
        if self._hover_iid is not None:
            try:
                self.tree.item(self._hover_iid, tags=self._hover_original_tags)
            except tk.TclError:
                pass  # العنصر ممكن يكون انمسح (refresh) وسط التحويم
            self._hover_iid = None
        if row:
            self._hover_original_tags = self.tree.item(row, "tags")
            self.tree.tag_configure("_hover", background="#e8f0fe")
            self.tree.item(row, tags=("_hover",))
            self._hover_iid = row

    def _show_tooltip(self, row, x_root, y_root):
        path = self._paths.get(row)
        if not path:
            return
        name = os.path.basename(path)
        self._tooltip = tk.Toplevel(self)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.wm_geometry(f"+{x_root + 12}+{y_root + 12}")
        ttk.Label(
            self._tooltip, text=name, background="#ffffe0", relief="solid", borderwidth=1,
            font=("Segoe UI", 9), padding=(4, 2),
        ).pack()

    def _hide_tooltip(self):
        if self._tooltip_after_id is not None:
            self.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._tooltip_row = None

    # ---------- معاينة سريعة (صور بس حالياً — راجع _preview_selected) ----------
    def _preview_selected(self):
        iid = self.tree.focus()
        path = self._paths.get(iid)
        if not path or os.path.isdir(path):
            alerts.info("معاينة", "اختر ملفاً أولاً.")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in _IMAGE_EXTS:
            # PDF وWord ما فيهم معاينة حقيقية هون عمداً — تحتاج مكتبة
            # خارجية إضافية (زي PyMuPDF) استغنى عنها المشروع بالكامل
            # سابقاً (راجع requirements.txt)، فما نرجّعها لميزة وحدها.
            alerts.info(
                "لا معاينة متاحة",
                "معاينة سريعة متاحة للصور بس حالياً.\nاضغط 'فتح' (📂) لعرض هذا الملف ببرنامجه الافتراضي.",
            )
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((600, 600))
            photo = ImageTk.PhotoImage(img)
        except Exception as exc:  # noqa: BLE001
            alerts.error("خطأ", f"تعذرت معاينة الصورة:\n{exc}")
            return
        win = tk.Toplevel(self)
        win.title(os.path.basename(path))
        label = ttk.Label(win, image=photo)
        label.image = photo  # مرجع حي حتى ما تُمسح الصورة بجمع القمامة
        label.pack()

    # ---------- تحميل الشجرة (كسول: كل مجلد يُفحص فعلياً أول ما يُفتح) ----------
    def _list_dir_sorted(self, dir_path):
        try:
            entries = os.listdir(dir_path)
        except OSError:
            return []
        full = [os.path.join(dir_path, e) for e in entries]
        dirs = sorted((p for p in full if os.path.isdir(p)), key=lambda p: os.path.basename(p).lower())
        files = sorted((p for p in full if not os.path.isdir(p)), key=lambda p: os.path.basename(p).lower())
        return dirs + files

    def _depth_of(self, iid):
        """عمق عنصر بالشجرة (0 لعناصر الجذر مباشرة) — يُحسب من سلسلة
        الآباء الحقيقية بـTk نفسها، بلا حاجة لتخزين إضافي."""
        depth = 0
        while iid:
            iid = self.tree.parent(iid)
            depth += 1
        return depth

    def _build_lock_icons(self):
        """يبني أيقونتي 🔒/🔓 كـPhotoImage حقيقية (عنصر Treeview
        image=، لا نص) — مرة وحدة بمنشئ الودجت، تُعاد استخدامها لكل
        صف. رسم مباشر بـPillow (متوفرة أصلاً بالمشروع لرسم خلفية CD —
        راجع ui/cd/document.py) بدل الاعتماد على رمز إيموجي كنص، حتى
        نقدر نميّز نقرة على الأيقونة تحديداً عبر identify_element (راجع
        _on_double_click) — نص عادي ما يعطي هالتمييز. لو Pillow غير
        متوفرة لأي سبب، نرجع لنص "🔒" كنص عادي (راجع _node_for_path) —
        تدهور نظيف بلا كسر الشريط بالكامل."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            return
        size = 14

        def draw(locked):
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            color = "#c0392b" if locked else "#7f8c8d"
            d.rounded_rectangle((2, 6, size - 3, size - 1), radius=2, fill=color)
            if locked:
                d.arc((3, 1, size - 4, 9), start=180, end=360, fill=color, width=2)
            else:
                d.arc((5, 0, size - 1, 8), start=190, end=340, fill=color, width=2)
            return ImageTk.PhotoImage(img)

        self._lock_icon_locked = draw(True)
        self._lock_icon_unlocked = draw(False)

    def _node_for_path(self, parent_iid, path):
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        icon = "📁 " if is_dir else "📄 "
        depth = self._depth_of(parent_iid) if parent_iid else 0
        # تظليل خفيف متدرّج حسب العمق (بدل خطوط اتصال حرفية غير مدعومة
        # بموثوقية بـTreeview — راجع نقاش التوضيح البصري) — يبيّن وين
        # بالضبط تعشيش الملف بلمحة، بلا تدقيق كثير بالمسافات البادئة.
        depth_tag = f"depth{min(depth, 4)}"
        # أيقونة 🔒 لملفات "شغل منتهي" — راجع is_path_active بالمُنشئ.
        # عنصر image= حقيقي (لا نص) بموقع ثابت بالصف، يسمح بتمييز نقرة
        # الأيقونة تحديداً (راجع _on_double_click/on_toggle_lock) —
        # التبديل 🔒↔🔓ينعكس فوراً بأي refresh() لاحق (راجع CD:
        # _toggle_lock_for_path).
        locked = not is_dir and not self._is_path_active(path)
        insert_kwargs = {}
        text = icon + name
        if locked:
            if self._lock_icon_locked is not None:
                insert_kwargs["image"] = self._lock_icon_locked
            else:
                text += " 🔒"  # تدهور نظيف لو Pillow غير متوفرة (راجع _build_lock_icons)
        iid = self.tree.insert(parent_iid, "end", text=text, tags=(depth_tag,), **insert_kwargs)
        self._paths[iid] = path
        if is_dir:
            # ابن وهمي بس حتى يظهر سهم التوسيع — يُستبدل بالمحتوى الحقيقي
            # أول ما المستخدم يفتح المجلد فعلاً (راجع _expand_node).
            self.tree.insert(iid, "end", text="", tags=("dummy",))
        return iid

    def _populate_root(self):
        self.tree.delete(*self.tree.get_children(""))
        self._paths = {"": self.root_dir}
        for p in self._list_dir_sorted(self.root_dir):
            self._node_for_path("", p)

    def refresh(self):
        selected_path = self._paths.get(self.tree.focus())
        self._populate_root()
        if selected_path:
            self.reveal_path(selected_path)
        # يغطّي "تُفلتَر مقابل القرص كل عرض" — refresh() تُنادى أصلاً بعد
        # كل حذف/تسمية/نقل/إنشاء (نقطة تجميع واحدة بدل نداء منفصل بكل مكان).
        self._refresh_recent_list()

    def _expand_node(self, iid):
        children = self.tree.get_children(iid)
        if len(children) == 1 and "dummy" in self.tree.item(children[0], "tags"):
            self.tree.delete(children[0])
            dir_path = self._paths.get(iid, self.root_dir)
            for p in self._list_dir_sorted(dir_path):
                self._node_for_path(iid, p)

    def _on_tree_open(self, _event):
        self._expand_node(self.tree.focus())

    # ---------- التحديد والفتح ----------
    def _on_select(self, _event):
        iid = self.tree.focus()
        path = self._paths.get(iid, self.root_dir)
        self.path_label.configure(text=path)
        _save_json(PREFS_PATH, {"last_path": path})

    def _on_double_click(self, event):
        # دبل كليك سريع = فتح دايماً — نلغي أي مؤقّت تعديل مباشر جدولته
        # النقرة الأولى من هالدبل كليك بالغلط (راجع _maybe_schedule_rename).
        if self._rename_after_id is not None:
            self.after_cancel(self._rename_after_id)
            self._rename_after_id = None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        path = self._paths.get(iid)
        if not path:
            return
        # دبل كليك على أيقونة 🔒 تحديداً (لا أي مكان ثاني بنفس الصف) —
        # identify_element يميّز عنصر "image" عن "text"/باقي الصف بدقة،
        # بعكس النص العادي القديم (كان أي نقرة بالصف تفتح الملف بس).
        if self._on_toggle_lock and not self._is_path_active(path):
            element = self.tree.identify_element(event.x, event.y)
            if element in ("image", "Treeitem.image"):
                self._on_toggle_lock(path)
                return
        if os.path.isfile(path):
            self._open_file(path)
        # لو مجلد: التصرف الافتراضي بـTreeview (فتح/طي) يشتغل عادي بلا تدخّل منا.

    def _open_focused(self):
        """Enter يفتح العنصر المحدَّد حالياً — نفس منطق دبل كليك بالضبط."""
        iid = self.tree.focus()
        path = self._paths.get(iid)
        if path and os.path.isfile(path):
            self._open_file(path)

    def _open_file(self, path):
        """يفتح ملف — يعطي فرصة أولاً لـon_open_file (لو انعطت) تتكفّل
        هي بفتحه بطريقتها الخاصة (زي تحميله باستمارة CD للقراءة فقط)؛
        لو رجعت False (أو ما انعطت أصلاً)، يفتحه عادي بالنظام (نفس
        السلوك القديم بالضبط) — راجع شرح on_open_file بـ__init__."""
        handled = self._on_open_file(path) if self._on_open_file else False
        if not handled:
            open_path(path)
        self.record_recent(path)

    def _on_recent_select(self, _event):
        sel = self.recent_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._recent_paths):
            self._open_file(self._recent_paths[idx])

    def record_recent(self, path):
        """يسجّل path كأحدث عنصر "ملموس" (فُتح أو أُنشئ) بقائمة الملفات
        الأخيرة — يرفعه لأعلى لو موجود أصلاً (بلا تكرار)، يقصّها لآخر 8.
        عامة عمداً (مو _record_recent) — تُستدعى داخلياً من _open_file()
        بس هنا حالياً، ومصمَّمة لتُستدعى من خارج هذا الودجت كمان (زي CD
        لاحقاً عند توليد مستند جديد)."""
        prefs = _load_json(PREFS_PATH)
        recent = [p for p in prefs.get(_RECENT_PREFS_KEY, []) if p != path]
        recent.insert(0, path)
        prefs[_RECENT_PREFS_KEY] = recent[:_RECENT_MAX]
        _save_json(PREFS_PATH, prefs)
        self._refresh_recent_list()

    def _refresh_recent_list(self):
        """يعيد بناء عرض قائمة "الأخيرة" — تُفلتَر مقابل القرص كل مرة
        (عنصر مفقود يُحذف بصمت من العرض والتخزين معاً)."""
        prefs = _load_json(PREFS_PATH)
        recent = prefs.get(_RECENT_PREFS_KEY, [])
        existing = [p for p in recent if os.path.exists(p)]
        if existing != recent:
            prefs[_RECENT_PREFS_KEY] = existing
            _save_json(PREFS_PATH, prefs)
        self._recent_paths = existing
        self.recent_listbox.delete(0, tk.END)
        for p in existing:
            icon = "📁 " if os.path.isdir(p) else "📄 "
            self.recent_listbox.insert(tk.END, icon + os.path.basename(p))

    def _selected_dir(self):
        """المجلد المستهدَف للعملية الحالية (إنشاء/فتح بمستكشف) — لو المحدَّد
        ملف، نرجّع مجلده الأب؛ لو ما فيه تحديد، نرجّع الجذر."""
        iid = self.tree.focus()
        path = self._paths.get(iid, self.root_dir)
        return path if os.path.isdir(path) else os.path.dirname(path)

    def _open_selected_in_explorer(self):
        open_path(self._selected_dir())

    def _copy_selected_path(self):
        """ينسخ مسار العنصر المحدَّد للحافظة — مفيد لإرساله لشخص ثاني أو
        لصقه بمكان آخر، بلا حاجة لكتابته يدوياً."""
        iid = self.tree.focus()
        path = self._paths.get(iid, self.root_dir)
        self.clipboard_clear()
        self.clipboard_append(path)

    def _jump_to_current_month(self):
        """يقفز مباشرة لمجلد الشهر الحالي (بنفس اصطلاح تسمية الأشهر
        المستخدَم بمجلدات الشغل — YYYY-MM، راجع _month_output_path
        بـui/cd/document.py) — أينما كان بعمق الشجرة (تحت أي خدمة)، بلا
        حاجة لمعرفة اسم الخدمة نفسها (الودجت عام، ما يفترض شي عن CD
        تحديداً). ما يسوي شي لو ما لقى مجلد بهذا الاسم بعد (شهر جديد
        وماكو أي مستند فيه لسا)."""
        target_name = datetime.now().strftime("%Y-%m")
        for dirpath, dirnames, _filenames in os.walk(self.root_dir):
            if target_name in dirnames:
                self.refresh()
                self.reveal_path(os.path.join(dirpath, target_name))
                return

    def _show_context_menu(self, event):
        """قائمة كليك يمين — نفس عمليات شريط الأدوات بالضبط، بس أوضح
        وأسرع من دوران الفأرة لزر معيّن. تحدّد العنصر تحت المؤشر أولاً
        (بدل الاعتماد على تحديد سابق قد يكون مكان ثاني تماماً)."""
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        path = self._paths.get(iid, self.root_dir)
        is_file = bool(iid) and os.path.isfile(path)

        menu = tk.Menu(self, tearoff=0)
        if is_file:
            menu.add_command(label="📂 فتح", command=lambda: self._open_file(path))
            menu.add_command(label="👁️ معاينة", command=self._preview_selected)
            if self._on_toggle_lock and not self._is_path_active(path):
                menu.add_command(label="🔓 فتح للتعديل", command=lambda: self._on_toggle_lock(path))
        menu.add_command(label="📁 فتح بمستكشف ويندوز", command=self._open_selected_in_explorer)
        menu.add_command(label="📋 نسخ المسار", command=self._copy_selected_path)
        menu.add_separator()
        menu.add_command(label="📁+ مجلد جديد", command=self._new_folder)
        if iid and path != self.root_dir:
            menu.add_command(label="✏️ إعادة تسمية", command=self._rename_selected)
            menu.add_command(label="🗑️ حذف", command=self._delete_selected)
        menu.add_separator()
        # هذولا دايماً بالقائمة (بغض النظر عن التحديد) — بديل شريط
        # الأزرار العلوي المحذوف كليّاً (راجع _build_ui).
        menu.add_command(label="🔄 تحديث", command=self.refresh)
        menu.add_command(label="📅 الشهر الحالي", command=self._jump_to_current_month)
        menu.tk_popup(event.x_root, event.y_root)

    # ---------- إنشاء / إعادة تسمية / حذف ----------
    def _new_folder(self):
        target_dir = self._selected_dir()
        name = simpledialog.askstring("مجلد جديد", "اسم المجلد الجديد:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name or any(c in name for c in _INVALID_NAME_CHARS):
            alerts.error("خطأ", "اسم غير صالح.")
            return
        new_path = os.path.join(target_dir, name)
        if os.path.exists(new_path):
            alerts.error("خطأ", "فيه ملف/مجلد بنفس الاسم أصلاً.")
            return
        try:
            os.makedirs(new_path)
        except OSError as exc:
            alerts.error("خطأ", f"تعذر إنشاء المجلد:\n{exc}")
            return
        self.refresh()
        self.reveal_path(new_path)

    def _rename_selected(self):
        """F2 وقائمة كليك يمين ("✏️ إعادة تسمية") ينادوا هذي — تفتح
        تعديل مباشر بالسطر (راجع _begin_inline_rename)، بلا أي نافذة
        منبثقة (simpledialog انحذف من هون بطلب صريح — منطق ويندوز)."""
        iid = self.tree.focus()
        path = self._paths.get(iid)
        if not path or path == self.root_dir:
            return
        self._begin_inline_rename(iid)

    def _maybe_schedule_rename(self, iid):
        """يُنادى من _on_drag_start (أول ضغطة فأرة) — منطق ويندوز: نقرة
        على عنصر محدَّد أصلاً بعد فترة كافية (لا سحب، لا دبل كليك) تدخل
        تعديل مباشر. نعتمد على self.tree.selection() *قبل* ما Tk يحدّث
        التحديد لهذي النقرة الجديدة (تجري بعدنا) للتفريق بين "كان محدَّد
        أصلاً" و"عم يُحدَّد الآن لأول مرة"."""
        if self._rename_after_id is not None:
            self.after_cancel(self._rename_after_id)
            self._rename_after_id = None
        if not iid or self._editing_iid is not None:
            self._last_clicked_iid = iid
            return
        was_already_selected = iid == self._last_clicked_iid and iid in self.tree.selection()
        self._last_clicked_iid = iid
        path = self._paths.get(iid)
        if was_already_selected and path and path != self.root_dir:
            self._rename_after_id = self.after(
                _RENAME_CLICK_DELAY_MS, lambda: self._begin_inline_rename(iid)
            )

    def _begin_inline_rename(self, iid):
        path = self._paths.get(iid)
        if not path or path == self.root_dir:
            return
        if self._editing_iid is not None:
            self._cancel_inline_rename()
        bbox = self.tree.bbox(iid)
        if not bbox:
            return  # الصف مو ظاهر حالياً (خارج نطاق التمرير) — تجاهل بصمت
        x, y, _width, height = bbox
        row_width = self.tree.winfo_width() - x
        old_name = os.path.basename(path)
        self._editing_iid = iid
        self._rename_entry_var = tk.StringVar(value=old_name)
        entry = ttk.Entry(self.tree, textvariable=self._rename_entry_var)
        # نزيح شوي لليمين (تقريبي) حتى ما نغطّي أيقونة 📁/📄 نفسها — محاذاة
        # مقبولة بلا حاجة لحساب عرض حرف الأيقونة بدقة بكسل.
        entry.place(x=x + 20, y=y, width=max(row_width - 20, 100), height=height)
        entry.focus_set()
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)
        entry.bind("<Return>", lambda _e: self._commit_inline_rename())
        entry.bind("<Escape>", lambda _e: self._cancel_inline_rename())
        entry.bind("<FocusOut>", lambda _e: self._commit_inline_rename())
        self._rename_entry = entry

    def _cancel_inline_rename(self):
        if self._editing_iid is None:
            return
        entry = self._rename_entry
        self._rename_entry = None
        self._editing_iid = None
        if entry is not None:
            entry.destroy()

    def _commit_inline_rename(self):
        if self._editing_iid is None:
            return
        iid = self._editing_iid
        path = self._paths.get(iid)
        new_name = self._rename_entry_var.get().strip() if self._rename_entry_var else ""
        entry = self._rename_entry
        self._rename_entry = None
        self._editing_iid = None
        if entry is not None:
            entry.destroy()
        if not path or not new_name or new_name == os.path.basename(path):
            return
        self._apply_rename(path, new_name)

    def _apply_rename(self, path, new_name):
        """نفس التحقق والتنفيذ القديم بالضبط (اسم غير صالح/متكرر، حماية
        شغل منتهي) — بس مستقلة عن مصدر الاسم الجديد (تعديل مباشر بالسطر
        الآن، بدل simpledialog.askstring)."""
        if any(c in new_name for c in _INVALID_NAME_CHARS):
            alerts.error("خطأ", "اسم غير صالح.")
            return
        new_path = os.path.join(os.path.dirname(path), new_name)
        if os.path.exists(new_path):
            alerts.error("خطأ", "فيه ملف/مجلد بنفس الاسم أصلاً.")
            return
        # حماية إضافية لملف "شغل منتهي" (راجع is_path_active بالمُنشئ) —
        # تأكيد أوضح بس، مو منع كامل. الملف الجاري (تبويبه مفتوح فعلاً)
        # يبقى بلا أي احتكاك زيادة، زي دايماً.
        if not self._is_path_active(path):
            if not alerts.confirm_always(
                "إعادة تسمية شغل منتهي", f"⚠️ هذا شغل منتهي (تبويبه مسكّر) — متأكد تريد إعادة تسميته؟\n\n{path}",
            ):
                return
        try:
            os.rename(path, new_path)
        except OSError as exc:
            alerts.error("خطأ", f"تعذر إعادة التسمية:\n{exc}")
            return
        self.refresh()
        self.reveal_path(new_path)

    def _delete_selected(self):
        iid = self.tree.focus()
        path = self._paths.get(iid)
        if not path or path == self.root_dir:
            return
        # حذف حقيقي من القرص — نهائي وغير قابل للتراجع، فتأكيده دائماً فعلي
        # (بعكس تنبيهات بيانات CD المؤقتة، هذا خطر من نوع مختلف تماماً).
        # لملف "شغل منتهي" (راجع is_path_active بالمُنشئ)، نأكّد بصياغة
        # أوضح تنبّهك إنه ليس عمل جارٍ عشوائي.
        kind = "المجلد وكل محتوياته" if os.path.isdir(path) else "الملف"
        if not self._is_path_active(path):
            msg = f"⚠️ هذا شغل منتهي (تبويبه مسكّر) — تريد حذف {kind} نهائياً؟\n\n{path}"
        else:
            msg = f"تريد حذف {kind} نهائياً؟\n\n{path}"
        if not alerts.confirm_always("تأكيد الحذف", msg):
            return
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError as exc:
            alerts.error("خطأ", f"تعذر الحذف:\n{exc}")
            return
        self.refresh()

    # ---------- البحث السريع (بكل الشجرة، مو بس المفتوح ظاهرياً) ----------
    def _on_search_change(self):
        query = self.search_var.get().strip().lower()
        if not query:
            self._populate_root()
            return
        matches = []
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            for name in dirnames + filenames:
                if query in name.lower():
                    matches.append(os.path.join(dirpath, name))
        self.tree.delete(*self.tree.get_children(""))
        self._paths = {"": self.root_dir}
        for path in sorted(matches, key=lambda p: os.path.basename(p).lower()):
            rel = os.path.relpath(path, self.root_dir)
            icon = "📁 " if os.path.isdir(path) else "📄 "
            iid = self.tree.insert("", "end", text=f"{icon}{rel}")
            self._paths[iid] = path

    # ---------- نقل بالسحب والإفلات (منفَّذ يدوياً بأحداث الفأرة) ----------
    def _on_drag_start(self, event):
        iid = self.tree.identify_row(event.y)
        self._drag_iid = iid
        self._drag_started = False
        self._maybe_schedule_rename(iid)

    def _clear_drop_highlight(self):
        if self._drop_target_iid is not None:
            try:
                self.tree.item(self._drop_target_iid, tags=())
            except tk.TclError:
                pass  # العنصر ممكن يكون انمسح (refresh) وسط السحب
            self._drop_target_iid = None

    def _on_drag_motion(self, event):
        if not self._drag_iid:
            return
        if not self._drag_started:
            # أول حركة فعلية بعد الضغطة تبدأ السحب — نلغي أي مؤقّت تعديل
            # مباشر جدولته الضغطة (سحب حقيقي، مو نقرة تعديل).
            if self._rename_after_id is not None:
                self.after_cancel(self._rename_after_id)
                self._rename_after_id = None
            self._hide_tooltip()
        self._drag_started = True
        src_path = self._paths.get(self._drag_iid)
        if src_path:
            self.tree.configure(cursor="fleur")  # مؤشر "نقل" أثناء السحب الفعلي
            self._show_drag_ghost(src_path, event.x_root, event.y_root)
        self._clear_drop_highlight()
        target_iid = self.tree.identify_row(event.y)
        if target_iid and target_iid != self._drag_iid:
            target_path = self._paths.get(target_iid)
            if target_path and os.path.isdir(target_path):
                self.tree.item(target_iid, tags=("drop_target",))
                self._drop_target_iid = target_iid
                self._hide_drop_line()
                return
            if target_path:
                # الهدف ملف لا مجلد — الوجهة الفعلية مجلده الأب (نفس منطق
                # _on_drag_release/_move_path تحت)، بس بصرياً نعرض خط رفيع
                # "بين ملفين" بدل تظليل كامل (مو هو نفسه الهدف).
                self._show_drop_line(target_iid)
                return
        self._hide_drop_line()

    def _show_drag_ghost(self, path, x_root, y_root):
        """نافذة عائمة صغيرة تتبع الفأرة أثناء السحب — تعرض أيقونة+اسم
        العنصر المسحوب، بإعادة استخدام نفس تقنية _show_tooltip."""
        icon = "📁 " if os.path.isdir(path) else "📄 "
        if self._drag_ghost is None:
            self._drag_ghost = tk.Toplevel(self)
            self._drag_ghost.wm_overrideredirect(True)
            try:
                self._drag_ghost.attributes("-topmost", True)
            except tk.TclError:
                pass
            self._drag_ghost_label = ttk.Label(
                self._drag_ghost, text=icon + os.path.basename(path),
                background="#ffffe0", relief="solid", borderwidth=1,
                font=("Segoe UI", 9), padding=(4, 2),
            )
            self._drag_ghost_label.pack()
        self._drag_ghost.wm_geometry(f"+{x_root + 14}+{y_root + 14}")

    def _hide_drag_ghost(self):
        if self._drag_ghost is not None:
            self._drag_ghost.destroy()
            self._drag_ghost = None

    def _show_drop_line(self, iid):
        bbox = self.tree.bbox(iid)
        if not bbox:
            self._hide_drop_line()
            return
        _x, y, _width, height = bbox
        if self._drop_line is None:
            self._drop_line = tk.Frame(self.tree, height=2, background="#2f7fd1")
        self._drop_line.place(x=0, y=y + height - 1, relwidth=1.0, height=2)

    def _hide_drop_line(self):
        if self._drop_line is not None:
            self._drop_line.place_forget()

    def _on_drag_release(self, event):
        self._clear_drop_highlight()
        self._hide_drop_line()
        self._hide_drag_ghost()
        self.tree.configure(cursor="")
        drag_iid, drag_started = self._drag_iid, self._drag_started
        self._drag_iid = None
        self._drag_started = False
        if not drag_started or not drag_iid:
            return  # مجرد نقرة عادية (اختيار)، مو سحب فعلي

        src_path = self._paths.get(drag_iid)
        if not src_path or src_path == self.root_dir:
            return
        target_iid = self.tree.identify_row(event.y)
        target_path = self._paths.get(target_iid) if target_iid else self.root_dir
        if target_path is None:
            return
        dest_dir = target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
        self._move_path(src_path, dest_dir)

    def _move_path(self, src_path, dest_dir):
        abs_src = os.path.abspath(src_path)
        abs_dest = os.path.abspath(dest_dir)
        conflict_key = (abs_src, abs_dest)

        if abs_dest == os.path.abspath(os.path.dirname(src_path)):
            self._last_conflict = None
            return  # أفلت بنفس مكانه أصلاً — ما فيه شي نسويه
        if os.path.isdir(src_path) and (abs_dest == abs_src or abs_dest.startswith(abs_src + os.sep)):
            # رفض صامت (بطلب صريح) — نقل مجلد داخل نفسه/أحد فروعه غلطة
            # واضحة بصرياً وقت السحب نفسه (التظليل ما يقبل هالهدف أصلاً
            # بالمعتاد)، ما يستاهل نافذة خطأ زيادة.
            self._last_conflict = None
            return
        new_path = os.path.join(dest_dir, os.path.basename(src_path))
        if os.path.exists(new_path):
            if self._last_conflict == conflict_key:
                # نفس المحاولة بالضبط (نفس المصدر + الوجهة) مرة ثانية
                # متتالية — المستخدم يصرّ، تنبيه صريح هالمرة.
                alerts.error("خطأ", "فيه ملف/مجلد بنفس الاسم بالمكان الهدف أصلاً.")
            else:
                # أول محاولة على هالتعارض بالذات — ومضة لونية على الملف
                # الموجود أصلاً بس، بلا أي نافذة (أقل إزعاجاً لسحبة عرضية).
                self._last_conflict = conflict_key
                existing_iid = next((i for i, p in self._paths.items() if p == new_path), None)
                self._flash_row(existing_iid)
            return
        self._last_conflict = None  # محاولة مختلفة (نجحت أو غير متعارضة) تصفّر حالة آخر تعارض

        # النقل بالسحب والإفلات كان بلا أي تأكيد إطلاقاً (ثغرة حقيقية —
        # سحبة يد بالغلط تنقل ملف بصمت) — لملف "شغل جارٍ" (تبويبه مفتوح)
        # نتركه بلا احتكاك زيادة زي دايماً، لكن لملف "شغل منتهي" نأكّد
        # صراحة قبل النقل (راجع is_path_active بالمُنشئ).
        if not self._is_path_active(src_path):
            if not alerts.confirm_always(
                "نقل شغل منتهي", f"⚠️ هذا شغل منتهي (تبويبه مسكّر) — متأكد تريد نقله؟\n\n{src_path}",
            ):
                return
        try:
            shutil.move(src_path, dest_dir)
        except OSError as exc:
            alerts.error("خطأ", f"تعذر نقل الملف:\n{exc}")
            return
        self.refresh()
        self.reveal_path(new_path)

    def _flash_row(self, iid, color="#ffe08a", duration_ms=500):
        """ومضة لونية نصف ثانية على صف معيّن — إشارة خفيفة غير مزعجة
        لتعارض اسم بالسحب (أول محاولة بس — راجع _move_path)."""
        if not iid:
            return
        try:
            original_tags = self.tree.item(iid, "tags")
        except tk.TclError:
            return
        self.tree.tag_configure("_flash", background=color)
        self.tree.item(iid, tags=("_flash",))
        self.after(duration_ms, lambda: self._restore_tags_if_still_flashing(iid, original_tags))

    def _restore_tags_if_still_flashing(self, iid, original_tags):
        try:
            if self.tree.item(iid, "tags") == ("_flash",):
                self.tree.item(iid, tags=original_tags)
        except tk.TclError:
            pass  # العنصر ممكن يكون انمسح (refresh) خلال الومضة

    # ---------- تذكّر آخر مكان بين الجلسات ----------
    def _restore_last_location(self):
        prefs = _load_json(PREFS_PATH)
        last_path = prefs.get("last_path")
        if last_path and os.path.exists(last_path):
            self.reveal_path(last_path)

    def reveal_path(self, path):
        """يفتح كل المجلدات الأب حتى يوصل للمسار المطلوب، ويحدّده — يُستخدم
        بعد أي عملية (إنشاء/تسمية/نقل) حتى تبقى النتيجة ظاهرة قدّامك مباشرة،
        وباسترجاع آخر مكان بين الجلسات."""
        try:
            rel = os.path.relpath(path, self.root_dir)
        except ValueError:
            return
        if rel == os.curdir:
            return
        if rel.startswith(".."):
            return  # خارج نطاق الشريط أصلاً (ما لازم يصير عادةً)
        parts = rel.split(os.sep)
        parent_iid = ""
        for part in parts:
            self._expand_node(parent_iid)
            found = next(
                (c for c in self.tree.get_children(parent_iid)
                 if self._paths.get(c) and os.path.basename(self._paths[c]) == part),
                None,
            )
            if found is None:
                return
            self.tree.item(found, open=True)
            parent_iid = found
        self.tree.selection_set(parent_iid)
        self.tree.see(parent_iid)
        self.tree.focus(parent_iid)
        self.path_label.configure(text=self._paths.get(parent_iid, ""))
