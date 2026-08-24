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

        # لما نافذة البرنامج تفقد التركيز على مستوى النظام (Alt+Tab
        # لبرنامج آخر)، نلتقط الخانة اللي فيها التركيز فعلياً وقتها —
        # تُستخدم بواجهات الحقول (ui/widgets.py: is_window_reactivation_focus)
        # للتفريق بين رجوع النافذة نفسها للواجهة (ما نلمس فيه شي) وبين
        # تنقّل حقيقي بين الخانات (يحدّد كل المكتوب زي المطلوب). بدون
        # هالتفريق، أي رجوع من برنامج آخر كان يحدّد كل الكتابة الجارية
        # ويجبر إعادتها من جديد بدل إكمالها من مكانها.
        #
        # نتتبّع "آخر خانة فيها تركيز" باستمرار عبر bind_all (يشتغل مع
        # أي خانة بكل التطبيق، حتى لو ما عندها أي ربط خاص منا — أزرار،
        # خانات بتبويب ثاني...) بدل الاعتماد على focus_get() لحظة حدث
        # Deactivate نفسه (توقيته غير مضمون، ممكن يرجع فاضي وقتها).
        self.bind_all("<FocusIn>", self._on_any_focus_in, add="+")
        self.bind("<Deactivate>", self._on_window_deactivate)

        self.show_home()

    def _on_any_focus_in(self, event):
        self._current_focus_widget = event.widget

    def _on_window_deactivate(self, _event):
        self._deactivated_focus_widget = getattr(self, "_current_focus_widget", None)

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
