"""
تبويب إدارة الفواتير: قائمة الفواتير + نافذة منبثقة لإنشاء/تعديل فاتورة ببنودها.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date

from database import get_connection
from utils import generate_invoice_number, export_rows_to_csv


class InvoiceDialog(tk.Toplevel):
    def __init__(self, parent, app, invoice_id=None):
        super().__init__(parent)
        self.app = app
        self.invoice_id = invoice_id
        self.title("فاتورة جديدة" if invoice_id is None else "تعديل فاتورة")
        self.geometry("650x600")
        self.grab_set()
        self.items = []  # كل عنصر: description, quantity, unit_price
        self.build()
        if invoice_id:
            self.load_invoice()

    def build(self):
        top = ttk.Frame(self, padding=15)
        top.pack(fill="x")

        ttk.Label(top, text="العميل").grid(row=0, column=0, sticky="w")
        conn = get_connection()
        self.clients = conn.execute("SELECT id, name FROM clients ORDER BY name").fetchall()
        conn.close()
        self.client_var = tk.StringVar()
        self.client_combo = ttk.Combobox(
            top, textvariable=self.client_var,
            values=[c["name"] for c in self.clients], state="readonly", width=30,
        )
        self.client_combo.grid(row=0, column=1, sticky="w", padx=5, pady=3)

        ttk.Label(top, text="تاريخ الفاتورة (YYYY-MM-DD)").grid(row=1, column=0, sticky="w")
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(top, textvariable=self.date_var, width=20).grid(row=1, column=1, sticky="w", padx=5, pady=3)

        ttk.Label(top, text="تاريخ الاستحقاق (YYYY-MM-DD)").grid(row=2, column=0, sticky="w")
        self.due_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.due_var, width=20).grid(row=2, column=1, sticky="w", padx=5, pady=3)

        ttk.Label(top, text="الحالة").grid(row=3, column=0, sticky="w")
        self.status_var = tk.StringVar(value="غير مدفوعة")
        ttk.Combobox(
            top, textvariable=self.status_var,
            values=["غير مدفوعة", "مدفوعة", "متأخرة"], state="readonly", width=18,
        ).grid(row=3, column=1, sticky="w", padx=5, pady=3)

        items_frame = ttk.LabelFrame(self, text="بنود الفاتورة", padding=10)
        items_frame.pack(fill="both", expand=True, padx=15, pady=10)

        cols = ("description", "quantity", "unit_price", "total")
        self.items_tree = ttk.Treeview(items_frame, columns=cols, show="headings", height=8)
        for col, text in zip(cols, ["الوصف", "الكمية", "سعر الوحدة", "الإجمالي"]):
            self.items_tree.heading(col, text=text)
        self.items_tree.pack(fill="both", expand=True)

        add_frame = ttk.Frame(items_frame)
        add_frame.pack(fill="x", pady=8)
        self.desc_var = tk.StringVar()
        self.qty_var = tk.StringVar(value="1")
        self.price_var = tk.StringVar(value="0")
        ttk.Entry(add_frame, textvariable=self.desc_var, width=25).pack(side="left", padx=2)
        ttk.Entry(add_frame, textvariable=self.qty_var, width=8).pack(side="left", padx=2)
        ttk.Entry(add_frame, textvariable=self.price_var, width=10).pack(side="left", padx=2)
        ttk.Button(add_frame, text="إضافة بند", command=self.add_item).pack(side="left", padx=5)
        ttk.Button(add_frame, text="حذف البند المحدد", command=self.remove_item).pack(side="left", padx=5)

        self.total_label = ttk.Label(items_frame, text="الإجمالي: 0.00", font=("Segoe UI", 12, "bold"))
        self.total_label.pack(anchor="e", pady=5)

        bottom = ttk.Frame(self, padding=15)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="حفظ الفاتورة", command=self.save).pack(side="right")
        ttk.Button(bottom, text="إلغاء", command=self.destroy).pack(side="right", padx=8)

    def add_item(self):
        desc = self.desc_var.get().strip()
        if not desc:
            messagebox.showwarning("تنبيه", "أدخل وصف البند")
            return
        try:
            qty = float(self.qty_var.get())
            price = float(self.price_var.get())
        except ValueError:
            messagebox.showwarning("تنبيه", "الكمية والسعر يجب أن يكونا أرقاماً")
            return
        self.items.append({"description": desc, "quantity": qty, "unit_price": price})
        self.items_tree.insert("", "end", values=(desc, qty, price, f"{qty * price:.2f}"))
        self.desc_var.set("")
        self.qty_var.set("1")
        self.price_var.set("0")
        self.update_total()

    def remove_item(self):
        sel = self.items_tree.selection()
        if not sel:
            return
        idx = self.items_tree.index(sel[0])
        self.items_tree.delete(sel[0])
        del self.items[idx]
        self.update_total()

    def update_total(self):
        total = sum(i["quantity"] * i["unit_price"] for i in self.items)
        self.total_label.config(text=f"الإجمالي: {total:,.2f}")

    def load_invoice(self):
        conn = get_connection()
        inv = conn.execute("SELECT * FROM invoices WHERE id=?", (self.invoice_id,)).fetchone()
        if inv:
            client = conn.execute("SELECT name FROM clients WHERE id=?", (inv["client_id"],)).fetchone()
            if client:
                self.client_var.set(client["name"])
            self.date_var.set(inv["date"] or "")
            self.due_var.set(inv["due_date"] or "")
            self.status_var.set(inv["status"] or "غير مدفوعة")
        for it in conn.execute("SELECT * FROM invoice_items WHERE invoice_id=?", (self.invoice_id,)).fetchall():
            self.items.append(
                {"description": it["description"], "quantity": it["quantity"], "unit_price": it["unit_price"]}
            )
            self.items_tree.insert(
                "", "end",
                values=(it["description"], it["quantity"], it["unit_price"], f"{it['quantity'] * it['unit_price']:.2f}"),
            )
        conn.close()
        self.update_total()

    def save(self):
        client_name = self.client_var.get()
        if not client_name:
            messagebox.showwarning("تنبيه", "اختر عميلاً")
            return
        if not self.items:
            messagebox.showwarning("تنبيه", "أضف بنداً واحداً على الأقل")
            return
        client_id = next((c["id"] for c in self.clients if c["name"] == client_name), None)
        conn = get_connection()
        try:
            if self.invoice_id is None:
                number = generate_invoice_number(conn)
                cur = conn.execute(
                    "INSERT INTO invoices (invoice_number, client_id, date, due_date, status) VALUES (?, ?, ?, ?, ?)",
                    (number, client_id, self.date_var.get().strip(), self.due_var.get().strip(), self.status_var.get()),
                )
                invoice_id = cur.lastrowid
            else:
                invoice_id = self.invoice_id
                conn.execute(
                    "UPDATE invoices SET client_id=?, date=?, due_date=?, status=? WHERE id=?",
                    (client_id, self.date_var.get().strip(), self.due_var.get().strip(), self.status_var.get(), invoice_id),
                )
                conn.execute("DELETE FROM invoice_items WHERE invoice_id=?", (invoice_id,))
            for item in self.items:
                conn.execute(
                    "INSERT INTO invoice_items (invoice_id, description, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (invoice_id, item["description"], item["quantity"], item["unit_price"]),
                )
            conn.commit()
        finally:
            conn.close()
        self.app.invoices_tab.refresh()
        self.app.dashboard_tab.refresh()
        self.destroy()


class InvoicesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=15)
        self.app = app
        self.build()

    def build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="+ فاتورة جديدة", command=self.new_invoice).pack(side="left")
        ttk.Button(top, text="تعديل", command=self.edit_invoice).pack(side="left", padx=5)
        ttk.Button(top, text="تحديد كمدفوعة", command=self.mark_paid).pack(side="left", padx=5)
        ttk.Button(top, text="حذف", command=self.delete_invoice).pack(side="left", padx=5)
        ttk.Button(top, text="تصدير CSV", command=self.export_csv).pack(side="left", padx=5)

        columns = ("number", "client", "date", "due", "status", "total")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=22)
        for col, text in zip(columns, ["رقم الفاتورة", "العميل", "التاريخ", "الاستحقاق", "الحالة", "الإجمالي"]):
            self.tree.heading(col, text=text)
        self.tree.pack(fill="both", expand=True)
        self.refresh()

    def new_invoice(self):
        InvoiceDialog(self, self.app)

    def get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "اختر فاتورة من القائمة")
            return None
        return int(self.tree.item(sel[0], "tags")[0])

    def edit_invoice(self):
        invoice_id = self.get_selected_id()
        if invoice_id:
            InvoiceDialog(self, self.app, invoice_id=invoice_id)

    def mark_paid(self):
        invoice_id = self.get_selected_id()
        if not invoice_id:
            return
        conn = get_connection()
        conn.execute("UPDATE invoices SET status='مدفوعة' WHERE id=?", (invoice_id,))
        conn.commit()
        conn.close()
        self.refresh()
        self.app.dashboard_tab.refresh()

    def delete_invoice(self):
        invoice_id = self.get_selected_id()
        if not invoice_id:
            return
        if not messagebox.askyesno("تأكيد", "هل تريد حذف هذه الفاتورة؟"):
            return
        conn = get_connection()
        conn.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
        conn.commit()
        conn.close()
        self.refresh()
        self.app.dashboard_tab.refresh()

    def export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT i.invoice_number, COALESCE(c.name,''), i.date, i.due_date, i.status,
                   COALESCE((SELECT SUM(quantity*unit_price) FROM invoice_items WHERE invoice_id=i.id), 0)
            FROM invoices i LEFT JOIN clients c ON c.id = i.client_id
            ORDER BY i.date DESC
            """
        ).fetchall()
        conn.close()
        export_rows_to_csv(
            [tuple(r) for r in rows],
            ["رقم الفاتورة", "العميل", "التاريخ", "الاستحقاق", "الحالة", "الإجمالي"],
            path,
        )
        messagebox.showinfo("تم", "تم تصدير البيانات بنجاح")

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT i.id, i.invoice_number, COALESCE(c.name,'-') as client_name, i.date, i.due_date, i.status,
                   COALESCE((SELECT SUM(quantity*unit_price) FROM invoice_items WHERE invoice_id=i.id), 0) as total
            FROM invoices i LEFT JOIN clients c ON c.id = i.client_id
            ORDER BY i.date DESC
            """
        ).fetchall()
        conn.close()
        for row in rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["invoice_number"],
                    row["client_name"],
                    row["date"],
                    row["due_date"],
                    row["status"],
                    f"{row['total']:,.2f}",
                ),
                tags=(str(row["id"]),),
            )
