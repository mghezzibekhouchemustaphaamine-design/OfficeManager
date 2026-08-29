"""نافذة سجل مستندات CD السابقة — بحث سريع (اسم الراكب/رقم البوردرو/رقم
الجواز)، فتح الملف الأصلي، فتح مستند قديم للتعديل بتبويب جديد بشاشة CD،
وإعادة طباعته — بدل إعادة تعبئة من الصفر أو البحث يدوياً بمجلدات الأقراص.

ملف مستقل عن tab.py (CDTab يُمرَّر له كمرجع بس عبر المُنشئ، للاستدعاء
بس — CDHistoryWindow ما يعرف تفاصيل بناء الشاشة الداخلية)."""
import os
import tkinter as tk
from tkinter import ttk, simpledialog

from ui.common import alerts

from programme.database import search_cd_documents, deserialize_cd_data
from ui.cd.document import generate_cd_pdf, OUTPUT_DIR
from programme.utils import open_path


class CDHistoryWindow(tk.Toplevel):
    def __init__(self, cd_tab):
        super().__init__(cd_tab)
        self.cd_tab = cd_tab
        self.title("سجل مستندات CD")
        self.geometry("760x420")
        self.transient(cd_tab.winfo_toplevel())

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="بحث (اسم الراكب / رقم البوردرو / رقم الجواز):").pack(side="left")
        self.query_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.query_var)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        entry.bind("<KeyRelease>", lambda _e: self._refresh())
        entry.focus_set()

        columns = ("dossier_no", "passager", "passport_no", "doc_date", "agence", "created_at")
        headers = {
            "dossier_no": "رقم البوردرو", "passager": "الراكب", "passport_no": "رقم الجواز",
            "doc_date": "تاريخ المعاملة", "agence": "Agence", "created_at": "وقت الإنشاء",
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=110, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)

        btns = ttk.Frame(self, padding=(10, 0, 10, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="📂 فتح الملف المحدَّد", command=self._open_selected).pack(side="left")
        ttk.Button(btns, text="📝 فتح للتعديل بالاستمارة", command=self._load_selected_for_edit).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(btns, text="🖨️ إعادة طباعة", command=self._reprint_selected).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="إغلاق", command=self.destroy).pack(side="right")

        self._rows = []
        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows = search_cd_documents(self.query_var.get().strip())
        for row in self._rows:
            self.tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row.get("dossier_no") or "",
                    row.get("passager") or "",
                    row.get("passport_no") or "",
                    row.get("doc_date") or "",
                    row.get("agence") or "",
                    (row.get("created_at") or "")[:16],
                ),
            )

    def _get_selected_row(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return next((r for r in self._rows if str(r["id"]) == sel[0]), None)

    def _show_context_menu(self, event):
        """قائمة كليك يمين — نفس أزرار الشريط السفلي بالضبط، بس أوضح
        وأسرع (زي قائمة كليك يمين بالشريط الجانبي — راجع ui/common/
        file_explorer.py). تحدّد الصف تحت المؤشر أولاً."""
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📂 فتح الملف المحدَّد", command=self._open_selected)
        menu.add_command(label="📝 فتح للتعديل بالاستمارة", command=self._load_selected_for_edit)
        menu.add_command(label="🖨️ إعادة طباعة", command=self._reprint_selected)
        menu.add_separator()
        menu.add_command(label="📁 أظهره بالشريط الجانبي", command=self._reveal_in_sidebar)
        menu.tk_popup(event.x_root, event.y_root)

    def _reveal_in_sidebar(self):
        """يقفز بالشريط الجانبي (شاشة CD اللي فتحت منها هذي النافذة) مباشرة
        للملف المحدَّد ويحدّده — نفس آلية القفز التلقائي بعد توليد مستند
        جديد بالضبط (راجع _do_generate بـtab.py)، بس يدوياً هون لأي مستند
        قديم تلقاه بالسجل. يسكّر النافذة بعدها حتى تشوف الشريط محدَّثاً
        فوراً (زي فتح للتعديل بالاستمارة بالضبط)."""
        row = self._get_selected_row()
        if row is None:
            return
        if not os.path.exists(row["file_path"]):
            alerts.error("خطأ", "الملف غير موجود (ربما نُقل أو حُذف).")
            return
        self.cd_tab.explorer_panel.refresh()
        self.cd_tab.explorer_panel.reveal_path(row["file_path"])
        self.destroy()

    def _open_selected(self):
        row = self._get_selected_row()
        if row is None:
            return
        if not open_path(row["file_path"]):
            alerts.error("خطأ", "الملف غير موجود (ربما نُقل أو حُذف).")

    def _load_selected_for_edit(self):
        """يحمّل بيانات المستند المحدَّد كاملة **بتبويب جديد مستقل** (زي
        فتح رابط بتبويب جديد بالمتصفح) للمراجعة أو التعديل — بعدها لو
        حفظت من نفس التبويب، يحدّث فوق نفس الحالة (نفس السطر، نفس
        الملفين) بدل ما يسجّل حالة جديدة مكرّرة (راجع "loaded_from"
        بـ_open_data_in_new_tab وشرح "حفظ" مقابل "حفظ في مكان آخر"
        بـtab.py). بما إنه تبويب جديد، ما يلمس أي تبويب مفتوح حالياً —
        بلا حاجة لأي تأكيد."""
        row = self._get_selected_row()
        if row is None:
            return
        data = deserialize_cd_data(row.get("full_data_json"))
        if data is None:
            alerts.info(
                "غير متاح",
                "هذا مستند قديم (قبل تفعيل حفظ كل بيانات الاستمارة)، فبياناته الكاملة غير محفوظة "
                "بالسجل — ما نقدر نرجّعه للاستمارة.\nتقدر تفتح الملف نفسه بس (📂 فتح الملف المحدَّد).",
            )
            return
        self.cd_tab._open_data_in_new_tab(
            data, source_row_id=row["id"], source_file_path=row.get("file_path"), source_pdf_path=row.get("pdf_path"),
        )
        self.destroy()

    def _reprint_selected(self):
        """يطبع نسخة PDF الدائمة المحفوظة أصلاً للمستند (كل حفظ حديث
        يولّدها تلقائياً — راجع _do_generate بـtab.py)، لو موجودة فعلياً.
        وإلا (مستند أقدم من هذا التغيير) يولّد نسخة PDF مؤقتة من بيانات
        المستند الكاملة لو محفوظة بالسجل (أضمن، بلا حاجة لـWord). لو
        مستند أقدم من هذا كمان بلا بيانات كاملة (قبل تفعيل full_data_json)،
        يطبع الملف الأصلي (Word) كما كان، وقد يحتاج Word مثبَّتاً عندها."""
        row = self._get_selected_row()
        if row is None:
            return
        if row.get("pdf_path") and os.path.exists(row["pdf_path"]):
            print_path = row["pdf_path"]
        else:
            data = deserialize_cd_data(row.get("full_data_json"))
            if data is not None:
                try:
                    print_path = generate_cd_pdf(
                        data, out_path=os.path.join(OUTPUT_DIR, "_print_tmp.pdf")
                    )
                except Exception as exc:  # noqa: BLE001
                    alerts.error("خطأ", f"تعذر تجهيز نسخة الطباعة (PDF):\n{exc}")
                    return
            else:
                print_path = row["file_path"]
                if not os.path.exists(print_path):
                    alerts.error("خطأ", "الملف غير موجود (ربما نُقل أو حُذف).")
                    return
        copies = simpledialog.askinteger(
            "إعادة طباعة", "عدد النسخ؟", initialvalue=1, minvalue=1, maxvalue=10, parent=self,
        )
        if not copies:
            return
        try:
            for _ in range(copies):
                os.startfile(print_path, "print")
        except OSError as exc:
            alerts.error("خطأ", f"تعذر إرسال الملف للطابعة:\n{exc}")
