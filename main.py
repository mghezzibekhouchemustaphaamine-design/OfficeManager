"""
نظام إدارة الأعمال المكتبية - نقطة تشغيل البرنامج.

تشغيل البرنامج:
    python main.py
"""
import tkinter as tk
from tkinter import ttk

from database import init_db
from ui.dossier_tab import DossierTab
from ui.cd_tab import CDTab


class OfficeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("نظام إدارة الأعمال المكتبية")
        self.geometry("900x600")
        self.minsize(700, 500)

        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))

        self.body = ttk.Frame(self, padding=20)
        self.body.pack(fill="both", expand=True)

        self.show_home()

    def clear_body(self):
        for widget in self.body.winfo_children():
            widget.destroy()

    # ---------- الشاشة الرئيسية: قائمة الخدمات ----------
    def show_home(self):
        self.clear_body()
        container = ttk.Frame(self.body)
        container.place(relx=0.5, rely=0.4, anchor="center")

        ttk.Label(container, text="الخدمات", font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

        buttons_row = ttk.Frame(container)
        buttons_row.pack()

        ttk.Button(buttons_row, text="📁 Dossier", command=self.open_dossier).pack(
            side="left", padx=10, ipadx=20, ipady=8
        )
        ttk.Button(buttons_row, text="CD", command=self.open_cd).pack(
            side="left", padx=10, ipadx=20, ipady=8
        )

    def open_dossier(self):
        self.clear_body()
        DossierTab(self.body, self).pack(fill="both", expand=True)

    def open_cd(self):
        self.clear_body()
        CDTab(self.body, self).pack(fill="both", expand=True)


def main():
    init_db()
    app = OfficeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
