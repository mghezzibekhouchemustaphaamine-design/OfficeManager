"""مكوّن اختيار زبون مشترك — خانة بحث بالاسم + قائمة نتائج حية منسدلة +
زر "＋ زبون جديد". يُستخدم بمكانين بلا تكرار بناءه: خانة الزبون باستمارة
CD (ui/cd/tab.py)، ونافذة السجل (ui/cd/history.py — فلتر + ربط).

عام تماماً — يعتمد بس على programme.database (list_clients/get_client/
create_client) وui.common.alerts، بلا أي معرفة بـtab.py أو أي شاشة
معيّنة (نفس فلسفة FileExplorerPanel).

get_client_id() يرجّع None لو ما فيه زبون **مُختار فعلياً** من القائمة —
نص مكتوب يدوياً بلا اختيار لا يُحتسب، لأن الفلترة/الربط يشتغلان بالمعرّف
(client_id) لا بمطابقة نص الاسم (حتى ما يلتبس زبونين بنفس الاسم — راجع
بند 4-ب بمستند التصميم)."""
import tkinter as tk
from tkinter import ttk

from ui.common import alerts
from programme.database import list_clients, get_client, create_client


class ClientPickerEntry(ttk.Frame):
    def __init__(self, parent, on_change=None, entry_width=22):
        super().__init__(parent)
        self._on_change = on_change
        self._client_id = None
        self._popup = None
        self._listbox = None
        self._results = []
        self._suppress_search = False  # يوقف البحث الحي وقت التعبئة البرمجية
        self._selected_text = ""  # آخر نص مطابق فعلياً لـ_client_id (راجع _on_key_release)

        self.entry_var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.entry_var, width=entry_width)
        self.entry.pack(side="left")
        self._add_btn = ttk.Button(self, text="＋", width=3, command=self._add_new_client)
        self._add_btn.pack(side="left", padx=(2, 0))

        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<FocusOut>", lambda _e: self.after(150, self._maybe_hide_popup))
        self.entry.bind("<Down>", self._focus_popup)
        self.entry.bind("<Escape>", lambda _e: self._hide_popup())

    # ---------- واجهة عامة ----------
    def get_client_id(self):
        return self._client_id

    def set_client_id(self, client_id):
        """تعبئة برمجية (تحميل حالة محفوظة) — بلا إطلاق بحث حي ولا
        on_change (المتصل هو اللي يعرف إنه بدّلها)."""
        self._hide_popup()
        self._suppress_search = True
        try:
            client = get_client(client_id) if client_id is not None else None
            if client is None:
                self._client_id = None
                self.entry_var.set("")
            else:
                self._client_id = client_id
                self.entry_var.set(client["name"])
            self._selected_text = self.entry_var.get()
        finally:
            self._suppress_search = False

    def clear(self):
        self.set_client_id(None)

    def set_state(self, state):
        """'normal'/'readonly'/'disabled' — لمتابعة قفل الاستمارة
        (set_form_readonly بـtab.py)."""
        locked = state in ("readonly", "disabled")
        try:
            self.entry.configure(state=state)
        except tk.TclError:
            pass
        self._add_btn.configure(state="disabled" if locked else "normal")
        if locked:
            self._hide_popup()

    # ---------- بحث حي ----------
    def _on_key_release(self, event):
        if self._suppress_search or event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        # مفاتيح تنقّل/تعديل بلا أي تغيير فعلي بالنص (أسهم، Home/End،
        # رفع إصبع عن Shift/Ctrl/Alt لوحدهم...) ما تلغي الاختيار — بس
        # تغيّر النص فعلاً يعتبر "كتابة يدوية". هيك لو زبون مُختار
        # وضغط المستخدم سهم أو Ctrl+A يراجع الاسم، الربط ما ينفك بصمت
        # (كان القديم بيلغي الاختيار لأي KeyRelease مو بالقائمة
        # المستثناة فوق — حتى بلا تغيّر حرف وحد).
        current_text = self.entry_var.get()
        if self._client_id is not None and current_text == self._selected_text:
            return
        # أي كتابة يدوية غيّرت النص فعلاً تبطل أي اختيار سابق — لازم يعيد الاختيار من القائمة.
        if self._client_id is not None:
            self._client_id = None
            self._notify_change()
        self._results = list_clients(current_text.strip())
        self._show_popup()

    def _show_popup(self):
        if not self._results:
            self._hide_popup()
            return
        if self._popup is None:
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            try:
                self._popup.attributes("-topmost", True)
            except tk.TclError:
                pass
            self._listbox = tk.Listbox(
                self._popup, activestyle="none", exportselection=False, font=("Segoe UI", 9),
            )
            self._listbox.pack(fill="both", expand=True)
            self._listbox.bind("<ButtonRelease-1>", lambda _e: self._pick_from_listbox())
            self._listbox.bind("<Return>", lambda _e: self._pick_from_listbox())
            self._listbox.bind("<Escape>", lambda _e: (self._hide_popup(), self.entry.focus_set()))
        self._listbox.delete(0, tk.END)
        for c in self._results:
            label = c["name"]
            if c.get("phone"):
                label += f"  ({c['phone']})"
            self._listbox.insert(tk.END, label)
        self._listbox.configure(height=min(len(self._results), 6))
        self.entry.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        w = max(self.entry.winfo_width(), 160)
        self._listbox.update_idletasks()
        self._popup.wm_geometry(f"{w}x{self._listbox.winfo_reqheight()}+{x}+{y}")
        self._popup.deiconify()

    def _focus_popup(self, _event=None):
        if self._listbox is not None:
            self._listbox.focus_set()
            if self._listbox.size():
                self._listbox.selection_clear(0, tk.END)
                self._listbox.selection_set(0)
                self._listbox.activate(0)
        return "break"

    def _pick_from_listbox(self):
        if self._listbox is None:
            return
        sel = self._listbox.curselection()
        if not sel:
            return
        self._select_client(self._results[sel[0]])

    def _select_client(self, client):
        self._suppress_search = True
        try:
            self._client_id = client["id"]
            self.entry_var.set(client["name"])
            self.entry.icursor(tk.END)
            self._selected_text = self.entry_var.get()
        finally:
            self._suppress_search = False
        self._hide_popup()
        self.entry.focus_set()
        self._notify_change()

    def _maybe_hide_popup(self):
        # ما نخفي لو التركيز راح للقائمة نفسها (المستخدم عم يختار منها).
        focused = self.focus_get()
        if focused is not None and self._popup is not None and str(focused).startswith(str(self._popup)):
            return
        self._hide_popup()

    def _hide_popup(self):
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
            self._listbox = None

    def _notify_change(self):
        if self._on_change is not None:
            self._on_change()

    # ---------- ＋ زبون جديد ----------
    def _add_new_client(self):
        dlg = _NewClientDialog(self)
        self.wait_window(dlg)
        if dlg.created_id is not None:
            client = get_client(dlg.created_id)
            if client is not None:
                self._select_client(client)


class _NewClientDialog(tk.Toplevel):
    """نافذة صغيرة: اسم إجباري + هاتف/إيميل/عنوان/ملاحظات اختيارية →
    create_client → created_id (يقرأه المستدعي بعد wait_window)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("＋ زبون جديد")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.created_id = None

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        frm.grid_columnconfigure(1, weight=1)
        self._vars = {}
        rows = [
            ("name", "الاسم *"), ("phone", "الهاتف"), ("email", "الإيميل"),
            ("address", "العنوان"), ("notes", "ملاحظات"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="e", padx=(0, 8), pady=3)
            var = tk.StringVar()
            self._vars[key] = var
            ent = ttk.Entry(frm, textvariable=var, width=30)
            ent.grid(row=i, column=1, sticky="ew", pady=3)
            if i == 0:
                ent.focus_set()
        btns = ttk.Frame(frm)
        btns.grid(row=len(rows), column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(btns, text="حفظ", command=self._save).pack(side="left")
        ttk.Button(btns, text="إلغاء", command=self.destroy).pack(side="left", padx=(6, 0))
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _save(self):
        name = self._vars["name"].get().strip()
        if not name:
            alerts.error("خطأ", "اسم الزبون إجباري.")
            return
        self.created_id = create_client(
            name,
            phone=self._vars["phone"].get().strip() or None,
            email=self._vars["email"].get().strip() or None,
            address=self._vars["address"].get().strip() or None,
            notes=self._vars["notes"].get().strip() or None,
        )
        self.destroy()
