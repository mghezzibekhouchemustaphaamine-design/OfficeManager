"""
عرض تجريبي حقيقي (شغّال فعلاً، مو صورة) لشكل شاشة CD بـPySide6 — واجهة
بس، بلا أي ربط بقاعدة البيانات أو case_ops الحقيقية (زر "حفظ" هون بس
يعرض رسالة تأكيد للتجربة). الهدف: تشوف وتحس الفرق الحقيقي بنفسك قبل ما
تقرر تنقل التطبيق كامل.

التشغيل عندك (جهازك، مو هون بالجلسة السحابية — PySide6 ما ينثبت هون):
    pip install PySide6
    python cd_screen_demo_pyside6.py

⚠️ هذا الملف ما اتشغّل ولا اتّختبر فعلياً بأي بيئة (PySide6 ما كان
متوفر بالجلسة السحابية لأثبّته وأجربه) — كتبته بالاعتماد على معرفتي
بـPySide6 API. لو طلعت أي مشكلة بالتشغيل عندك، ابعتلي رسالة الخطأ
بالضبط وأصلّحها فوراً.
"""
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QDateEdit, QMessageBox,
)
from PySide6.QtCore import QDate


STYLE = """
QWidget#root { background: #ffffff; }

QLabel.field-label {
    color: #64748b; font-size: 11px; font-weight: 600;
    letter-spacing: 0.3px;
}
QLineEdit {
    background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 8px;
    padding: 8px 10px; font-size: 13px; color: #1e293b;
}
QLineEdit:focus { border-color: #2563eb; background: #ffffff; }

QDateEdit {
    background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 8px;
    padding: 6px 10px; font-size: 13px; color: #1e293b;
}

QFrame#titlebar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                 stop:0 #2563eb, stop:1 #1d4ed8);
    border-top-left-radius: 12px; border-top-right-radius: 12px;
}
QLabel#titleLabel { color: white; font-size: 14px; font-weight: 700; }

QFrame#amountCard {
    background: #f1f5f9; border-radius: 10px; border: 1px solid #e2e8f0;
}
QLabel.amount-value { font-size: 20px; font-weight: 700; color: #1e293b; }
QLabel.amount-caption { color: #94a3b8; font-size: 11px; }

QPushButton {
    border: none; border-radius: 8px; padding: 10px 18px;
    font-size: 13px; font-weight: 700;
}
QPushButton#primary { background: #2563eb; color: white; }
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#ghost { background: #eef2ff; color: #2563eb; }
QPushButton#ghost:hover { background: #e0e7ff; }
"""


def field(label_text):
    """(عمود عمودي: تسمية صغيرة فوق + خانة كتابة) — يرجّع (widget, entry)."""
    box = QVBoxLayout()
    box.setSpacing(4)
    lbl = QLabel(label_text)
    lbl.setProperty("class", "field-label")
    entry = QLineEdit()
    box.addWidget(lbl)
    box.addWidget(entry)
    wrapper = QWidget()
    wrapper.setLayout(box)
    return wrapper, entry


class CDScreenDemo(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("OfficeManager · Change Devise — عرض تجريبي PySide6")
        self.resize(560, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- شريط العنوان ----
        titlebar = QFrame()
        titlebar.setObjectName("titlebar")
        tb_layout = QHBoxLayout(titlebar)
        tb_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("Change Devise (CD)")
        title.setObjectName("titleLabel")
        tb_layout.addWidget(title)
        outer.addWidget(titlebar)

        # ---- جسم الاستمارة ----
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 20, 22, 20)
        body_layout.setSpacing(14)

        # صف Agence/Devise/Guichet/Caisse (٤ أعمدة، نفس شاشتك الحقيقية)
        row1 = QGridLayout()
        row1.setSpacing(12)
        w, self.agence = field("AGENCE")
        row1.addWidget(w, 0, 0)
        w, self.devise = field("DEVISE")
        row1.addWidget(w, 0, 1)
        w, self.guichet = field("GUICHET")
        row1.addWidget(w, 0, 2)
        w, self.caisse = field("CAISSE")
        row1.addWidget(w, 0, 3)
        self.agence.setText("0021")
        self.devise.setText("EUR")
        self.guichet.setText("0007")
        self.caisse.setText("0003")
        body_layout.addLayout(row1)

        w, self.passager = field("NOM DU REMETTANT")
        body_layout.addWidget(w)
        self.passager.setText("Bekhouche Amine")

        row2 = QGridLayout()
        row2.setSpacing(12)
        w, self.passport = field("N° PASSPORT")
        row2.addWidget(w, 0, 0)
        self.passport.setText("18AB34567")

        obtent_box = QVBoxLayout()
        obtent_box.setSpacing(4)
        obtent_lbl = QLabel("تاريخ الحصول (Obtent.)")
        obtent_lbl.setProperty("class", "field-label")
        self.obtent_date = QDateEdit(calendarPopup=True)
        self.obtent_date.setDate(QDate.currentDate())
        obtent_box.addWidget(obtent_lbl)
        obtent_box.addWidget(self.obtent_date)
        obtent_wrapper = QWidget()
        obtent_wrapper.setLayout(obtent_box)
        row2.addWidget(obtent_wrapper, 0, 1)

        body_layout.addLayout(row2)

        w, self.client = field("الزبون")
        self.client.setPlaceholderText("ابحث عن زبون بالاسم...")
        body_layout.addWidget(w)

        # بطاقة المبالغ
        amount_card = QFrame()
        amount_card.setObjectName("amountCard")
        ac_layout = QGridLayout(amount_card)
        ac_layout.setContentsMargins(16, 14, 16, 14)
        ac_layout.setSpacing(4)

        eur_caption = QLabel("Montant EUR")
        eur_caption.setProperty("class", "amount-caption")
        eur_val = QLabel("450,00")
        eur_val.setProperty("class", "amount-value")
        ac_layout.addWidget(eur_caption, 0, 0)
        ac_layout.addWidget(eur_val, 1, 0)

        taux_caption = QLabel("Tx de change")
        taux_caption.setProperty("class", "amount-caption")
        taux_val = QLabel("260,50")
        taux_val.setProperty("class", "amount-value")
        ac_layout.addWidget(taux_caption, 0, 1)
        ac_layout.addWidget(taux_val, 1, 1)

        body_layout.addWidget(amount_card)
        body_layout.addStretch()

        # ---- أزرار ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        save_btn = QPushButton("💾 حفظ")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._on_save_clicked)
        print_btn = QPushButton("🖨️ طباعة")
        print_btn.setObjectName("ghost")
        new_btn = QPushButton("🆕 مستند جديد")
        new_btn.setObjectName("ghost")
        new_btn.clicked.connect(self._on_new_clicked)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(print_btn)
        btn_row.addWidget(new_btn)
        btn_row.addStretch()
        body_layout.addLayout(btn_row)

        outer.addWidget(body)

    def _on_save_clicked(self):
        # عرض تجريبي بس — بلا أي حفظ حقيقي بقاعدة بيانات أو ملفات.
        QMessageBox.information(
            self, "تجربة", "هيك بيبان شكل رسالة تأكيد بـQt (زر حفظ حقيقي هون رح يستدعي case_ops الحقيقية)."
        )

    def _on_new_clicked(self):
        self.passager.clear()
        self.passport.clear()
        self.client.clear()


if __name__ == "__main__":
    print("PySide6 استوردت صح — عم أبني النافذة...")
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setStyleSheet(STYLE)
    window = CDScreenDemo()
    window.show()
    window.raise_()
    window.activateWindow()
    print("النافذة المفروض فتحت هلق — دوّر عليها بالـ Alt+Tab أو شريط المهام.")
    sys.exit(app.exec())
