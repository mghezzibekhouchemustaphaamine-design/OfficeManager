"""معالج الإعداد الأول لحماية البيانات (3-2-1): يظهر أول فتح للبرنامج
بس (لو ماكو وجهة "ثانية" أو "سحابة" معيّنة بعد ولا اختار المستخدم
"لاحقاً" مرة سابقة — راجع backup.resilience_setup_needed/
mark_resilience_setup_skipped)، يعرض مكان الشغل الرئيسي للمعلومة بس
(بلا تعديل)، ويطلب مجلدين: نسخة ثانية (قرص/فلاشة مختلفة فعلياً — نتحقق
فوراً ونرفض لو نفس القرص) ونسخة سحابة (أي مجلد مزامنة، نقترح OneDrive
تلقائياً لو مكتشَف). يُستدعى من main() بس (مو من OfficeApp نفسها) —
نفس اصطلاح backup.maybe_run_daily_backup() بالضبط، حتى ما يظهر أثناء
الاختبارات الآلية اللي تبني OfficeApp() مباشرة."""
import os
import tkinter as tk
from tkinter import ttk, filedialog

from ui.common import alerts

import programme.backup as backup
from programme.paths import get_travail_root


class ResilienceSetupWizard(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("إعداد حماية البيانات")
        self.geometry("620x420")
        self.transient(parent)
        self.grab_set()

        self._secondary_path = tk.StringVar()
        self._cloud_path = tk.StringVar()

        ttk.Label(
            self, text="🛡️ حماية شغلك من فقدان القرص أو الجهاز",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=15, pady=(15, 5))

        intro = (
            "شغلك الحالي محفوظ هون (بلا أي تغيير):\n"
            f"  • قاعدة البيانات: {backup.DB_PATH}\n"
            f"  • المستندات: {get_travail_root()}\n\n"
            "نضيف الآن نسختين احتياطيتين — قرص مختلف يحميك من عطل هالقرص، "
            "وسحابة تحميك من فقدان الجهاز كله (حريق، سرقة...)."
        )
        ttk.Label(self, text=intro, wraplength=580, justify="right").pack(
            anchor="e", padx=15, pady=(0, 15)
        )

        self._build_role_row(
            "🔒 النسخة الثانية (قرص أو فلاشة مختلفة)", self._secondary_path, self._pick_secondary,
        )
        self._build_role_row("☁️ نسخة السحابة (OneDrive أو أي خدمة مزامنة)", self._cloud_path, self._pick_cloud)

        btns = ttk.Frame(self)
        btns.pack(fill="x", side="bottom", padx=15, pady=15)
        ttk.Button(btns, text="لاحقاً", command=self._skip).pack(side="left")
        ttk.Button(btns, text="✅ حفظ", command=self._save).pack(side="right")

    def _build_role_row(self, title, var, command):
        frame = ttk.LabelFrame(self, text=title)
        frame.pack(fill="x", padx=15, pady=8)
        ttk.Entry(frame, textvariable=var, state="readonly", width=55).pack(
            side="left", padx=10, pady=10, fill="x", expand=True
        )
        ttk.Button(frame, text="اختر مجلد...", command=command).pack(side="left", padx=(0, 10))

    def _pick_secondary(self):
        path = filedialog.askdirectory(
            title="اختر مجلد بقرص أو فلاشة مختلفة عن القرص الرئيسي", parent=self,
        )
        if path:
            self._secondary_path.set(path)

    def _pick_cloud(self):
        suggested = backup.ONEDRIVE_SUGGESTED_PATH
        if os.path.exists(suggested) and alerts.confirm_always(
            "نسخة السحابة", f"لقيت مجلد OneDrive بجهازك:\n{suggested}\nتستخدمه؟", parent=self,
        ):
            self._cloud_path.set(suggested)
            return
        path = filedialog.askdirectory(
            title="اختر مجلد يتزامن مع خدمة سحابة (Google Drive/Dropbox...)", parent=self,
        )
        if path:
            self._cloud_path.set(path)

    def _save(self):
        secondary, cloud = self._secondary_path.get().strip(), self._cloud_path.get().strip()
        if not secondary and not cloud:
            alerts.info(
                "ما اخترت شي", "اختر مجلد واحد على الأقل، أو اضغط \"لاحقاً\" لتأجيل الإعداد.", parent=self,
            )
            return
        if secondary:
            try:
                backup.set_role_destination("secondary", "نسخة ثانية", secondary)
            except ValueError as exc:
                alerts.error("قرص غير مناسب", str(exc), parent=self)
                return
        if cloud:
            backup.set_role_destination("cloud", "نسخة سحابة", cloud)
        self.destroy()

    def _skip(self):
        backup.mark_resilience_setup_skipped()
        self.destroy()


def maybe_show_setup_wizard(parent):
    """تُستدعى من main() بعد إنشاء النافذة الرئيسية مباشرة — تفتح
    المعالج فقط لو الإعداد ناقص فعلاً وما اختار المستخدم "لاحقاً" مرة
    سابقة."""
    if backup.resilience_setup_needed() and not backup.resilience_setup_was_skipped():
        ResilienceSetupWizard(parent)
