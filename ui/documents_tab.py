"""
تبويب إدارة المستندات: ربط ملفات موجودة على الجهاز بعملاء وتصنيفات، وفتحها مباشرة.
"""
import tkinter as tk
from tkinter import ttk, filedialog

from ui.common import alerts

from programme.database import get_connection
from programme.utils import open_path


class DocumentsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=15)
        self.app = app
        self.build()
        self.refresh()

    def build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="+ إضافة مستند", command=self.add_document).pack(side="left")
        ttk.Button(top, text="فتح المحدد", command=self.open_selected).pack(side="left", padx=5)
        ttk.Button(top, text="حذف المحدد", command=self.delete_selected).pack(side="left", padx=5)

        ttk.Label(top, text="بحث:").pack(side="left", padx=(20, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(top, textvariable=self.search_var, width=25).pack(side="left", padx=5)

        columns = ("title", "category", "client", "path")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=22)
        for col, text in zip(columns, ["العنوان", "التصنيف", "العميل", "المسار"]):
            self.tree.heading(col, text=text)
        self.tree.column("path", width=320)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.open_selected())

    def add_document(self):
        path = filedialog.askopenfilename(title="اختر ملفاً")
        if not path:
            return

        dialog = tk.Toplevel(self)
        dialog.title("إضافة مستند")
        dialog.geometry("400x340")
        dialog.grab_set()

        default_title = path.replace("\\", "/").split("/")[-1]

        ttk.Label(dialog, text="العنوان").pack(anchor="w", padx=15, pady=(15, 0))
        title_var = tk.StringVar(value=default_title)
        ttk.Entry(dialog, textvariable=title_var, width=40).pack(padx=15)

        ttk.Label(dialog, text="التصنيف").pack(anchor="w", padx=15, pady=(10, 0))
        category_var = tk.StringVar()
        ttk.Combobox(
            dialog, textvariable=category_var,
            values=["عقود", "فواتير", "مراسلات", "تقارير", "أخرى"], width=37,
        ).pack(padx=15)

        conn = get_connection()
        clients = conn.execute("SELECT id, name FROM clients ORDER BY name").fetchall()
        conn.close()
        ttk.Label(dialog, text="العميل (اختياري)").pack(anchor="w", padx=15, pady=(10, 0))
        client_var = tk.StringVar()
        ttk.Combobox(dialog, textvariable=client_var, values=[c["name"] for c in clients], width=37).pack(padx=15)

        ttk.Label(dialog, text=f"المسار: {path}", wraplength=360, foreground="#555").pack(
            anchor="w", padx=15, pady=(15, 0)
        )

        def save():
            client_id = next((c["id"] for c in clients if c["name"] == client_var.get()), None)
            conn = get_connection()
            conn.execute(
                "INSERT INTO documents (title, file_path, category, client_id) VALUES (?, ?, ?, ?)",
                (title_var.get().strip() or default_title, path, category_var.get().strip(), client_id),
            )
            conn.commit()
            conn.close()
            dialog.destroy()
            self.refresh()

        ttk.Button(dialog, text="حفظ", command=save).pack(pady=20)

    def get_selected(self):
        sel = self.tree.selection()
        if not sel:
            return None, None
        doc_id = int(self.tree.item(sel[0], "tags")[0])
        values = self.tree.item(sel[0], "values")
        return doc_id, values[3]

    def open_selected(self):
        doc_id, path = self.get_selected()
        if not doc_id:
            alerts.warning("تنبيه", "اختر مستنداً من القائمة")
            return
        if not open_path(path):
            alerts.error("خطأ", "تعذر العثور على الملف في مساره الأصلي")

    def delete_selected(self):
        doc_id, _ = self.get_selected()
        if not doc_id:
            alerts.warning("تنبيه", "اختر مستنداً من القائمة")
            return
        if not alerts.confirm_always("تأكيد", "هل تريد حذف هذا السجل (لن يُحذف الملف الأصلي)؟"):
            return
        conn = get_connection()
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        conn.commit()
        conn.close()
        self.refresh()

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        conn = get_connection()
        query = """
            SELECT d.id, d.title, d.category, COALESCE(c.name, '-') as client_name, d.file_path
            FROM documents d LEFT JOIN clients c ON c.id = d.client_id
        """
        params = ()
        term = self.search_var.get().strip()
        if term:
            query += " WHERE d.title LIKE ? OR d.category LIKE ?"
            like = f"%{term}%"
            params = (like, like)
        query += " ORDER BY d.added_at DESC"
        for row in conn.execute(query, params).fetchall():
            self.tree.insert(
                "",
                "end",
                values=(row["title"], row["category"], row["client_name"], row["file_path"]),
                tags=(str(row["id"]),),
            )
        conn.close()
