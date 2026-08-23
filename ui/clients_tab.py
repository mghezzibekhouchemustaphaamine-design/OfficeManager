"""
تبويب إدارة العملاء: إضافة، تعديل، حذف، بحث.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from database import get_connection


class ClientsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=15)
        self.app = app
        self.selected_id = None
        self.build()
        self.refresh()

    def build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="بحث:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh())
        ttk.Entry(top, textvariable=self.search_var, width=30).pack(side="left", padx=5)

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)

        list_frame = ttk.Frame(main)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        columns = ("name", "phone", "email", "address")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=20)
        for col, text in zip(columns, ["الاسم", "الهاتف", "البريد الإلكتروني", "العنوان"]):
            self.tree.heading(col, text=text)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.LabelFrame(main, text="بيانات العميل", padding=15)
        form.pack(side="left", fill="y")

        self.name_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.address_var = tk.StringVar()

        for label, var in [
            ("الاسم *", self.name_var),
            ("الهاتف", self.phone_var),
            ("البريد الإلكتروني", self.email_var),
            ("العنوان", self.address_var),
        ]:
            ttk.Label(form, text=label).pack(anchor="w", pady=(6, 0))
            ttk.Entry(form, textvariable=var, width=32).pack(anchor="w")

        ttk.Label(form, text="ملاحظات").pack(anchor="w", pady=(6, 0))
        self.notes_text = tk.Text(form, width=32, height=5)
        self.notes_text.pack(anchor="w")

        btns = ttk.Frame(form)
        btns.pack(fill="x", pady=15)
        ttk.Button(btns, text="حفظ / إضافة", command=self.save).pack(fill="x", pady=2)
        ttk.Button(btns, text="تعديل المحدد", command=self.update_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="حذف المحدد", command=self.delete_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="تفريغ الحقول", command=self.clear_form).pack(fill="x", pady=2)

    def clear_form(self):
        self.selected_id = None
        self.name_var.set("")
        self.phone_var.set("")
        self.email_var.set("")
        self.address_var.set("")
        self.notes_text.delete("1.0", "end")

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        client_id = int(self.tree.item(sel[0], "tags")[0])
        self.selected_id = client_id
        conn = get_connection()
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        conn.close()
        if row:
            self.name_var.set(row["name"] or "")
            self.phone_var.set(row["phone"] or "")
            self.email_var.set(row["email"] or "")
            self.address_var.set(row["address"] or "")
            self.notes_text.delete("1.0", "end")
            self.notes_text.insert("1.0", row["notes"] or "")

    def save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("تنبيه", "الاسم مطلوب")
            return
        conn = get_connection()
        conn.execute(
            "INSERT INTO clients (name, phone, email, address, notes) VALUES (?, ?, ?, ?, ?)",
            (
                name,
                self.phone_var.get().strip(),
                self.email_var.get().strip(),
                self.address_var.get().strip(),
                self.notes_text.get("1.0", "end").strip(),
            ),
        )
        conn.commit()
        conn.close()
        self.clear_form()
        self.refresh()

    def update_selected(self):
        if not self.selected_id:
            messagebox.showwarning("تنبيه", "اختر عميلاً من القائمة أولاً")
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("تنبيه", "الاسم مطلوب")
            return
        conn = get_connection()
        conn.execute(
            "UPDATE clients SET name=?, phone=?, email=?, address=?, notes=? WHERE id=?",
            (
                name,
                self.phone_var.get().strip(),
                self.email_var.get().strip(),
                self.address_var.get().strip(),
                self.notes_text.get("1.0", "end").strip(),
                self.selected_id,
            ),
        )
        conn.commit()
        conn.close()
        self.clear_form()
        self.refresh()

    def delete_selected(self):
        if not self.selected_id:
            messagebox.showwarning("تنبيه", "اختر عميلاً من القائمة أولاً")
            return
        if not messagebox.askyesno("تأكيد", "هل أنت متأكد من حذف هذا العميل؟"):
            return
        conn = get_connection()
        conn.execute("DELETE FROM clients WHERE id=?", (self.selected_id,))
        conn.commit()
        conn.close()
        self.clear_form()
        self.refresh()

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        conn = get_connection()
        query = "SELECT * FROM clients"
        params = ()
        term = self.search_var.get().strip()
        if term:
            query += " WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?"
            like = f"%{term}%"
            params = (like, like, like)
        query += " ORDER BY name"
        for row in conn.execute(query, params).fetchall():
            self.tree.insert(
                "",
                "end",
                values=(row["name"], row["phone"], row["email"], row["address"]),
                tags=(str(row["id"]),),
            )
        conn.close()
