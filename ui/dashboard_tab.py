"""
تبويب اللوحة الرئيسية: نظرة عامة سريعة على العملاء، الفواتير غير المدفوعة، والمهام.
"""
import tkinter as tk
from tkinter import ttk
from datetime import date

from database import get_connection


class DashboardTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=20)
        self.app = app
        self.build()

    def build(self):
        title = ttk.Label(self, text="نظرة عامة", font=("Segoe UI", 16, "bold"))
        title.pack(anchor="w", pady=(0, 15))

        self.cards_frame = ttk.Frame(self)
        self.cards_frame.pack(fill="x")

        self.card_labels = {}
        cards = [
            ("clients", "👥 عدد العملاء"),
            ("unpaid", "🧾 فواتير غير مدفوعة"),
            ("unpaid_total", "💰 إجمالي المستحقات"),
            ("tasks_pending", "✅ مهام قيد الانتظار"),
            ("tasks_today", "📅 مهام اليوم"),
        ]
        for i, (key, label) in enumerate(cards):
            card = ttk.Frame(self.cards_frame, relief="groove", borderwidth=1, padding=15)
            card.grid(row=0, column=i, padx=8, sticky="nsew")
            self.cards_frame.grid_columnconfigure(i, weight=1)
            ttk.Label(card, text=label, font=("Segoe UI", 10)).pack(anchor="w")
            value_lbl = ttk.Label(card, text="0", font=("Segoe UI", 20, "bold"))
            value_lbl.pack(anchor="w", pady=(6, 0))
            self.card_labels[key] = value_lbl

        ttk.Separator(self).pack(fill="x", pady=20)

        ttk.Label(self, text="أقرب المهام غير المكتملة", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        columns = ("title", "due_date", "due_time", "status")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=12)
        for col, text in zip(columns, ["العنوان", "التاريخ", "الوقت", "الحالة"]):
            self.tree.heading(col, text=text)
            self.tree.column(col, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=10)

        self.refresh()

    def refresh(self):
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM clients")
        self.card_labels["clients"].config(text=str(cur.fetchone()[0]))

        cur.execute("SELECT COUNT(*) FROM invoices WHERE status != 'مدفوعة'")
        self.card_labels["unpaid"].config(text=str(cur.fetchone()[0]))

        cur.execute(
            """
            SELECT COALESCE(SUM(ii.quantity * ii.unit_price), 0)
            FROM invoices i
            JOIN invoice_items ii ON ii.invoice_id = i.id
            WHERE i.status != 'مدفوعة'
            """
        )
        total = cur.fetchone()[0] or 0
        self.card_labels["unpaid_total"].config(text=f"{total:,.2f}")

        cur.execute("SELECT COUNT(*) FROM tasks WHERE status != 'مكتملة'")
        self.card_labels["tasks_pending"].config(text=str(cur.fetchone()[0]))

        today = date.today().isoformat()
        cur.execute("SELECT COUNT(*) FROM tasks WHERE due_date = ? AND status != 'مكتملة'", (today,))
        self.card_labels["tasks_today"].config(text=str(cur.fetchone()[0]))

        for row in self.tree.get_children():
            self.tree.delete(row)
        cur.execute(
            """
            SELECT title, due_date, due_time, status FROM tasks
            WHERE status != 'مكتملة' AND due_date IS NOT NULL AND due_date != ''
            ORDER BY due_date ASC, due_time ASC LIMIT 20
            """
        )
        for row in cur.fetchall():
            self.tree.insert("", "end", values=tuple(row))

        conn.close()
