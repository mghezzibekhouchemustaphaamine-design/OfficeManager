"""معرض شاشات وحدة الأجور (المرحلة 2 — الجزء ب).

الشاشة الظاهرة الوحيدة حالياً: **توليد الكشف**. جدولا «الشركات»
و«الاتفاقية» يبقيان في المخطط و``repository``، وشاشة ``companies.py``
مبنيّة لكن **لا تُعرَض** — تُفعَّل لاحقاً بعلمٍ في الإعدادات
(:data:`SHOW_ADMIN_SCREENS`).

عند أول تشغيل: يُنشأ زبون افتراضي واتفاقية مؤكَّدة تلقائياً
(``repository.ensure_default_client``) حتى لا تمنع V15 التوليد.

التشغيل:      python demos/ui2_paie_gallery.py
بلا شاشة:     QT_QPA_PLATFORM=offscreen python demos/ui2_paie_gallery.py --selftest
"""
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from programme.payroll import repository
from ui2 import theme
from ui2.paie.bulletin import BulletinScreen
from ui2.paie.companies import CompaniesScreen        # مبنيّة، غير معروضة
from ui2.toolbar import ToolAction
from ui2.window import MainWindow

# علم إعدادات مستقبلي — تفعيل شاشات الإدارة (الشركات/الاتفاقية)
SHOW_ADMIN_SCREENS = False


def _make_db() -> sqlite3.Connection:
    path = os.path.join(tempfile.gettempdir(), "om_paie_gallery.db")
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    repository.run_migrations(conn)
    repository.ensure_default_client(conn=conn)        # أول تشغيل
    return conn


def build_gallery(conn) -> MainWindow:
    win = MainWindow("معرض شاشات الأجور — المرحلة 2")
    win.toolbar.add(ToolAction(
        "عن المعرض",
        lambda: win.status("شاشة الكشف — مبنيّة من ui2/ حصراً")))

    bulletin = BulletinScreen(conn=conn)
    win.add_tab(bulletin, "توليد كشف")
    win._bulletin = bulletin

    if SHOW_ADMIN_SCREENS:
        win.add_tab(CompaniesScreen(conn=conn), "الزبناء (إدارة)")

    win.tabs.tab_widget().setCurrentIndex(0)
    return win


def _selftest() -> int:
    from decimal import Decimal

    # صناديق الرسائل النمطية تُوقِف التشغيل بلا شاشة — نلتقطها بدل عرضها
    import ui2.paie.bulletin as _b
    import ui2.paie.companies as _c
    _captured: list = []
    _stub = lambda _p, title, lines: _captured.append((title, list(lines)))
    _b.warn = _stub
    _c.warn = _stub

    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    assert app.layoutDirection() == Qt.RightToLeft

    conn = _make_db()
    regs = repository.list_entreprises(registered_only=True, conn=conn)
    assert len(regs) == 1, regs
    print(f"[selftest] أول تشغيل: زبون افتراضي مسجَّل (id={regs[0]['id']})")

    win = build_gallery(conn)
    scr = win._bulletin

    # الأجر القاعدي مُضاف آلياً
    assert [r.type_key for r in scr._rows] == ["salaire_base"]
    scr._rows[0].form.set_values({"montant": "45000"})

    # + اقتطاع ساعات غياب  (نوع يمسّ الوعاء)
    scr.add_line("abs_heures")
    scr._rows[1].form.set_values({"heures": "16"})
    # + سلة  (نوع في Z2 يتنسّب)
    scr.add_line("panier")
    scr._rows[2].form.set_values({"montant_mensuel": "2500"})
    scr.recompute()

    v = scr._view
    zones = {l.key: l.zone for l in v.lignes}
    assert zones == {"salaire_base": "Z1", "abs_heures": "Z1",
                     "panier": "Z2"}, zones
    assert v.a == Decimal("40846.07"), v.a          # 45000 − 4153.93
    assert v.b == Decimal("3676.15"), v.b
    assert v.c == Decimal("39439.15"), v.c
    assert v.e == Decimal("36470.25"), v.e
    assert v.result.heures_presence == Decimal("157.33"), v.result.heures_presence
    print(f"[selftest] الآلية: قاعدي Z1 · غياب Z1(−) يمسّ [A] · سلة Z2 تتنسّب "
          f"→ [A]={v.a} [C]={v.c} [E]={v.e}")

    # الاتفاقية الافتراضية مؤكَّدة تلقائياً (نسخة 1) → التوليد يعمل، لكن
    # الشريط الاستشاري يبقى ظاهراً: قيمها لم يراجعها أحد (المراجعة #7).
    assert not scr._warnbar.isHidden(), "الشريط الاستشاري غائب للاتفاقية الافتراضية"
    assert "لم تُراجَع" in scr._warnbar.text(), scr._warnbar.text()
    print("[selftest] #7: اتفاقية افتراضية غير مُراجَعة → الشريط الاستشاري ظاهر دائماً")

    # حذف السلة → إعادة حساب فورية
    scr._remove_line(scr._rows[2])
    assert len(scr._view.lignes) == 2
    assert scr._view.c == Decimal("37169.92"), scr._view.c   # لا سلة في Z2
    print("[selftest] حذف سطر → إعادة حساب فورية")
    scr.add_line("panier")
    scr._rows[2].form.set_values({"montant_mensuel": "2500"})
    scr.recompute()

    # الحفظ ثم التثبيت
    scr._header.set_values({"employe_nom": "TESTي أمين",
                            "periode": "2026-09"})
    bid = scr.save()
    assert bid is not None
    saved = repository.get_bulletin(bid, conn=conn)
    assert saved["etat"] == "CALCULE"
    assert isinstance(saved["net_e"], Decimal)
    assert saved["net_e"] == Decimal("36470.25"), saved["net_e"]
    sys_codes = {l["ligne_systeme"] for l in saved["lignes"]
                 if l["zone"] == "SYSTEME"}
    assert sys_codes == {"A", "B", "C", "D", "E"}, sys_codes
    print(f"[selftest] حُفِظ الكشف #{bid} — net={saved['net_e']} · [A..E] مخزَّنة")

    numero = repository.fige_bulletin(bid, conn=conn)
    scr.fige()
    assert repository.get_bulletin(bid, conn=conn)["etat"] == "FIGE"
    print(f"[selftest] تثبيت → رقم السلسلة {numero}")

    # V15: زبون مسجَّل باتفاقية غير مؤكَّدة يُمنع حفظه — بلا أثر جانبي
    reg_id = repository.create_entreprise(
        {"raison_sociale": "SARL غير مؤكَّدة", "transient": 0}, conn=conn)
    repository.seed_catalogue(reg_id, conn=conn)
    repository.create_convention(reg_id, {}, conn=conn)     # confirme=0
    scr2 = BulletinScreen(conn=conn)
    scr2._client_id = reg_id
    scr2._header.set_values({"employe_nom": "ع. فلان", "periode": "2026-09"})
    scr2._rows[0].form.set_values({"montant": "40000"})
    scr2.recompute()
    n_ent = len(repository.list_entreprises(actif_only=False, conn=conn))
    n_emp = len(repository.list_employes(reg_id, conn=conn))
    _captured.clear()
    assert scr2.save() is None, "V15 لم تمنع الحفظ"
    assert any("V15" in t for t, _ in _captured), _captured
    assert not scr2._warnbar.isHidden()
    # لا أثر جانبي: لا صفّ entreprise/employe جديد بعد رفض V15
    assert len(repository.list_entreprises(actif_only=False, conn=conn)) == n_ent
    assert len(repository.list_employes(reg_id, conn=conn)) == n_emp
    print("[selftest] V15: حفظ ممنوع + لا صفّ entreprise/employe يتيم")

    # V16: فترة بلا ملف معاملات → الحفظ مرفوض، لا أثر جانبي
    scr2b = BulletinScreen(conn=conn)
    scr2b._header.set_values({"employe_nom": "ع. فلان", "periode": "1990-01"})
    scr2b._rows[0].form.set_values({"montant": "40000"})
    scr2b.recompute()
    n_ent = len(repository.list_entreprises(actif_only=False, conn=conn))
    _captured.clear()
    assert scr2b.save() is None
    assert any("V16" in t for t, _ in _captured), _captured
    assert len(repository.list_entreprises(actif_only=False, conn=conn)) == n_ent
    print("[selftest] V16: فترة بلا معاملات → حفظ مرفوض، لا أثر جانبي")

    # سطر الأقدمية §1.2.4: اقتراح تلقائي · تمييز «معدَّلة يدوياً» · العودة
    scr3 = BulletinScreen(conn=conn)
    # الترويسة الآن بلا تاريخ دخول افتراضي → لا اقتراح حتى يُدخَل
    assert scr3._header.values()["employe_date_entree"] == ""
    scr3.add_line("iep")
    iep_row0 = scr3._rows[-1]
    assert iep_row0.form.values()["taux"] == ""
    assert "حدّد تاريخ الدخول" in iep_row0._iep_hint.text()
    scr3._remove_line(iep_row0)

    scr3._header.set_values({"employe_nom": "IEP ت", "periode": "2026-09",
                             "employe_date_entree": "2016-06-14"})
    scr3._rows[0].form.set_values({"montant": "40000"})
    scr3.add_line("iep")
    iep_row = scr3._rows[-1]
    scr3.recompute()
    auto = iep_row.form.values()["taux"]
    assert Decimal(auto) == Decimal("0.10"), auto   # 10 سنوات كاملة × 0,01
    assert not iep_row._iep_manual
    assert "مقترَحة" in iep_row._iep_hint.text()
    # تعديل يدوي → يُوسَم، ولا يُدهَس بالاقتراح
    iep_row.form.widget("taux").setText("0.0708")
    scr3._on_line_field_edited(iep_row, "taux")
    assert iep_row._iep_manual
    scr3.recompute()
    assert iep_row.form.values()["taux"] == "0.0708"
    assert "معدَّلة يدوياً" in iep_row._iep_hint.text()
    # العودة إلى المقترَح
    scr3._apply_iep_suggestion(iep_row, force=True)
    assert Decimal(iep_row.form.values()["taux"]) == Decimal("0.10")
    assert not iep_row._iep_manual
    print("[selftest] الأقدمية: اقتراح 0.10 · وسم «معدَّلة يدوياً» · عودة للمقترَح")

    # تحت الحدّ الأدنى → 0% مع السبب
    scr3._header.set_values({"employe_date_entree": "2026-03-01"})
    scr3._apply_iep_suggestion(iep_row, force=True)
    assert Decimal(iep_row.form.values()["taux"]) == 0
    assert "الحدّ الأدنى" in iep_row._iep_hint.text()
    print("[selftest] الأقدمية: تحت الحدّ الأدنى → 0% مع السبب")

    # السطر الحرّ: V7 + القفز للمناطق الأربع
    scr4 = BulletinScreen(conn=conn)
    scr4._menu  # القائمة تحوي «سطر حرّ»
    assert "libre" in _b.lignes.LINE_TYPES
    scr4._rows[0].form.set_values({"montant": "40000"})
    scr4._header.set_values({"employe_nom": "LIBRE ت", "periode": "2026-09"})
    scr4.add_line("libre")
    lib = scr4._rows[-1]
    lib.form.set_values({"libelle": "منحة خاصة", "montant": "3000"})
    scr4.recompute()
    # غير مصنَّف → لا يُحتسَب + شريط V7
    assert "libre" not in [l.key for l in scr4._view.lignes]
    assert "V7" in lib._libre_hint.text()
    _captured.clear()
    assert scr4.save() is None
    assert any("V7" in t for t, _ in _captured), _captured
    print("[selftest] السطر الحرّ: بلا تصنيف → لا يُحتسَب + save مُنِع (V7)")

    for cot, imp, ret, want in (("نعم", "نعم", "لا", "Z1"),
                                ("لا", "نعم", "لا", "Z2"),
                                ("لا", "لا", "لا", "Z3"),
                                ("لا", "لا", "نعم", "Z4")):
        lib.form.set_values({"cotisable": cot, "imposable": imp,
                             "est_retenue": ret})
        scr4.recompute()
        got = next(l.zone for l in scr4._view.lignes if l.key == "libre")
        assert got == want, (cot, imp, ret, got, want)
    print("[selftest] السطر الحرّ: القفز للمناطق الأربع Z1/Z2/Z3/Z4 صحيح")

    # #2 — V3: صافٍ سالب يُمنع حفظه وتثبيته، بلا أثر جانبي
    def _count_bulletins():
        return conn.execute("SELECT COUNT(*) FROM bulletin").fetchone()[0]

    scr5 = BulletinScreen(conn=conn)
    scr5._header.set_values({"employe_nom": "V3 ت", "periode": "2026-09"})
    scr5._rows[0].form.set_values({"montant": "20000"})
    scr5.add_line("avance")
    scr5._rows[-1].form.set_values({"montant": "25000"})
    scr5.recompute()
    assert scr5._view.e < 0, scr5._view.e
    n_b = _count_bulletins()
    _captured.clear()
    assert scr5.save() is None, "V3 لم تمنع الحفظ"
    assert any("V3" in t for t, _ in _captured), _captured
    assert _count_bulletins() == n_b, "V3: صفّ كشف رغم الرفض"
    print(f"[selftest] #2: V3 صافٍ سالب ({scr5._view.e}) → حفظ وتثبيت ممنوعان")

    # #5 — نوع فريد لا يُضاف مرّتين (القائمة تعطّله)
    scr6 = BulletinScreen(conn=conn)
    scr6.add_line("panier")
    scr6.add_line("panier")
    assert [r.type_key for r in scr6._rows].count("panier") == 1
    scr6.add_line("avance")
    scr6.add_line("avance")               # التسبيق متكرّر
    assert [r.type_key for r in scr6._rows].count("avance") == 2
    print("[selftest] #5: النوع الفريد لا يتكرّر · التسبيق يتكرّر")

    # #4 — سطر بلا قيمة: لا يُحتسَب + تنبيه «أدخل القيمة»
    scr7 = BulletinScreen(conn=conn)
    scr7._rows[0].form.set_values({"montant": "40000"})
    scr7.add_line("nuit")
    scr7.recompute()
    assert "nuit" not in [l.key for l in scr7._view.lignes]
    assert not scr7._rows[-1].is_filled()
    assert not scr7._rows[-1]._warn.isHidden()      # ظاهر (لا يعتمد على عرض النافذة)
    print("[selftest] #4: سطر بلا قيمة → غير محتسَب + تنبيه «أدخل القيمة»")

    # ===== الكوميت 2 — عرض وتصميم =====
    from programme.payroll.calc import fmt_montant       # المصدر الوحيد

    # #10 — صيغة عربية موحّدة: فاصل آلاف مسافة، فاصلة عشرية
    assert fmt_montant(Decimal("25000")) == "25 000,00", fmt_montant(Decimal("25000"))
    # #11 — صفرٌ بلا إشارة سالبة
    assert fmt_montant(Decimal("0")) == "0,00"
    assert fmt_montant(Decimal("-0.00")) == "0,00"

    scr8 = BulletinScreen(conn=conn)
    scr8._rows[0].form.set_values({"montant": "25000"})   # [C] < 30 000 → [D]=0
    scr8._header.set_values({"employe_nom": "عرض ت", "periode": "2026-09"})
    scr8.recompute()
    rrows = scr8._result._model._rows
    # #8 — الترتيب: الأجر القاعدي أولاً، [E] أخيراً (الفرز مُعطَّل)
    assert not rrows[0].get("_sys"), rrows[0]              # أوّل سطر ليس نظامياً
    assert "🔒" not in rrows[0]["libelle"]
    assert rrows[-1]["_sys"] == "E", rrows[-1]
    assert [r.get("_sys") for r in rrows if r.get("_sys")] == \
        ["A", "B", "C", "D", "E"], rrows
    assert scr8._result._view.isSortingEnabled() is False
    # #12 — عمود المنطقة للأسطر النظامية يعرض [A]..[E]
    sysrows = {r["_sys"]: r for r in rrows if r.get("_sys")}
    assert sysrows["A"]["zone"] == "[A]", sysrows["A"]
    assert sysrows["D"]["zone"] == "[D]"
    # #11 — [D] = 0 → «0,00» بلا «−»
    assert sysrows["D"]["montant"] == "0,00", sysrows["D"]["montant"]
    # #10 — كل المبالغ بالفاصلة العشرية
    assert "," in sysrows["A"]["montant"] and "." not in sysrows["A"]["montant"]
    # #9 — نمط السطر النظامي: خلفية + خط أثقل + فاصل (عدا [D] الملاصق لـ[C])
    stA = scr8._result._model._row_style(sysrows["A"])
    stD = scr8._result._model._row_style(sysrows["D"])
    assert stA["bold"] and stA["separator_above"]
    assert stD["bold"] and stD["separator_above"] is False
    print("[selftest] #8/#9/#10/#11/#12: ترتيب ثابت · أسطر نظامية مميَّزة · "
          "صيغة عربية · [A]..[E] في عمود المنطقة")

    print("[selftest] ALLOK")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    conn = _make_db()
    win = build_gallery(conn)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
