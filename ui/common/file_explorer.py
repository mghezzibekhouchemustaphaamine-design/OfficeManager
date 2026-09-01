"""
شريط شجرة الشغل (يسار الشاشة) — **انعكاس لقاعدة البيانات، لا ماسح قرص**
(راجع docs/cd-clients-architecture.md بند 1). الشجرة تُبنى مباشرة من
`list_cd_documents_for_tree()`: كل صف `cd_documents` عقدة ملف (leaf)
تحمل `row_id` جاهز، مجمّعة تحت مجلد زبونها (`travail/<اسم>`، مسطّح) أو
تحت `Autre/<الشهر>` (شغل بلا زبون معروف). ملف حطّه المستخدم يدوياً بمجلد
بلا أي سطر CD يخصّه **ما يبان بالشريط إطلاقاً** — مو جزء من "شغل
البرنامج" (الأداة الصحيحة لتصفّح ملفات خام: "📁 فتح بمستكشف ويندوز").

تجربة المستخدم تبقى زي إكسبلورر ويندوز (تصفّح، فتح، بحث سريع، تسمية،
سحب/إفلات) — التغيير بـ"مصدر" الشجرة لا بـ"شكلها". العمليات:
- فتح ملف (نقرة مزدوجة/📂): يمرّ عبر on_open_file(row_id, path) أولاً.
- إعادة تسمية مباشرة بالسطر (منطق ويندوز): تجدّد اسم الملفين (docx+pdf)
  معاً عبر case_ops.rename_case — البادئة "CD_" ثابتة خارج خانة الكتابة.
- سحب/إفلات = اختصار بصري لعملية "نقل الحالة": فوق مجلد زبون → ربط/تغيير
  زبون؛ فوق Autre → فك ربط؛ أي مكان ثاني → مرفوض بصمت.
- القفل حاجز صارم: لملف "شغل منتهي" (is_path_active ترجع False) التسمية
  والسحب ما تشتغل إطلاقاً إلا بعد "🔓 فتح للتعديل".
- الحذف الفردي لحالة **مؤجَّل عمداً** — غير مدعوم بهذا الإصدار (بند 4-ز).

يتذكّر آخر حالة كنت واقف عندها بين الجلسات عبر ملف تفضيلات محلي بسيط
(file_explorer_prefs.json).
"""
import json
import os
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from ui.common import alerts

from programme.utils import open_path
from programme.paths import get_travail_root, get_autre_dir, get_client_dir
from programme.database import (
    list_cd_documents_for_tree, search_cd_documents, get_cd_document,
)
from programme.case_ops import move_case, rename_case

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPLORER_ROOT = get_travail_root()
PREFS_PATH = os.path.join(_APP_ROOT, "file_explorer_prefs.json")

_INVALID_NAME_CHARS = '\\/:*?"<>|'

# منطق ويندوز لإعادة التسمية: نقرة ثانية على عنصر محدَّد أصلاً بعد هالمدة
# تُحسب "نقرة تعديل" لا جزء من دبل كليك — راجع _maybe_schedule_rename.
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


def _norm(path):
    """تطبيع مسار للمقارنة (abspath + normcase — حماية فرق حالة الأحرف
    بويندوز)."""
    try:
        return os.path.normcase(os.path.abspath(path))
    except (TypeError, ValueError):
        return None


class FileExplorerPanel(ttk.Frame):
    def __init__(
        self, parent, root_dir=None, width=220, is_path_active=None, on_open_file=None,
        on_toggle_lock=None,
    ):
        """كل الـcallbacks تاخذ (row_id, path) — الشجرة تبني من قاعدة
        البيانات وعندها row_id جاهز لكل عقدة ملف، فأبسط وأدق من إعادة
        البحث بالمسار بكل استدعاء.

        is_path_active (اختياري): (row_id, path) -> True/False — "شغل
        جارٍ وقابل للتعديل" (True) مقابل "شغل منتهي/مقفول" (False). لملف
        منتهي، إعادة التسمية والسحب **ما تشتغلان إطلاقاً** (حاجز صارم، لا
        تأكيد قابل للتجاوز) إلا بعد فك القفل. بلا تمرير، كل شي "جارٍ".

        on_open_file (اختياري): (row_id, path) -> True/False — تُستدعى
        قبل الفتح الافتراضي بالنظام؛ لو رجعت True تكفّلت هي بالفتح.

        on_toggle_lock (اختياري): (row_id, path) -> بلا رجعة — تُستدعى عند
        دبل كليك على أيقونة 🔒 لملف منتهي **تحديداً** (لا أي مكان ثاني
        بالصف)، أو من "🔓 فتح للتعديل" بقائمة كليك يمين."""
        super().__init__(parent, padding=(4, 4))
        self.root_dir = root_dir or EXPLORER_ROOT
        try:
            os.makedirs(self.root_dir, exist_ok=True)
        except OSError:
            pass
        self._width = width
        self.configure(width=width)
        self.pack_propagate(False)
        self._is_path_active = is_path_active or (lambda _row_id, _path: True)
        self._on_open_file = on_open_file
        self._on_toggle_lock = on_toggle_lock

        # iid -> مسار قرص (عقد الملفات: pdf_path or file_path؛ عقد المجلدات:
        # مسار المجلد على القرص). iid -> صف cd_documents (عقد الملفات بس).
        self._paths = {}
        self._rows = {}
        self._recent_row_ids = []

        self._drag_iid = None
        self._drag_started = False
        self._drop_target_iid = None
        self._drag_ghost = None

        self._rename_after_id = None
        self._last_clicked_iid = None
        self._editing_iid = None
        self._rename_entry = None
        self._rename_entry_var = None
        self._rename_prefix = ""       # بادئة "CD_" المحمية (خارج خانة الكتابة)
        self._rename_prefix_label = None

        self._hover_iid = None
        self._hover_original_tags = ()

        self._last_conflict = None

        # ترتيب ملفات الحالات (leaves) جوّا كل مجلد — "name"/"created"/
        # "modified"، محفوظ بـfile_explorer_prefs.json. مجلدات الجذر
        # (زبائن + Autre) تبقى أبجدية دائماً، ومجلدات الشهور الأحدث
        # أولاً — بلا تأثّر بهالتفضيل (راجع بند 6 بمستند التصميم).
        self._sort_by = self._load_sort_pref()
        self._sort_var = tk.StringVar(value=self._sort_by)

        self._lock_icon_locked = None
        self._lock_icon_unlocked = None
        self._build_lock_icons()

        self._build_ui()
        self._rebuild_tree()
        self._restore_last_location()
        self._refresh_recent_list()

    # ---------- بناء الواجهة ----------
    def _build_ui(self):
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
        style = ttk.Style(self)
        style.configure("FileExplorer.Treeview", indent=28)
        self.tree.configure(style="FileExplorer.Treeview")
        for level, shade in enumerate(("#ffffff", "#f5f7fa", "#eaeef3", "#dde3ea", "#cfd7e0")):
            self.tree.tag_configure(f"depth{level}", background=shade)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<ButtonPress-1>", self._on_drag_start)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<F2>", lambda _e: self._rename_selected())
        self.tree.bind("<Return>", lambda _e: self._open_focused())
        self.tree.bind("<Control-f>", self._focus_search)
        self.tree.bind("<Control-F>", self._focus_search)
        self.bind("<Control-f>", self._focus_search)
        self.bind("<Control-F>", self._focus_search)
        self._tooltip = None
        self._tooltip_after_id = None
        self._tooltip_row = None
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)

        self.path_label = ttk.Label(
            self, text="", anchor="w",
            wraplength=self._width if isinstance(self._width, int) else 200,
            font=("Segoe UI", 8), foreground="#555",
        )
        self.path_label.pack(fill="x", pady=(4, 0))

    def _focus_search(self, _event=None):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
        return "break"

    # ---------- تلميح الاسم الكامل + تظليل الصف تحت الفأرة ----------
    def _on_tree_motion(self, event):
        if self._drag_iid and self._drag_started:
            return
        row = self.tree.identify_row(event.y)
        self._update_hover_highlight(row)
        if row != self._tooltip_row:
            self._hide_tooltip()
            self._tooltip_row = row
            if row:
                self._tooltip_after_id = self.after(
                    500, lambda: self._show_tooltip(row, event.x_root, event.y_root)
                )

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
                pass
            self._hover_iid = None
        if row:
            self._hover_original_tags = self.tree.item(row, "tags")
            self.tree.tag_configure("_hover", background="#e8f0fe")
            self.tree.item(row, tags=("_hover",))
            self._hover_iid = row

    def _show_tooltip(self, row, x_root, y_root):
        text = self.tree.item(row, "text") if self.tree.exists(row) else ""
        if not text:
            return
        self._tooltip = tk.Toplevel(self)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.wm_geometry(f"+{x_root + 12}+{y_root + 12}")
        ttk.Label(
            self._tooltip, text=text.lstrip("📁📄⚠️ "), background="#ffffe0", relief="solid",
            borderwidth=1, font=("Segoe UI", 9), padding=(4, 2),
        ).pack()

    def _hide_tooltip(self):
        if self._tooltip_after_id is not None:
            self.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._tooltip_row = None

    # ---------- معاينة سريعة (صور بس) ----------
    def _preview_selected(self):
        iid = self.tree.focus()
        path = self._paths.get(iid)
        if not path or iid not in self._rows:
            alerts.info("معاينة", "اختر ملفاً أولاً.")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in _IMAGE_EXTS:
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
        label.image = photo
        label.pack()

    # ---------- بناء الشجرة من قاعدة البيانات ----------
    def _depth_of(self, iid):
        depth = 0
        while iid:
            iid = self.tree.parent(iid)
            depth += 1
        return depth

    def _build_lock_icons(self):
        """يبني أيقونتي 🔒/🔓 كـPhotoImage حقيقية (عنصر Treeview image=،
        لا نص) — مرة وحدة، تُعاد استخدامها لكل صف، وتسمح بتمييز نقرة على
        الأيقونة تحديداً عبر identify_element. تدهور نظيف لنص "🔒" لو
        Pillow غير متوفرة."""
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

    def _month_of(self, row):
        src = (row.get("doc_date") or row.get("created_at") or "")[:7]
        return src if len(src) == 7 else datetime.now().strftime("%Y-%m")

    @staticmethod
    def _row_display_name(row):
        path = row.get("pdf_path") or row.get("file_path")
        if path:
            return os.path.basename(path)
        return f"(بلا ملف) #{row['id']}"

    def _insert_folder(self, iid, parent, label, disk_path):
        depth = self._depth_of(parent) if parent else 0
        self.tree.insert(
            parent, "end", iid=iid, text="📁 " + label,
            tags=(f"depth{min(depth, 4)}",), open=False,
        )
        self._paths[iid] = disk_path

    def _insert_leaf(self, row, parent):
        iid = f"row:{row['id']}"
        path = row.get("pdf_path") or row.get("file_path")
        name = self._row_display_name(row)
        on_disk = bool(path and os.path.exists(path))
        depth = self._depth_of(parent) + 1
        locked = not self._is_path_active(row["id"], path)
        text = "📄 " + name
        if not on_disk:
            # الملف انمسح فيزيائياً برّة البرنامج — نعرضه بردو (الحالة
            # موجودة بقاعدة البيانات) لكن نعلّمه بصرياً بدل ما يختفي بصمت.
            text = "⚠️ " + text
        insert_kwargs = {}
        if locked:
            if self._lock_icon_locked is not None:
                insert_kwargs["image"] = self._lock_icon_locked
            else:
                text += " 🔒"
        self.tree.insert(
            parent, "end", iid=iid, text=text,
            tags=(f"depth{min(depth, 4)}",), **insert_kwargs,
        )
        self._paths[iid] = path
        self._rows[iid] = row

    @staticmethod
    def _load_sort_pref():
        v = _load_json(PREFS_PATH).get("sort_by")
        return v if v in ("name", "created", "modified") else "name"

    def _set_sort_by(self, value):
        if value not in ("name", "created", "modified"):
            return
        self._sort_by = value
        self._sort_var.set(value)
        prefs = _load_json(PREFS_PATH)
        prefs["sort_by"] = value
        _save_json(PREFS_PATH, prefs)
        # لو كنا وسط بحث، أعِد ترتيب نتائجه؛ وإلا أعِد بناء الشجرة.
        if self.search_var.get().strip():
            self._on_search_change()
        else:
            self.refresh()

    def _sorted_rows(self, rows):
        """ترتيب ملفات الحالات جوّا مجلد واحد حسب التفضيل المحفوظ:
        الاسم (تصاعدي أبجدي)، أو تاريخ الإنشاء/آخر تعديل (الأحدث أولاً —
        نفس اتجاه مجلدات الشهور بالشجرة). المصدر دايماً أعمدة قاعدة
        البيانات (created_at/updated_at)، لا وقت الملف الفيزيائي —
        updated_at فاضي لمستند قديم فنرجع لـcreated_at."""
        if self._sort_by == "created":
            return sorted(rows, key=lambda r: (r.get("created_at") or "", r["id"]), reverse=True)
        if self._sort_by == "modified":
            return sorted(
                rows,
                key=lambda r: (r.get("updated_at") or r.get("created_at") or "", r["id"]),
                reverse=True,
            )
        return sorted(rows, key=lambda r: (self._row_display_name(r).casefold(), r["id"]))

    def _rebuild_tree(self):
        self.tree.delete(*self.tree.get_children(""))
        self._paths = {"": self.root_dir}
        self._rows = {}
        try:
            rows = list_cd_documents_for_tree()
        except Exception:  # noqa: BLE001
            rows = []

        clients = {}
        autre = []
        for r in rows:
            cid = r.get("client_id")
            if cid is not None:
                c = clients.setdefault(cid, {
                    "name": r.get("client_name") or f"زبون #{cid}",
                    "folder_name": r.get("client_folder_name")
                    or r.get("client_name") or f"client_{cid}",
                    "rows": [],
                })
                c["rows"].append(r)
            else:
                autre.append(r)

        # مجلدات الزبائن (أبجدي بالاسم)، بس اللي عندهم ≥ صف واحد (⚠️ قرار
        # تنفيذي: زبون بلا أي مستند ما يبان بالشريط — الشجرة انعكاس لـ"شنو
        # موجود فعلاً").
        for cid, c in sorted(clients.items(), key=lambda kv: (kv[1]["name"] or "").casefold()):
            fiid = f"client:{cid}"
            self._insert_folder(fiid, "", c["name"], get_client_dir(c["folder_name"]))
            for r in self._sorted_rows(c["rows"]):
                self._insert_leaf(r, fiid)

        # Autre — مجلدات فرعية بالشهر (الأحدث أولاً)
        if autre:
            self._insert_folder("autre", "", "Autre", get_autre_dir())
            months = {}
            for r in autre:
                months.setdefault(self._month_of(r), []).append(r)
            for ym in sorted(months.keys(), reverse=True):
                miid = f"month:{ym}"
                self._insert_folder(miid, "autre", ym, os.path.join(get_autre_dir(), ym))
                for r in self._sorted_rows(months[ym]):
                    self._insert_leaf(r, miid)

    def refresh(self):
        focused = self.tree.focus()
        keep_row = self._rows[focused]["id"] if focused in self._rows else None
        self._rebuild_tree()
        if keep_row is not None:
            self.reveal_row(keep_row)
        self._refresh_recent_list()

    # ---------- التحديد والفتح ----------
    def _on_select(self, _event):
        iid = self.tree.focus()
        path = self._paths.get(iid, self.root_dir)
        self.path_label.configure(text=path or self.root_dir)
        if iid in self._rows:
            prefs = _load_json(PREFS_PATH)
            prefs["last_row_id"] = self._rows[iid]["id"]
            _save_json(PREFS_PATH, prefs)

    def _on_double_click(self, event):
        if self._rename_after_id is not None:
            self.after_cancel(self._rename_after_id)
            self._rename_after_id = None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid in self._rows:
            row = self._rows[iid]
            path = self._paths.get(iid)
            # دبل كليك على أيقونة 🔒 تحديداً (لا أي مكان ثاني بالصف).
            if self._on_toggle_lock and not self._is_path_active(row["id"], path):
                element = self.tree.identify_element(event.x, event.y)
                if element in ("image", "Treeitem.image"):
                    self._on_toggle_lock(row["id"], path)
                    return
            self._open_row_id(row["id"])
        # مجلد: سلوك Treeview الافتراضي (فتح/طي) يشتغل بلا تدخّل.

    def _open_focused(self):
        iid = self.tree.focus()
        if iid in self._rows:
            self._open_row_id(self._rows[iid]["id"])

    def _open_row_id(self, row_id):
        doc = get_cd_document(row_id)
        if doc is None:
            alerts.error("خطأ", "الحالة غير موجودة بقاعدة البيانات (ربما حُذفت).")
            return
        path = doc.get("pdf_path") or doc.get("file_path")
        handled = self._on_open_file(row_id, path) if self._on_open_file else False
        if not handled:
            if path and os.path.exists(path):
                open_path(path)
            else:
                alerts.error("خطأ", "الملف غير موجود (ربما نُقل أو حُذف خارج البرنامج).")
        self.record_recent(row_id)

    def _on_recent_select(self, _event):
        sel = self.recent_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._recent_row_ids):
            self._open_row_id(self._recent_row_ids[idx])

    def record_recent(self, row_id):
        """يسجّل الحالة كأحدث عنصر "ملموس" بقائمة الأخيرة (بلا تكرار،
        آخر 8) — عامة عمداً، مصمَّمة لتُستدعى من خارج الودجت كمان (زي CD
        عند توليد مستند)."""
        prefs = _load_json(PREFS_PATH)
        recent = [
            e for e in prefs.get(_RECENT_PREFS_KEY, [])
            if not (isinstance(e, dict) and e.get("row_id") == row_id)
        ]
        recent.insert(0, {"row_id": row_id})
        prefs[_RECENT_PREFS_KEY] = recent[:_RECENT_MAX]
        _save_json(PREFS_PATH, prefs)
        self._refresh_recent_list()

    def _refresh_recent_list(self):
        """يعيد بناء قائمة "الأخيرة" — كل عنصر يُقرأ مساره **الحالي** من
        قاعدة البيانات بالـrow_id (يحمي من مسارات قديمة بعد نقل/تسمية)،
        وعنصر لحالة ما عادت موجودة يختفي بصمت من العرض والتخزين."""
        prefs = _load_json(PREFS_PATH)
        raw = [e for e in prefs.get(_RECENT_PREFS_KEY, []) if isinstance(e, dict) and e.get("row_id") is not None]
        self._recent_row_ids = []
        names = []
        for e in raw:
            doc = get_cd_document(e["row_id"])
            if doc is None:
                continue
            path = doc.get("pdf_path") or doc.get("file_path")
            self._recent_row_ids.append(e["row_id"])
            names.append(os.path.basename(path) if path else f"#{e['row_id']}")
        kept = [{"row_id": rid} for rid in self._recent_row_ids]
        if kept != raw:
            prefs[_RECENT_PREFS_KEY] = kept
            _save_json(PREFS_PATH, prefs)
        self.recent_listbox.delete(0, tk.END)
        for name in names:
            self.recent_listbox.insert(tk.END, "📄 " + name)

    def _selected_dir(self):
        iid = self.tree.focus()
        if iid in self._rows:
            path = self._paths.get(iid)
            return os.path.dirname(path) if path else self.root_dir
        return self._paths.get(iid, self.root_dir)

    def _open_selected_in_explorer(self):
        target = self._selected_dir()
        if not open_path(target):
            alerts.info("غير موجود", "هذا المجلد ما اتكوّن على القرص بعد (ماكو ملفات فيه).")

    def _copy_selected_path(self):
        iid = self.tree.focus()
        path = self._paths.get(iid, self.root_dir)
        self.clipboard_clear()
        self.clipboard_append(path or self.root_dir)

    def _jump_to_current_month(self):
        """يقفز لمجلد الشهر الحالي **جوّا Autre بس** (لا مسح كل الجذر)."""
        iid = f"month:{datetime.now().strftime('%Y-%m')}"
        if self.tree.exists(iid):
            self.tree.item("autre", open=True)
            self.tree.item(iid, open=True)
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self.tree.focus(iid)

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
        is_leaf = iid in self._rows
        path = self._paths.get(iid)

        menu = tk.Menu(self, tearoff=0)
        if is_leaf:
            row = self._rows[iid]
            menu.add_command(label="📂 فتح", command=lambda: self._open_row_id(row["id"]))
            menu.add_command(label="👁️ معاينة", command=self._preview_selected)
            if self._on_toggle_lock and not self._is_path_active(row["id"], path):
                menu.add_command(
                    label="🔓 فتح للتعديل",
                    command=lambda: self._on_toggle_lock(row["id"], path),
                )
            menu.add_command(label="✏️ إعادة تسمية", command=lambda: self._begin_inline_rename(iid))
        menu.add_command(label="📁 فتح بمستكشف ويندوز", command=self._open_selected_in_explorer)
        menu.add_command(label="📋 نسخ المسار", command=self._copy_selected_path)
        menu.add_separator()
        sort_menu = tk.Menu(menu, tearoff=0)
        for val, label in (
            ("name", "🔤 الاسم"), ("created", "🕐 تاريخ الإنشاء"), ("modified", "🕑 آخر تعديل"),
        ):
            sort_menu.add_radiobutton(
                label=label, value=val, variable=self._sort_var,
                command=lambda v=val: self._set_sort_by(v),
            )
        menu.add_cascade(label="↕️ ترتيب حسب", menu=sort_menu)
        menu.add_command(label="🔄 تحديث", command=self.refresh)
        menu.add_command(label="📅 الشهر الحالي", command=self._jump_to_current_month)
        menu.tk_popup(event.x_root, event.y_root)

    # ---------- إعادة التسمية (مباشرة بالسطر، البادئة CD_ محمية) ----------
    def _rename_selected(self):
        iid = self.tree.focus()
        if iid in self._rows:
            self._begin_inline_rename(iid)

    def _maybe_schedule_rename(self, iid):
        if self._rename_after_id is not None:
            self.after_cancel(self._rename_after_id)
            self._rename_after_id = None
        if not iid or self._editing_iid is not None or iid not in self._rows:
            self._last_clicked_iid = iid
            return
        # حاجز القفل الصارم: ملف منتهي ما يدخل تعديل تسمية إطلاقاً.
        row = self._rows[iid]
        if not self._is_path_active(row["id"], self._paths.get(iid)):
            self._last_clicked_iid = iid
            return
        was_already_selected = iid == self._last_clicked_iid and iid in self.tree.selection()
        self._last_clicked_iid = iid
        if was_already_selected:
            self._rename_after_id = self.after(
                _RENAME_CLICK_DELAY_MS, lambda: self._begin_inline_rename(iid)
            )

    def _begin_inline_rename(self, iid):
        row = self._rows.get(iid)
        if row is None:
            return  # المجلدات (زبون/Autre/شهر) لا تُعاد تسميتها — نتجاهل بصمت.
        if not self._is_path_active(row["id"], self._paths.get(iid)):
            alerts.info("مقفول", "افتح القفل أولاً (🔓 فتح للتعديل) قبل إعادة التسمية.")
            return
        if self._editing_iid is not None:
            self._cancel_inline_rename()
        bbox = self.tree.bbox(iid)
        if not bbox:
            return
        x, y, _width, height = bbox
        old_name = self._row_display_name(row)
        root_name, _ext = os.path.splitext(old_name)
        self._rename_prefix = "CD_" if root_name.startswith("CD_") else ""
        editable = root_name[len(self._rename_prefix):]

        self._editing_iid = iid
        prefix_px = 0
        if self._rename_prefix:
            self._rename_prefix_label = tk.Label(
                self.tree, text=self._rename_prefix, bg="#ffffe0", font=("Segoe UI", 9),
                bd=0, padx=1,
            )
            self._rename_prefix_label.place(x=x + 20, y=y, height=height)
            self._rename_prefix_label.update_idletasks()
            prefix_px = self._rename_prefix_label.winfo_reqwidth()

        self._rename_entry_var = tk.StringVar(value=editable)
        entry = ttk.Entry(self.tree, textvariable=self._rename_entry_var)
        row_width = self.tree.winfo_width() - x - 20 - prefix_px
        entry.place(x=x + 20 + prefix_px, y=y, width=max(row_width, 80), height=height)
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
        if self._rename_prefix_label is not None:
            self._rename_prefix_label.destroy()
            self._rename_prefix_label = None

    def _commit_inline_rename(self):
        if self._editing_iid is None:
            return
        iid = self._editing_iid
        row = self._rows.get(iid)
        typed = self._rename_entry_var.get().strip() if self._rename_entry_var else ""
        prefix = self._rename_prefix
        entry = self._rename_entry
        self._rename_entry = None
        self._editing_iid = None
        if entry is not None:
            entry.destroy()
        if self._rename_prefix_label is not None:
            self._rename_prefix_label.destroy()
            self._rename_prefix_label = None
        if row is None or not typed:
            return
        old_root = os.path.splitext(self._row_display_name(row))[0]
        new_base = prefix + typed
        if new_base == old_root:
            return
        self._apply_rename(iid, new_base)

    def _apply_rename(self, iid, new_base_name):
        row = self._rows.get(iid)
        if row is None:
            return
        path = self._paths.get(iid)
        if not self._is_path_active(row["id"], path):
            alerts.info("مقفول", "افتح القفل أولاً (🔓 فتح للتعديل) قبل إعادة التسمية.")
            return
        try:
            rename_case(row["id"], new_base_name)
        except ValueError as exc:
            alerts.error("خطأ", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            alerts.error("خطأ", f"تعذر إعادة التسمية:\n{exc}")
            return
        self.refresh()
        self.reveal_row(row["id"])

    # ---------- البحث السريع (قاعدة البيانات مباشرة) ----------
    def _on_search_change(self):
        query = self.search_var.get().strip()
        if not query:
            self._rebuild_tree()
            self._restore_last_location()
            return
        try:
            results = search_cd_documents(query)
        except Exception:  # noqa: BLE001
            results = []
        self.tree.delete(*self.tree.get_children(""))
        self._paths = {"": self.root_dir}
        self._rows = {}
        for r in self._sorted_rows(results):  # نفس تفضيل الترتيب المحفوظ
            path = r.get("pdf_path") or r.get("file_path")
            name = os.path.basename(path) if path else f"#{r['id']}"
            label = "📄 " + name
            if r.get("client_name"):
                label += f"   — {r['client_name']}"
            iid = f"row:{r['id']}"
            self.tree.insert("", "end", iid=iid, text=label)
            self._paths[iid] = path
            self._rows[iid] = r

    # ---------- سحب وإفلات = اختصار بصري لعملية "نقل الحالة" ----------
    def _on_drag_start(self, event):
        iid = self.tree.identify_row(event.y)
        # بس عقد الملفات (الحالات) قابلة للسحب — لا المجلدات (زبون/Autre/شهر).
        self._drag_iid = iid if iid in self._rows else None
        self._drag_started = False
        if self._drag_iid is not None:
            row = self._rows[self._drag_iid]
            # حاجز القفل الصارم: ملف منتهي ما يُسحب إطلاقاً قبل فك القفل.
            if not self._is_path_active(row["id"], self._paths.get(self._drag_iid)):
                self._drag_iid = None
        self._maybe_schedule_rename(iid)

    def _clear_drop_highlight(self):
        if self._drop_target_iid is not None:
            try:
                kind_tag = self.tree.item(self._drop_target_iid, "tags")
                self.tree.item(self._drop_target_iid, tags=[t for t in kind_tag if t != "drop_target"])
            except tk.TclError:
                pass
            self._drop_target_iid = None

    def _is_drop_target(self, iid):
        return bool(iid) and (iid.startswith("client:") or iid == "autre" or iid.startswith("month:"))

    def _on_drag_motion(self, event):
        if not self._drag_iid:
            return
        if not self._drag_started:
            if self._rename_after_id is not None:
                self.after_cancel(self._rename_after_id)
                self._rename_after_id = None
            self._hide_tooltip()
        self._drag_started = True
        src_path = self._paths.get(self._drag_iid)
        if src_path:
            self.tree.configure(cursor="fleur")
            self._show_drag_ghost(src_path, event.x_root, event.y_root)
        self._clear_drop_highlight()
        target_iid = self.tree.identify_row(event.y)
        if self._is_drop_target(target_iid):
            self.tree.item(target_iid, tags=("drop_target",))
            self._drop_target_iid = target_iid

    def _show_drag_ghost(self, path, x_root, y_root):
        if self._drag_ghost is None:
            self._drag_ghost = tk.Toplevel(self)
            self._drag_ghost.wm_overrideredirect(True)
            try:
                self._drag_ghost.attributes("-topmost", True)
            except tk.TclError:
                pass
            self._drag_ghost_label = ttk.Label(
                self._drag_ghost, text="📄 " + os.path.basename(path),
                background="#ffffe0", relief="solid", borderwidth=1,
                font=("Segoe UI", 9), padding=(4, 2),
            )
            self._drag_ghost_label.pack()
        self._drag_ghost.wm_geometry(f"+{x_root + 14}+{y_root + 14}")

    def _hide_drag_ghost(self):
        if self._drag_ghost is not None:
            self._drag_ghost.destroy()
            self._drag_ghost = None

    def _on_drag_release(self, event):
        self._clear_drop_highlight()
        self._hide_drag_ghost()
        self.tree.configure(cursor="")
        drag_iid, drag_started = self._drag_iid, self._drag_started
        self._drag_iid = None
        self._drag_started = False
        if not drag_started or not drag_iid:
            return  # مجرد نقرة عادية، مو سحب فعلي
        row = self._rows.get(drag_iid)
        if row is None:
            return
        target_iid = self.tree.identify_row(event.y)
        matched, client_id = self._resolve_drop(target_iid)
        if not matched:
            return  # أي هدف ثاني (ملف، نفس مكانه، فراغ) → مرفوض بصمت
        # حاجز القفل الصارم مرة ثانية عند الإفلات نفسه.
        if not self._is_path_active(row["id"], self._paths.get(drag_iid)):
            return
        try:
            move_case(row["id"], client_id)
        except Exception as exc:  # noqa: BLE001
            alerts.error("خطأ", f"تعذر نقل الحالة:\n{exc}")
            return
        self.refresh()
        self.reveal_row(row["id"])

    def _resolve_drop(self, target_iid):
        """(matched, client_id) — مجلد زبون → (True, cid)؛ Autre أو أي
        شهر جوّاها → (True, None)؛ غير هيك → (False, None)."""
        if not target_iid:
            return False, None
        if target_iid.startswith("client:"):
            try:
                return True, int(target_iid.split(":", 1)[1])
            except ValueError:
                return False, None
        if target_iid == "autre" or target_iid.startswith("month:"):
            return True, None
        return False, None

    def _flash_row(self, iid, color="#ffe08a", duration_ms=500):
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
            pass

    # ---------- تذكّر آخر مكان بين الجلسات ----------
    def _restore_last_location(self):
        prefs = _load_json(PREFS_PATH)
        rid = prefs.get("last_row_id")
        if rid is not None:
            self.reveal_row(rid)

    def reveal_row(self, row_id):
        """يفتح كل المجلدات الأب حتى عقدة الحالة ويحدّدها — يُستخدم بعد
        أي عملية (توليد/تسمية/نقل) وباسترجاع آخر مكان بين الجلسات."""
        iid = f"row:{row_id}"
        if not self.tree.exists(iid):
            return
        chain = []
        parent = self.tree.parent(iid)
        while parent:
            chain.append(parent)
            parent = self.tree.parent(parent)
        for p in reversed(chain):
            self.tree.item(p, open=True)
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self.tree.focus(iid)
        self.path_label.configure(text=self._paths.get(iid, ""))

    def reveal_path(self, path):
        """توافقية: يلقى عقدة الحالة اللي أحد ملفيها يطابق المسار المُعطى
        ثم ينادي reveal_row. (المستدعون الجدد يفضّلون reveal_row مباشرة —
        الشجرة تحمل row_id أصلاً.)"""
        target = _norm(path)
        if target is None:
            return
        for iid, row in self._rows.items():
            for cand in (row.get("pdf_path"), row.get("file_path")):
                if cand and _norm(cand) == target:
                    self.reveal_row(row["id"])
                    return
