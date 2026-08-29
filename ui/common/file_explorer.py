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
    def __init__(self, parent, root_dir=None, width=220, is_path_active=None, on_open_file=None):
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
        عادي بالنظام (نفس السلوك القديم بالضبط) — راجع _open_file."""
        super().__init__(parent, padding=(4, 4))
        self.root_dir = root_dir or EXPLORER_ROOT
        os.makedirs(self.root_dir, exist_ok=True)
        self._width = width
        self.configure(width=width)
        self.pack_propagate(False)  # يبقى بعرضه المحدَّد بغض النظر عن محتواه
        self._is_path_active = is_path_active or (lambda _path: True)
        self._on_open_file = on_open_file

        self._paths = {}  # tree item id -> مسار حقيقي بالقرص
        self._drag_iid = None
        self._drag_started = False
        self._drop_target_iid = None

        self._build_ui()
        self._populate_root()
        self._restore_last_location()

    # ---------- بناء الواجهة ----------
    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(toolbar, text="🔄", width=3, command=self.refresh).pack(side="left")
        ttk.Button(toolbar, text="📁+", width=3, command=self._new_folder).pack(side="left", padx=(2, 0))
        ttk.Button(toolbar, text="✏️", width=3, command=self._rename_selected).pack(side="left", padx=(2, 0))
        ttk.Button(toolbar, text="🗑️", width=3, command=self._delete_selected).pack(side="left", padx=(2, 0))
        ttk.Button(toolbar, text="📂", width=3, command=self._open_selected_in_explorer).pack(side="left", padx=(2, 0))
        ttk.Button(toolbar, text="📋", width=3, command=self._copy_selected_path).pack(side="left", padx=(2, 0))
        ttk.Button(toolbar, text="📅", width=3, command=self._jump_to_current_month).pack(side="left", padx=(2, 0))
        ttk.Button(toolbar, text="👁️", width=3, command=self._preview_selected).pack(side="left", padx=(2, 0))

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
        self.tree.bind("<Leave>", lambda _e: self._hide_tooltip())

        self.path_label = ttk.Label(
            self, text="", anchor="w", wraplength=self._width if isinstance(self._width, int) else 200,
            font=("Segoe UI", 8), foreground="#555",
        )
        self.path_label.pack(fill="x", pady=(4, 0))

    def _focus_search(self, _event=None):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
        return "break"

    # ---------- تلميح الاسم الكامل عند التمرير ----------
    def _on_tree_motion(self, event):
        row = self.tree.identify_row(event.y)
        if row != self._tooltip_row:
            self._hide_tooltip()
            self._tooltip_row = row
            if row:
                # تأخير بسيط قبل الظهور (بدل فوري) — يمنع وميض مزعج لو
                # الفأرة بس عابرة، مو واقفة فعلاً فوق العنصر.
                self._tooltip_after_id = self.after(500, lambda: self._show_tooltip(row, event.x_root, event.y_root))

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

    def _node_for_path(self, parent_iid, path):
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        icon = "📁 " if is_dir else "📄 "
        depth = self._depth_of(parent_iid) if parent_iid else 0
        # تظليل خفيف متدرّج حسب العمق (بدل خطوط اتصال حرفية غير مدعومة
        # بموثوقية بـTreeview — راجع نقاش التوضيح البصري) — يبيّن وين
        # بالضبط تعشيش الملف بلمحة، بلا تدقيق كثير بالمسافات البادئة.
        depth_tag = f"depth{min(depth, 4)}"
        # علامة "🔒" معلوماتية بس (بلا أي تفاعل) لملفات "شغل منتهي" —
        # راجع is_path_active بالمُنشئ. الحماية الفعلية (تأكيد أوضح) عند
        # النقل/الحذف/إعادة التسمية، مو هون — هذي بس تنبيه بصري مسبق.
        lock_suffix = " 🔒" if not is_dir and not self._is_path_active(path) else ""
        iid = self.tree.insert(parent_iid, "end", text=icon + name + lock_suffix, tags=(depth_tag,))
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
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        path = self._paths.get(iid)
        if path and os.path.isfile(path):
            self._open_file(path)
        # لو مجلد: التصرف الافتراضي بـTreeview (فتح/طي) يشتغل عادي بلا تدخّل منا.

    def _open_file(self, path):
        """يفتح ملف — يعطي فرصة أولاً لـon_open_file (لو انعطت) تتكفّل
        هي بفتحه بطريقتها الخاصة (زي تحميله باستمارة CD للقراءة فقط)؛
        لو رجعت False (أو ما انعطت أصلاً)، يفتحه عادي بالنظام (نفس
        السلوك القديم بالضبط) — راجع شرح on_open_file بـ__init__."""
        handled = self._on_open_file(path) if self._on_open_file else False
        if not handled:
            open_path(path)

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
        menu.add_command(label="📁 فتح بمستكشف ويندوز", command=self._open_selected_in_explorer)
        menu.add_command(label="📋 نسخ المسار", command=self._copy_selected_path)
        menu.add_separator()
        menu.add_command(label="📁+ مجلد جديد", command=self._new_folder)
        if iid and path != self.root_dir:
            menu.add_command(label="✏️ إعادة تسمية", command=self._rename_selected)
            menu.add_command(label="🗑️ حذف", command=self._delete_selected)
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
        iid = self.tree.focus()
        path = self._paths.get(iid)
        if not path or path == self.root_dir:
            return
        old_name = os.path.basename(path)
        new_name = simpledialog.askstring(
            "إعادة تسمية", "الاسم الجديد:", initialvalue=old_name, parent=self,
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
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
        self._drag_iid = self.tree.identify_row(event.y)
        self._drag_started = False

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
        self._drag_started = True
        self._clear_drop_highlight()
        target_iid = self.tree.identify_row(event.y)
        if target_iid and target_iid != self._drag_iid:
            target_path = self._paths.get(target_iid)
            if target_path and os.path.isdir(target_path):
                self.tree.item(target_iid, tags=("drop_target",))
                self._drop_target_iid = target_iid

    def _on_drag_release(self, event):
        self._clear_drop_highlight()
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
        if abs_dest == os.path.abspath(os.path.dirname(src_path)):
            return  # أفلت بنفس مكانه أصلاً — ما فيه شي نسويه
        if os.path.isdir(src_path) and (abs_dest == abs_src or abs_dest.startswith(abs_src + os.sep)):
            alerts.error("خطأ", "ما تقدر تنقل مجلد داخل نفسه أو داخل أحد مجلداته الفرعية.")
            return
        new_path = os.path.join(dest_dir, os.path.basename(src_path))
        if os.path.exists(new_path):
            alerts.error("خطأ", "فيه ملف/مجلد بنفس الاسم بالمكان الهدف أصلاً.")
            return
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
