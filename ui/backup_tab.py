"""شاشة النسخ الاحتياطي: تعرض مكان الشغل الرئيسي (للمعلومة بس، بلا أي
تعديل)، وتسمح بإعداد وجهتين مطلوبتين (نسخة ثانية بقرص مختلف، ونسخة
سحابة) بالإضافة لأي وجهات إضافية اختيارية — بلا حاجة لأي تعديل كود.
راجع backup.py للتفاصيل الكاملة (مرآة + نسخ بتواريخ، فرض قرص مختلف
للنسخة الثانية...)."""
import os
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog

from ui.common import alerts

import programme.backup as backup
from programme.paths import get_travail_root

_ROLE_LABELS = {"secondary": "نسخة ثانية (قرص مختلف)", "cloud": "نسخة سحابة", "other": "إضافية"}


class BackupTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app

        top_bar = ttk.Frame(self)
        top_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(
            top_bar, text="🗄️ النسخ الاحتياطي وحماية البيانات", font=("Segoe UI", 14, "bold")
        ).pack(side="left")
        ttk.Button(top_bar, text="← رجوع", command=self.app.show_home).pack(side="right")

        primary_text = f"📍 المكان الرئيسي (بلا تغيير): {backup.DB_PATH}  |  {get_travail_root()}"
        ttk.Label(self, text=primary_text, foreground="#555", wraplength=760, justify="right").pack(
            fill="x", pady=(0, 10)
        )

        # حالة حساب OneDrive الحقيقية (مربوط فعلاً ولا لأ) — أول شي تشوفه
        # لما تفتح الشاشة، حتى تعرف بثانية وحدة هل نسخك فعلاً بترفع للسحابة.
        self.onedrive_banner = ttk.Label(
            self, text="", anchor="w", font=("Segoe UI", 10, "bold"), wraplength=760, justify="right",
        )
        self.onedrive_banner.pack(fill="x", pady=(0, 8))

        roles_bar = ttk.Frame(self)
        roles_bar.pack(fill="x", pady=(0, 8))
        ttk.Button(
            roles_bar, text="🔒 إعداد النسخة الثانية (قرص/فلاشة مختلفة)", command=self._setup_secondary,
        ).pack(side="left")
        ttk.Button(roles_bar, text="☁️ إعداد نسخة السحابة", command=self._setup_cloud).pack(
            side="left", padx=(8, 0)
        )

        actions_bar = ttk.Frame(self)
        actions_bar.pack(fill="x", pady=(0, 8))
        ttk.Button(actions_bar, text="📦 نسخة احتياطية الآن", command=self._run_now).pack(side="left")
        ttk.Button(actions_bar, text="➕ أضف مكان إضافي (فلاشة ثانية...)", command=self._add_destination).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions_bar, text="🗑️ احذف المكان المحدَّد", command=self._remove_selected).pack(
            side="left", padx=(8, 0)
        )

        self.status_label = ttk.Label(self, text="", anchor="w", font=("Segoe UI", 10))
        self.status_label.pack(fill="x", pady=(0, 8))

        columns = ("role", "label", "path", "status")
        headers = {"role": "النوع", "label": "الاسم", "path": "المسار", "status": "الحالة الآن"}
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=280 if col == "path" else 130, anchor="w")
        self.tree.pack(fill="both", expand=True)

        note = (
            "ملاحظة: كل وجهة تاخذ نسخة \"مرآة\" (تبين بالضبط زي المكان الرئيسي) + نسخ قاعدة "
            "بيانات بتواريخ (آخر 30 يوم) للرجوع لنقطة قبل أي خلل. النسخة الثانية لازم تكون "
            "بقرص مختلف فعلياً عن القرص الرئيسي — وإلا عطل بهالقرص يمسح الاثنين معاً."
        )
        ttk.Label(self, text=note, foreground="#666", wraplength=760, justify="right").pack(
            fill="x", pady=(8, 0)
        )

        self._refresh()

    def _refresh(self):
        self._refresh_onedrive_banner()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for dest in backup.get_destinations():
            reachable = backup.is_destination_reachable(dest["path"])
            status = "✅ متاحة الآن" if reachable else "⚠️ غير متاحة الآن"
            role = _ROLE_LABELS.get(dest.get("role"), "إضافية")
            self.tree.insert("", "end", values=(role, dest["label"], dest["path"], status))

        last_at, last_ok = backup.last_backup_info()
        if last_at:
            when = last_at[:16].replace("T", " ")
            ok_text = "، ".join(last_ok) if last_ok else "لا أحد (كل الوجهات كانت غير متاحة)"
            self.status_label.configure(text=f"آخر نسخة: {when} — نجحت لـ: {ok_text}")
        else:
            self.status_label.configure(text="ما فيه أي نسخة احتياطية اتسوّت بعد.")

    def _refresh_onedrive_banner(self):
        state, detail = backup.onedrive_status()
        if state == "signed_in":
            text = f"☁️ OneDrive: ✅ مربوط بحساب ({detail}) — النسخ فعلاً ترفع للسحابة"
            color = "#1a7f37"
        elif state == "not_signed_in":
            text = (
                "☁️ OneDrive: ⚠️ مثبَّت لكن حسابك غير مربوط — أي ملف بمجلده يبقى محلي بس، "
                "ما يرفع للسحابة إطلاقاً! افتح OneDrive من قائمة ابدأ وسجّل دخول."
            )
            color = "#b35c00"
        elif state == "not_installed":
            text = "☁️ OneDrive: ❌ غير مثبَّت على هذا الجهاز — النسخة السحابية معطّلة حالياً."
            color = "#999999"
        else:
            text = "☁️ OneDrive: تعذّر فحص الحالة."
            color = "#999999"
        self.onedrive_banner.configure(text=text, foreground=color)

    def _setup_secondary(self):
        path = filedialog.askdirectory(
            title="اختر مجلد بقرص أو فلاشة مختلفة عن القرص الرئيسي", parent=self,
        )
        if not path:
            return
        try:
            backup.set_role_destination("secondary", "نسخة ثانية", path)
        except ValueError as exc:
            alerts.error("قرص غير مناسب", str(exc), parent=self)
            return
        self._refresh()

    def _setup_cloud(self):
        suggested = backup.ONEDRIVE_SUGGESTED_PATH if os.path.exists(backup.ONEDRIVE_SUGGESTED_PATH) else None
        if suggested and alerts.confirm_always(
            "نسخة السحابة",
            f"لقيت مجلد OneDrive بجهازك:\n{suggested}\nتستخدمه؟ (لا = تختار مجلد آخر، أي خدمة سحابة أخرى)",
            parent=self,
        ):
            path = suggested
        else:
            path = filedialog.askdirectory(
                title="اختر مجلد يتزامن مع خدمة سحابة (OneDrive/Google Drive/Dropbox...)", parent=self,
            )
            if not path:
                return
        try:
            backup.set_role_destination("cloud", "نسخة سحابة", path)
        except ValueError as exc:
            alerts.error("مكان غير مناسب", str(exc), parent=self)
            return
        self._refresh()

    def _run_now(self):
        succeeded, skipped = backup.run_backup()
        self._refresh()
        msg = f"✅ نُسخت لـ: {'، '.join(succeeded) if succeeded else '—'}"
        if skipped:
            msg += f"\n⚠️ غير متاحة الآن (تُجووزت): {'، '.join(skipped)}"
        alerts.info("النسخ الاحتياطي", msg)

    def _add_destination(self):
        path = filedialog.askdirectory(title="اختر مجلد لحفظ النسخ الاحتياطية فيه", parent=self)
        if not path:
            return
        label = simpledialog.askstring(
            "اسم المكان", "اسم مختصر لهذا المكان (مثلاً: فلاشة ثانية):", parent=self,
        )
        if not label:
            label = os.path.basename(os.path.normpath(path)) or path
        if backup.add_destination(label, path):
            self._refresh()
        else:
            alerts.info("موجودة أصلاً", "هذا المكان مضاف مسبقاً بقائمة الوجهات.")

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        path = self.tree.item(sel[0], "values")[2]
        if backup.remove_destination(path):
            self._refresh()

    def refresh(self):
        self._refresh()
