"""
تبويب إدارة المهام والمواعيد.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from database import get_connection


class TasksTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=15)
        self.app = app
        self.selected_id = None
        self.build()
        self.refresh()

    def build(self):
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)

        list_frame = ttk.Frame(main)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        filter_bar = ttk.Frame(list_frame)
        filter_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(filter_bar, text="عرض:").pack(side="left")
        self.filter_var = tk.StringVar(value="الكل")
        filter_combo = ttk.Combobox(
            filter_bar, textvariable=self.filter_var,
            values=["الكل", "قيد الانتظار", "مكتملة"], state="readonly", width=15,
        )
        filter_combo.pack(side="left", padx=5)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        columns = ("title", "due_date", "due_time", "priority", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=20)
        for col, text in zip(columns, ["العنوان", "التاريخ", "الوقت", "الأولوية", "الحالة"]):
            self.tree.heading(col, text=text)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        form = ttk.LabelFrame(main, text="بيانات المهمة", padding=15)
        form.pack(side="left", fill="y")

        self.title_var = tk.StringVar()
        self.due_date_var = tk.StringVar()
        self.due_time_var = tk.StringVar()
        self.priority_var = tk.StringVar(value="عادية")
        self.status_var = tk.StringVar(value="قيد الانتظار")

        ttk.Label(form, text="العنوان *").pack(anchor="w")
        ttk.Entry(form, textvariable=self.title_var, width=32).pack(anchor="w")

        ttk.Label(form, text="الوصف").pack(anchor="w", pady=(6, 0))
        self.desc_text = tk.Text(form, width=32, height=4)
        self.desc_text.pack(anchor="w")

        ttk.Label(form, text="التاريخ (YYYY-MM-DD)").pack(anchor="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.due_date_var, width=32).pack(anchor="w")

        ttk.Label(form, text="الوقت (HH:MM)").pack(anchor="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.due_time_var, width=32).pack(anchor="w")

        ttk.Label(form, text="الأولوية").pack(anchor="w", pady=(6, 0))
        ttk.Combobox(
            form, textvariable=self.priority_var,
            values=["منخفضة", "عادية", "عالية"], state="readonly", width=29,
        ).pack(anchor="w")

        ttk.Label(form, text="الحالة").pack(anchor="w", pady=(6, 0))
        ttk.Combobox(
            form, textvariable=self.status_var,
            values=["قيد الانتظار", "قيد التنفيذ", "مكتملة"], state="readonly", width=29,
        ).pack(anchor="w")

        btns = ttk.Frame(form)
        btns.pack(fill="x", pady=15)
        ttk.Button(btns, text="إضافة", command=self.save).pack(fill="x", pady=2)
        ttk.Button(btns, text="تعديل المحدد", command=self.update_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="تحديد كمكتملة", command=self.mark_done).pack(fill="x", pady=2)
        ttk.Button(btns, text="حذف المحدد", command=self.delete_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="تفريغ الحقول", command=self.clear_form).pack(fill="x", pady=2)

    def clear_form(self):
        self.selected_id = None
        self.title_var.set("")
        self.desc_text.delete("1.0", "end")
        self.due_date_var.set("")
        self.due_time_var.set("")
        self.priority_var.set("عادية")
        self.status_var.set("قيد الانتظار")

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        task_id = int(self.tree.item(sel[0], "tags")[0])
        self.selected_id = task_id
        conn = get_connection()
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        conn.close()
        if row:
            self.title_var.set(row["title"] or "")
            self.desc_text.delete("1.0", "end")
            self.desc_text.insert("1.0", row["description"] or "")
            self.due_date_var.set(row["due_date"] or "")
            self.due_time_var.set(row["due_time"] or "")
            self.priority_var.set(row["priority"] or "عادية")
            self.status_var.set(row["status"] or "قيد الانتظار")

    def save(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("تنبيه", "العنوان مطلوب")
            return
        conn = get_connection()
        conn.execute(
            "INSERT INTO tasks (title, description, due_date, due_time, priority, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                title,
                self.desc_text.get("1.0", "end").strip(),
                self.due_date_var.get().strip(),
                self.due_time_var.get().strip(),
                self.priority_var.get(),
                self.status_var.get(),
            ),
        )
        conn.commit()
        conn.close()
        self.clear_form()
        self.refresh()

    def update_selected(self):
        if not self.selected_id:
            messagebox.showwarning("تنبيه", "اختر مهمة من القائمة أولاً")
            return
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("تنبيه", "العنوان مطلوب")
            return
        conn = get_connection()
        conn.execute(
            "UPDATE tasks SET title=?, description=?, due_date=?, due_time=?, priority=?, status=? WHERE id=?",
            (
                title,
                self.desc_text.get("1.0", "end").strip(),
                self.due_date_var.get().strip(),
                self.due_time_var.get().strip(),
                self.priority_var.get(),
                self.status_var.get(),
                self.selected_id,
            ),
        )
        conn.commit()
        conn.close()
        self.clear_form()
        self.refresh()

    def mark_done(self):
        if not self.selected_id:
            messagebox.showwarning("تنبيه", "اختر مهمة من القائمة أولاً")
            return
        conn = get_connection()
        conn.execute("UPDATE tasks SET status='مكتملة' WHERE id=?", (self.selected_id,))
        conn.commit()
        conn.close()
        self.clear_form()
        self.refresh()

    def delete_selected(self):
        if not self.selected_id:
            messagebox.showwarning("تنبيه", "اختر مهمة من القائمة أولاً")
            return
        if not messagebox.askyesno("تأكيد", "هل تريد حذف هذه المهمة؟"):
            return
        conn = get_connection()
        conn.execute("DELETE FROM tasks WHERE id=?", (self.selected_id,))
        conn.commit()
        conn.close()
        self.clear_form()
        self.refresh()

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        conn = get_connection()
        query = "SELECT * FROM tasks"
        f = self.filter_var.get()
        if f == "قيد الانتظار":
            query += " WHERE status != 'مكتملة'"
        elif f == "مكتملة":
            query += " WHERE status = 'مكتملة'"
        query += " ORDER BY (due_date IS NULL OR due_date = ''), due_date, due_time"
        for row in conn.execute(query).fetchall():
            self.tree.insert(
                "",
                "end",
                values=(row["title"], row["due_date"], row["due_time"], row["priority"], row["status"]),
                tags=(str(row["id"]),),
            )
        conn.close()
