"""شاشة الدخول (أو إنشاء الحساب أول تشغيل) — أول شي يظهر بالبرنامج، قبل
OfficeApp نفسها (راجع main.py). نافذة Tk جذرية مستقلة (مو Toplevel فوق
OfficeApp — لأنها تظهر قبل ما OfficeApp تُنشأ أصلاً)، بنفس الأسلوب
البصري لـui/resilience_wizard.py (عنوان، حقول بسيطة، زر تأكيد واحد).

حساب واحد بس بكل تنصيب — لو ماكو حساب أصلاً (programme.auth.has_account()
False)، نفس الشاشة تتحول تلقائياً لوضع "إنشاء الحساب" (نفس الحقلين،
زر مختلف بس) بدل شاشة منفصلة زيادة. نفس التحول (login ↔ create) يصير
كمان بعد استرجاع ناجح بكود الاسترجاع (راجع _forgot_password) — بدون
إعادة تشغيل main.py، لهذا الودجتس تُبنى عبر _build_ui() قابلة للإعادة
لا __init__ مباشر."""
import tkinter as tk
from tkinter import ttk

import programme.auth as auth
from ui.common import alerts


class LoginScreen:
    def __init__(self, root):
        self.root = root
        self.success = False
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self._create_mode = not auth.has_account()
        self._build_ui()

    def _build_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.username_var.set("")
        self.password_var.set("")

        self.root.title("إنشاء الحساب" if self._create_mode else "تسجيل الدخول")
        self.root.geometry("380x340")
        self.root.resizable(False, False)

        heading = "🔑 إنشاء حساب الدخول" if self._create_mode else "🔑 تسجيل الدخول"
        ttk.Label(self.root, text=heading, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(20, 5)
        )
        if self._create_mode:
            ttk.Label(
                self.root,
                text="أنشئ حساب الدخول (اسم مستخدم وكلمة مرور جديدين).",
                wraplength=340, justify="right",
            ).pack(anchor="e", padx=20, pady=(0, 10))

        form = ttk.Frame(self.root)
        form.pack(fill="x", padx=20, pady=(10, 0))
        ttk.Label(form, text="اسم المستخدم:").pack(anchor="e")
        entry_user = ttk.Entry(form, textvariable=self.username_var)
        entry_user.pack(fill="x", pady=(2, 12))
        ttk.Label(form, text="كلمة المرور:").pack(anchor="e")
        entry_pw = ttk.Entry(form, textvariable=self.password_var, show="•")
        entry_pw.pack(fill="x", pady=(2, 12))

        btn_text = "✅ إنشاء الحساب" if self._create_mode else "✅ دخول"
        ttk.Button(self.root, text=btn_text, command=self._submit).pack(
            padx=20, pady=(5, 10), fill="x"
        )

        # "نسيت كلمة المرور؟" بوضع تسجيل الدخول بس — إنشاء الحساب أصلاً
        # ما فيه شي تنساه بعد (حساب جديد كليّاً).
        if not self._create_mode:
            forgot = ttk.Label(
                self.root, text="نسيت كلمة المرور؟", foreground="#1a73e8", cursor="hand2",
            )
            forgot.pack(anchor="e", padx=20, pady=(0, 10))
            forgot.bind("<Button-1>", lambda _e: self._forgot_password())

        entry_user.focus_set()
        self.root.bind("<Return>", lambda _e: self._submit())

    def _submit(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            alerts.error(
                "بيانات ناقصة", "لازم تكتب اسم مستخدم وكلمة مرور.", parent=self.root
            )
            return

        if self._create_mode:
            recovery_code = auth.create_account(username, password)
            # إصلاح: أول جلسة بعد إنشاء الحساب لازم تُسجَّل بـ
            # login_sessions بالضبط زي أي دخول عادي — كانت مفقودة سابقاً.
            auth.record_login(username)
            self._show_recovery_code(recovery_code)
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

    def _show_recovery_code(self, code):
        """يعرض كود الاسترجاع مرة وحدة بس بعد إنشاء الحساب مباشرة —
        نافذة تأكيد إجبارية (بلا زر إغلاق بالعنوان، بلا تجاهل) حتى
        OfficeApp ما تفتح إلا بعد ما المستخدم يأكد صراحة إنه حفظ الكود."""
        top = tk.Toplevel(self.root)
        top.title("كود الاسترجاع")
        top.transient(self.root)
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", lambda: None)  # لا يُغلق إلا بالزر بالأسفل
        top.grab_set()

        ttk.Label(top, text="🔐 كود الاسترجاع", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(20, 5)
        )
        ttk.Label(
            top,
            text="احفظ هذا الكود بمكان آمن — يُستعمل لاحقاً لو نسيت كلمة "
                 "المرور.\nما رح يبان مرة ثانية بعد ما تسكّر هذي النافذة.",
            wraplength=340, justify="right",
        ).pack(anchor="e", padx=20, pady=(0, 12))

        code_entry = ttk.Entry(
            top, textvariable=tk.StringVar(value=code), justify="center",
            font=("Consolas", 14, "bold"),
        )
        code_entry.pack(fill="x", padx=20, pady=(0, 4))
        code_entry.icursor("end")

        ttk.Button(top, text="✅ حفظت الكود", command=top.destroy).pack(
            padx=20, pady=(16, 20), fill="x"
        )

        top.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - top.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - top.winfo_height()) // 2
        top.geometry(f"+{x}+{y}")

        self.root.wait_window(top)

    def _forgot_password(self):
        top = tk.Toplevel(self.root)
        top.title("استرجاع الحساب")
        top.transient(self.root)
        top.resizable(False, False)
        top.grab_set()

        ttk.Label(
            top, text="🔓 استرجاع الحساب بكود الاسترجاع", font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=20, pady=(20, 5))
        ttk.Label(
            top,
            text="أدخل كود الاسترجاع اللي انعطى لك عند إنشاء الحساب. الكود "
                 "الصحيح يحذف الحساب الحالي ويتيح إنشاء حساب جديد.",
            wraplength=320, justify="right",
        ).pack(anchor="e", padx=20, pady=(0, 12))

        code_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=code_var, justify="center", font=("Consolas", 12))
        entry.pack(fill="x", padx=20, pady=(0, 16))
        entry.focus_set()

        def _confirm_code():
            code = code_var.get().strip()
            if not code:
                alerts.error("كود ناقص", "لازم تكتب كود الاسترجاع.", parent=top)
                return
            if auth.reset_account_with_recovery_code(code):
                top.destroy()
                alerts.info(
                    "تم الاسترجاع",
                    "الحساب القديم انحذف. أنشئ حساب جديد الآن.",
                    parent=self.root,
                )
                self._create_mode = True
                self._build_ui()
            else:
                alerts.error(
                    "كود غير صحيح",
                    "كود الاسترجاع غير صحيح — الحساب الحالي بقي كما هو.",
                    parent=top,
                )

        ttk.Button(top, text="تأكيد", command=_confirm_code).pack(
            padx=20, pady=(0, 20), fill="x"
        )
        top.bind("<Return>", lambda _e: _confirm_code())


def run_login_flow():
    """يعرض شاشة الدخول/إنشاء الحساب وينتظر لحد ما المستخدم يدخل بنجاح
    أو يسكّر النافذة. يرجّع True لو دخل بنجاح (main.py يكمل فتح
    OfficeApp)، False لو سكّر النافذة بدون دخول (البرنامج ما يفتح
    إطلاقاً — راجع main.py)."""
    root = tk.Tk()
    screen = LoginScreen(root)
    root.mainloop()
    return screen.success
