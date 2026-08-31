"""شاشة الدخول (أو إنشاء الحساب أول تشغيل) — أول شي يظهر بالبرنامج، قبل
OfficeApp نفسها (راجع main.py). نافذة Tk جذرية مستقلة (مو Toplevel فوق
OfficeApp — لأنها تظهر قبل ما OfficeApp تُنشأ أصلاً)، بنفس الأسلوب
البصري لـui/resilience_wizard.py (عنوان، حقول بسيطة، زر تأكيد واحد).

حساب واحد بس بكل تنصيب — لو ماكو حساب أصلاً (programme.auth.has_account()
False)، نفس الشاشة تتحول تلقائياً لوضع "إنشاء الحساب" (نفس الحقلين،
زر مختلف بس) بدل شاشة منفصلة زيادة."""
import tkinter as tk
from tkinter import ttk

import programme.auth as auth
from ui.common import alerts


class LoginScreen:
    def __init__(self, root):
        self.root = root
        self.success = False
        self._create_mode = not auth.has_account()

        root.title("إنشاء الحساب" if self._create_mode else "تسجيل الدخول")
        root.geometry("380x300")
        root.resizable(False, False)

        heading = "🔑 إنشاء حساب الدخول" if self._create_mode else "🔑 تسجيل الدخول"
        ttk.Label(root, text=heading, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(20, 5)
        )
        if self._create_mode:
            ttk.Label(
                root,
                text="أول تشغيل للبرنامج — أنشئ حساب الدخول (مرة وحدة بس، ما يتكرر لاحقاً).",
                wraplength=340, justify="right",
            ).pack(anchor="e", padx=20, pady=(0, 10))

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        form = ttk.Frame(root)
        form.pack(fill="x", padx=20, pady=(10, 0))
        ttk.Label(form, text="اسم المستخدم:").pack(anchor="e")
        entry_user = ttk.Entry(form, textvariable=self.username_var)
        entry_user.pack(fill="x", pady=(2, 12))
        ttk.Label(form, text="كلمة المرور:").pack(anchor="e")
        entry_pw = ttk.Entry(form, textvariable=self.password_var, show="•")
        entry_pw.pack(fill="x", pady=(2, 12))

        btn_text = "✅ إنشاء الحساب" if self._create_mode else "✅ دخول"
        ttk.Button(root, text=btn_text, command=self._submit).pack(
            padx=20, pady=(5, 20), fill="x"
        )

        entry_user.focus_set()
        root.bind("<Return>", lambda _e: self._submit())

    def _submit(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            alerts.error(
                "بيانات ناقصة", "لازم تكتب اسم مستخدم وكلمة مرور.", parent=self.root
            )
            return

        if self._create_mode:
            auth.create_account(username, password)
            self.success = True
            self.root.destroy()
            return

        if auth.verify_login(username, password):
            auth.record_login(username)
            self.success = True
            self.root.destroy()
        else:
            alerts.error(
                "دخول خاطئ", "اسم المستخدم أو كلمة المرور غير صحيحة.", parent=self.root
            )
            self.password_var.set("")


def run_login_flow():
    """يعرض شاشة الدخول/إنشاء الحساب وينتظر لحد ما المستخدم يدخل بنجاح
    أو يسكّر النافذة. يرجّع True لو دخل بنجاح (main.py يكمل فتح
    OfficeApp)، False لو سكّر النافذة بدون دخول (البرنامج ما يفتح
    إطلاقاً — راجع main.py)."""
    root = tk.Tk()
    screen = LoginScreen(root)
    root.mainloop()
    return screen.success
