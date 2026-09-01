"""نافذة سجل مستندات CD السابقة — بحث سريع (اسم الراكب/رقم البوردرو/رقم
الجواز)، فلتر بالزبون، فتح الملف الأصلي، فتح مستند قديم للتعديل بتبويب
جديد بشاشة CD، إعادة طباعته، وربط/تغيير/فك ربط الزبون — بدل إعادة تعبئة
من الصفر أو البحث يدوياً بمجلدات الأقراص.

ملف مستقل عن tab.py (CDTab يُمرَّر له كمرجع بس عبر المُنشئ، للاستدعاء
بس — CDHistoryWindow ما يعرف تفاصيل بناء الشاشة الداخلية)."""
import os
import tkinter as tk
from tkinter import ttk, simpledialog

from ui.common import alerts
from ui.common.client_picker import ClientPickerEntry

from programme.database import (
    search_cd_documents, deserialize_cd_data, list_clients, delete_client, client_has_documents,
)
from programme.case_ops import move_case
from ui.cd.document import generate_cd_pdf, OUTPUT_DIR
from programme.utils import open_path


class CDHistoryWindow(tk.Toplevel):
    def __init__(self, cd_tab):
        super().__init__(cd_tab)
        self.cd_tab = cd_tab
        self.title("سجل مستندات CD")
        self.geometry("860x460")
        self.transient(cd_tab.winfo_toplevel())

        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        ttk.Label(top, text="بحث (اسم الراكب / رقم البوردرو / رقم الجواز):").pack(side="left")
        self.query_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.query_var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        entry.bind("<KeyRelease>", lambda _e: self._refresh())
        entry.focus_set()

        # فلتر الزبون — يشتغل بـclient_id لا بمطابقة نص الاسم (بند 4-ب
        # بمستند التصميم). نفس مكوّن الاختيار المستخدَم باستمارة CD.
        filt = ttk.Frame(self, padding=(10, 0, 10, 6))
        filt.pack(fill="x")
        ttk.Label(filt, text="فلتر الزبون:").pack(side="left")
        self.client_filter = ClientPickerEntry(filt, on_change=self._on_client_filter_change)
        self.client_filter.pack(side="left", padx=(6, 0))
        ttk.Button(filt, text="✖ مسح الفلتر", command=self._clear_client_filter).pack(side="left", padx=(6, 0))
        ttk.Button(filt, text="👥 إدارة الزبائن", command=self._open_clients_manager).pack(side="right")

        columns = ("dossier_no", "passager", "passport_no", "doc_date", "client_name", "agence", "created_at")
        headers = {
            "dossier_no": "رقم البوردرو", "passager": "الراكب", "passport_no": "رقم الجواز",
            "doc_date": "تاريخ المعاملة", "client_name": "الزبون", "agence": "Agence",
            "created_at": "وقت الإنشاء",
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=110, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)

        btns = ttk.Frame(self, padding=(10, 0, 10, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="📂 فتح الملف المحدَّد", command=self._open_selected).pack(side="left")
        ttk.Button(btns, text="📝 فتح للتعديل بالاستمارة", command=self._load_selected_for_edit).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(btns, text="🖨️ إعادة طباعة", command=self._reprint_selected).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="إغلاق", command=self.destroy).pack(side="right")

        self._rows = []
        self._refresh()

    # ---------- الفلتر ----------
    def _on_client_filter_change(self):
        self._refresh()

    def _clear_client_filter(self):
        self.client_filter.clear()
        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows = search_cd_documents(
            self.query_var.get().strip(), client_id=self.client_filter.get_client_id(),
        )
        for row in self._rows:
            self.tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row.get("dossier_no") or "",
                    row.get("passager") or "",
                    row.get("passport_no") or "",
                    row.get("doc_date") or "",
                    row.get("client_name") or "—",
                    row.get("agence") or "",
                    (row.get("created_at") or "")[:16],
                ),
            )

    def _get_selected_row(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return next((r for r in self._rows if str(r["id"]) == sel[0]), None)

    # ---------- قائمة كليك يمين ----------
    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        row = self._get_selected_row()

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📂 فتح الملف المحدَّد", command=self._open_selected)
        menu.add_command(label="📝 فتح للتعديل بالاستمارة", command=self._load_selected_for_edit)
        menu.add_command(label="🖨️ إعادة طباعة", command=self._reprint_selected)
        menu.add_separator()
        if row is not None:
            if row.get("client_id") is None:
                menu.add_command(label="🔗 اربط بزبون", command=lambda: self._link_client(row))
            else:
                menu.add_command(label="↔️ غيّر الزبون", command=lambda: self._link_client(row))
                menu.add_command(label="🔓 فك الربط", command=lambda: self._unlink_client(row))
        menu.add_separator()
        menu.add_command(label="📁 أظهره بالشريط الجانبي", command=self._reveal_in_sidebar)
        menu.tk_popup(event.x_root, event.y_root)

    # ---------- ربط / تغيير / فك ربط الزبون (عبر عملية "نقل الحالة") ----------
    def _link_client(self, row):
        picked = _PickClientDialog(self, initial=row.get("client_id")).show()
        if picked is _PickClientDialog.CANCEL:
            return
        try:
            move_case(row["id"], picked)
        except Exception as exc:  # noqa: BLE001
            alerts.error("خطأ", f"تعذر نقل الحالة:\n{exc}")
            return
        self._refresh()
        self.cd_tab.explorer_panel.refresh()

    def _unlink_client(self, row):
        if not alerts.confirm(
            "فك الربط",
            "ترجّع هذي الحالة لمجلد Autre (شغل بلا زبون)؟\nالملفان ينتقلان فعلياً.",
        ):
            return
        try:
            move_case(row["id"], None)
        except Exception as exc:  # noqa: BLE001
            alerts.error("خطأ", f"تعذر نقل الحالة:\n{exc}")
            return
        self._refresh()
        self.cd_tab.explorer_panel.refresh()

    # ---------- إدارة الزبائن (بسيطة: قائمة + حذف بس) ----------
    def _open_clients_manager(self):
        _ClientsManager(self)
        self._refresh()

    def _reveal_in_sidebar(self):
        """يقفز بالشريط الجانبي لنفس الحالة ويحدّدها (بـrow_id مباشرة)،
        ثم يسكّر النافذة حتى تشوف الشريط محدَّثاً فوراً."""
        row = self._get_selected_row()
        if row is None:
            return
        self.cd_tab.explorer_panel.refresh()
        self.cd_tab.explorer_panel.reveal_row(row["id"])
        self.destroy()

    def _open_selected(self):
        row = self._get_selected_row()
        if row is None:
            return
        target = row.get("pdf_path") or row.get("file_path")
        if not open_path(target):
            alerts.error("خطأ", "الملف غير موجود (ربما نُقل أو حُذف).")

    def _load_selected_for_edit(self):
        """يحمّل بيانات المستند المحدَّد كاملة بتبويب جديد مستقل للمراجعة
        أو التعديل — بعدها لو حفظت من نفس التبويب، يحدّث فوق نفس الحالة
        (نفس السطر، نفس الملفين) بدل تسجيل حالة جديدة مكرّرة."""
        row = self._get_selected_row()
        if row is None:
            return
        data = deserialize_cd_data(row.get("full_data_json"))
        if data is None:
            alerts.info(
                "غير متاح",
                "هذا مستند قديم (قبل تفعيل حفظ كل بيانات الاستمارة)، فبياناته الكاملة غير محفوظة "
                "بالسجل — ما نقدر نرجّعه للاستمارة.\nتقدر تفتح الملف نفسه بس (📂 فتح الملف المحدَّد).",
            )
            return
        self.cd_tab._open_data_in_new_tab(
            data, source_row_id=row["id"], source_file_path=row.get("file_path"),
            source_pdf_path=row.get("pdf_path"), source_client_id=row.get("client_id"),
        )
        self.destroy()

    def _reprint_selected(self):
        """يطبع نسخة PDF الدائمة المحفوظة أصلاً للمستند، وإلا يولّد نسخة
        مؤقتة من البيانات الكاملة لو محفوظة، وإلا يطبع الملف الأصلي."""
        row = self._get_selected_row()
        if row is None:
            return
        if row.get("pdf_path") and os.path.exists(row["pdf_path"]):
            print_path = row["pdf_path"]
        else:
            data = deserialize_cd_data(row.get("full_data_json"))
            if data is not None:
                try:
                    print_path = generate_cd_pdf(
                        data, out_path=os.path.join(OUTPUT_DIR, "_print_tmp.pdf")
                    )
                except Exception as exc:  # noqa: BLE001
                    alerts.error("خطأ", f"تعذر تجهيز نسخة الطباعة (PDF):\n{exc}")
                    return
            else:
                print_path = row["file_path"]
                if not os.path.exists(print_path):
                    alerts.error("خطأ", "الملف غير موجود (ربما نُقل أو حُذف).")
                    return
        copies = simpledialog.askinteger(
            "إعادة طباعة", "عدد النسخ؟", initialvalue=1, minvalue=1, maxvalue=10, parent=self,
        )
        if not copies:
            return
        try:
            for _ in range(copies):
                os.startfile(print_path, "print")
        except OSError as exc:
            alerts.error("خطأ", f"تعذر إرسال الملف للطابعة:\n{exc}")


class _PickClientDialog(tk.Toplevel):
    """نافذة صغيرة: اختيار زبون (أو "＋ زبون جديد") لربط/تغيير الزبون.
    show() يرجّع client_id المختار، أو CANCEL لو أُلغيت."""

    CANCEL = object()

    def __init__(self, parent, initial=None):
        super().__init__(parent)
        self.title("اختيار الزبون")
        self.transient(parent)
        self.resizable(False, False)
        self._result = self.CANCEL

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="الزبون:").pack(side="top", anchor="w")
        self._picker = ClientPickerEntry(frm, entry_width=28)
        self._picker.pack(side="top", pady=(4, 10))
        if initial is not None:
            self._picker.set_client_id(initial)
        btns = ttk.Frame(frm)
        btns.pack(side="top", anchor="e")
        ttk.Button(btns, text="موافق", command=self._ok).pack(side="left")
        ttk.Button(btns, text="إلغاء", command=self._cancel).pack(side="left", padx=(6, 0))
        self.bind("<Escape>", lambda _e: self._cancel())
        self.grab_set()

    def _ok(self):
        cid = self._picker.get_client_id()
        if cid is None:
            alerts.error("خطأ", "اختر زبوناً من القائمة أولاً (أو ＋ زبون جديد).")
            return
        self._result = cid
        self.destroy()

    def _cancel(self):
        self._result = self.CANCEL
        self.destroy()

    def show(self):
        self.wait_window()
        return self._result


class _ClientsManager(tk.Toplevel):
    """نافذة صغيرة: قائمة الزبائن + حذف لكل صف. ⚠️ قرار تنفيذي: بسيطة
    (قائمة + حذف بس، بلا تعديل بيانات الزبون بهذا الإصدار) — كافية لسدّ
    بند 4-و بمستند التصميم (منع حذف زبون له مستندات، سماح لو فاضٍ)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("👥 إدارة الزبائن")
        self.geometry("420x360")
        self.transient(parent)
        self.grab_set()

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(frm, activestyle="none", font=("Segoe UI", 10))
        self.listbox.pack(fill="both", expand=True)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="🗑️ حذف المحدَّد", command=self._delete_selected).pack(side="left")
        ttk.Button(btns, text="إغلاق", command=self.destroy).pack(side="right")

        self._clients = []
        self._reload()

    def _reload(self):
        self._clients = list_clients()
        self.listbox.delete(0, tk.END)
        for c in self._clients:
            self.listbox.insert(tk.END, c["name"])

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        client = self._clients[sel[0]]
        if client_has_documents(client["id"]):
            alerts.error(
                "غير مسموح",
                f"الزبون \"{client['name']}\" عنده مستندات مرتبطة — ما يمكن حذفه.\n"
                "فكّ ربط كل مستنداته أولاً (من السجل: 🔓 فك الربط) ثم أعد المحاولة.",
            )
            return
        if not alerts.confirm("تأكيد الحذف", f"حذف الزبون \"{client['name']}\" نهائياً؟"):
            return
        if delete_client(client["id"]):
            self._reload()
        else:
            alerts.error("غير مسموح", "تعذر حذف الزبون (ربما صارت له مستندات الآن).")
