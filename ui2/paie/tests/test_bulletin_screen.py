"""اختبار تثبيت (pinning) لشاشة توليد الكشف — قبل إعادة بنائها فوق
``ui2/screen.py``.

يثبّت **السلوك الحالي كما هو** (لا كما ينبغي أن يكون): يشغّل المسارات
عبر :class:`ui2.paie.bulletin.BulletinScreen` نفسها — لا عبر المحرّك
مباشرةً — فيلتقط تفاعل الشاشة (طيّ الأسطر، اشتقاق المناطق، حرّاس V2/V3/
V7/V15/V16، شريط الاتفاقية، منع تكرار الأنواع الفريدة) وليس فقط الحساب.

القيَم الرقمية مأخوذة من تشغيل الشاشة فعلياً على ``params_2026.json``
والاتفاقية الافتراضية (v1 مؤكَّدة تلقائياً، قيَم DEFAULT). أي تغيّر فيها
أثناء إعادة البناء = انحدار يجب أن يوقفنا.

التشغيل:
    python -m unittest discover -s ui2/paie/tests
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import sqlite3
import tempfile
import unittest
from decimal import Decimal

try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except Exception:                                    # noqa: BLE001
    _HAS_QT = False

if _HAS_QT:
    import ui2.paie.bulletin as bulletin_mod
    from programme import paths
    from programme.payroll import repository
    from ui2 import theme
    from ui2.paie.bulletin import BulletinScreen


def _fresh_db(dirpath: str) -> sqlite3.Connection:
    """قاعدة نظيفة على القرص (ملف لكل اختبار): هجرات + زبون افتراضي
    (اتفاقية v1 مؤكَّدة تلقائياً) — نفس تهيئة ``ui2/paie/__main__`` والمعرض."""
    path = os.path.join(dirpath, "pin.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    repository.run_migrations(conn)
    repository.ensure_default_client(conn=conn)
    return conn


@unittest.skipUnless(_HAS_QT, "PySide6 غير متوفّر")
class BulletinScreenPin(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        theme.apply_theme(cls.app)

    def setUp(self):
        # التقاط صناديق الرسائل بدل عرضها (تُوقف التشغيل بلا شاشة)
        self.captured = []
        self._orig_warn = bulletin_mod.warn
        self._orig_confirm = bulletin_mod.confirm
        bulletin_mod.warn = lambda _p, title, lines: self.captured.append(
            (title, list(lines)))
        bulletin_mod.confirm = lambda *_a, **_k: True     # تأكيد الحذف: نعم
        self._tmp = tempfile.mkdtemp(prefix="om_pin_")
        # عزل ملفات المسوّدة في مجلد الاختبار (بدل جذر المستودع)
        os.environ[paths._LOCAL_STATE_ENV_OVERRIDE] = self._tmp
        self.conn = _fresh_db(self._tmp)
        self.scr = BulletinScreen(conn=self.conn)

    def tearDown(self):
        bulletin_mod.warn = self._orig_warn
        bulletin_mod.confirm = self._orig_confirm
        os.environ.pop(paths._LOCAL_STATE_ENV_OVERRIDE, None)
        self.scr.deleteLater()
        self.conn.close()
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------ أدوات
    def _line(self, idx, **vals):
        self.scr._rows[idx].form.set_values({k: str(v) for k, v in vals.items()})

    def _add(self, key, **vals):
        self.scr.add_line(key)
        if vals:
            self._line(len(self.scr._rows) - 1, **vals)

    def _count_bulletins(self):
        return self.conn.execute("SELECT COUNT(*) FROM bulletin").fetchone()[0]

    def _zone(self, key):
        return next((l.zone for l in self.scr._view.lignes if l.key == key), None)

    # ============================================================ BOUCETTA
    def test_boucetta_full_scenario_through_screen(self):
        """كشف BOUCETTA الحقيقي، مُدخَل عبر الشاشة: قاعدي 27 472,53 ·
        ساعات غياب 72 · تأخّر 11,38 · إضافية 100% 7,88 · سلة 2 500 ·
        نقل 2 500 (§5.5 / CHANGELOG مرجع 38)."""
        self._line(0, montant="27472.53")
        self._add("abs_heures", heures="72")
        self._add("retard", heures="11.38")
        self._add("hs_100", heures="7.88")
        self._add("panier", montant_mensuel="2500")
        self._add("transport", montant_mensuel="2500")
        self.scr._header.set_values(
            {"employe_nom": "BOUCETTA", "periode": "2026-09"})
        self.scr.recompute()
        v = self.scr._view

        self.assertEqual(v.a, Decimal("16754.86"))
        self.assertEqual(v.b, Decimal("1507.94"))
        self.assertEqual(v.c, Decimal("18169.96"))
        self.assertEqual(v.d, Decimal("0.00"))
        self.assertEqual(v.e, Decimal("18169.96"))
        self.assertEqual(v.result.heures_presence, Decimal("101.33"))

        # حصّة كل سطر (المحرّك بدقّة كاملة × كمّية السطر ثم da مرّة واحدة)
        montants = {l.key: (l.montant, l.zone, l.sens) for l in v.lignes}
        self.assertEqual(montants["salaire_base"],
                         (Decimal("27472.53"), "Z1", "GAIN"))
        self.assertEqual(montants["abs_heures"],
                         (Decimal("11411.89"), "Z1", "RETENUE"))
        self.assertEqual(montants["retard"],
                         (Decimal("1803.71"), "Z1", "RETENUE"))
        self.assertEqual(montants["hs_100"],
                         (Decimal("2497.93"), "Z1", "GAIN"))
        self.assertEqual(montants["panier"],
                         (Decimal("1461.52"), "Z2", "GAIN"))
        self.assertEqual(montants["transport"],
                         (Decimal("1461.52"), "Z2", "GAIN"))
        # السلة = النقل (§1.2.3، تنسيب بالسنتيم)
        self.assertEqual(montants["panier"][0], montants["transport"][0])

        # مجموع أسطر Z1 المعروضة (بإشارتها) = [A] بالضبط
        z1_signed = sum(
            ((l.montant if l.sens == "GAIN" else -l.montant)
             for l in v.lignes if l.zone == "Z1"), Decimal("0"))
        self.assertEqual(z1_signed, v.a)

        # ترتيب صفوف جدول الكشف ثابت (الفرز مُعطَّل)
        rows = self.scr._result._model._rows
        sys_seq = [r.get("_sys") for r in rows if r.get("_sys")]
        self.assertEqual(sys_seq, ["A", "B", "C", "D", "E"])
        self.assertFalse(self.scr._result._view.isSortingEnabled())
        # أوّل صف ليس نظامياً (الأجر القاعدي)، آخر صف [E]
        self.assertIsNone(rows[0].get("_sys"))
        self.assertEqual(rows[-1].get("_sys"), "E")

    # ============================================ قفز الأسطر إلى المناطق الأربع
    def test_free_line_jumps_to_four_zones(self):
        self._line(0, montant="40000")
        self._add("libre")
        lib = self.scr._rows[-1]
        for cot, imp, ret, want in (("نعم", "نعم", "لا", "Z1"),
                                    ("لا", "نعم", "لا", "Z2"),
                                    ("لا", "لا", "لا", "Z3"),
                                    ("لا", "لا", "نعم", "Z4")):
            lib.form.set_values({"libelle": "خاص", "montant": "3000",
                                 "cotisable": cot, "imposable": imp,
                                 "est_retenue": ret})
            self.scr.recompute()
            self.assertEqual(self._zone("libre"), want, (cot, imp, ret))

    # ================================================================= V3
    def test_v3_negative_net_blocks_save_and_fige_no_orphan(self):
        self._line(0, montant="20000")
        self._add("avance", montant="25000")
        self.scr._header.set_values(
            {"employe_nom": "V3", "periode": "2026-09"})
        self.scr.recompute()
        self.assertEqual(self.scr._view.e, Decimal("-7160.00"))

        before = self._count_bulletins()
        self.captured.clear()
        self.assertIsNone(self.scr.save())
        self.assertTrue(any("V3" in t for t, _ in self.captured), self.captured)
        self.assertEqual(self._count_bulletins(), before)     # لا صفّ كشف

        self.captured.clear()
        self.scr.fige()                                        # قبل أي حفظ
        self.assertTrue(any(t for t, _ in self.captured))

    # ================================================================= V7
    def test_v7_unclassified_free_line_not_counted_and_blocks_save(self):
        self._line(0, montant="40000")
        self.scr._header.set_values(
            {"employe_nom": "V7", "periode": "2026-09"})
        self._add("libre")
        self.scr._rows[-1].form.set_values(
            {"libelle": "منحة", "montant": "3000"})
        self.scr.recompute()
        # غير مصنَّف → لا يظهر في العرض ولا يُحتسَب
        self.assertNotIn("libre", [l.key for l in self.scr._view.lignes])

        self.captured.clear()
        self.assertIsNone(self.scr.save())
        self.assertTrue(any("V7" in t for t, _ in self.captured), self.captured)

    # ================================================================ V15
    def test_v15_unconfirmed_convention_blocks_save_no_orphan_rows(self):
        rid = repository.create_entreprise(
            {"raison_sociale": "SARL غير مؤكَّدة", "transient": 0},
            conn=self.conn)
        repository.seed_catalogue(rid, conn=self.conn)
        repository.create_convention(rid, {}, conn=self.conn)   # confirme=0

        scr2 = BulletinScreen(conn=self.conn)
        scr2._client_id = rid
        scr2._header.set_values(
            {"employe_nom": "فلان", "periode": "2026-09"})
        scr2._rows[0].form.set_values({"montant": "40000"})
        scr2.recompute()

        n_ent = len(repository.list_entreprises(actif_only=False, conn=self.conn))
        n_emp = len(repository.list_employes(rid, conn=self.conn))
        self.captured.clear()
        self.assertIsNone(scr2.save())
        self.assertTrue(any("V15" in t for t, _ in self.captured), self.captured)
        # لا صفّ entreprise/employe يتيم بعد الرفض
        self.assertEqual(
            len(repository.list_entreprises(actif_only=False, conn=self.conn)),
            n_ent)
        self.assertEqual(
            len(repository.list_employes(rid, conn=self.conn)), n_emp)
        scr2.deleteLater()

    # ================================================================ V16
    def test_v16_period_without_params_blocks_save_no_orphan(self):
        self.scr._header.set_values(
            {"employe_nom": "V16", "periode": "1990-01"})
        self.scr._rows[0].form.set_values({"montant": "40000"})
        self.scr.recompute()

        n_ent = len(repository.list_entreprises(actif_only=False, conn=self.conn))
        self.captured.clear()
        self.assertIsNone(self.scr.save())
        self.assertTrue(any("V16" in t for t, _ in self.captured), self.captured)
        self.assertEqual(
            len(repository.list_entreprises(actif_only=False, conn=self.conn)),
            n_ent)

    # ============================================= V2 + شريط الاتفاقية
    def test_v2_warning_and_unreviewed_convention_bar(self):
        """أجر فوق SNMG يهبط وعاؤه دون الأرضية بسبب الغياب → تحذير V2
        (لا رفع تلقائي)، وشريط «الاتفاقية لم تُراجَع» ظاهر للاتفاقية
        الافتراضية (نسخة 1)."""
        self._line(0, montant="24500")
        self._add("abs_jours", jours="10")
        self.scr._header.set_values(
            {"employe_nom": "V2", "periode": "2026-09"})
        self.scr.recompute()

        av = self.scr._view.avertissements
        self.assertTrue(any(m.startswith("V2") for m in av), av)
        joined = " ".join(av)
        self.assertIn("أرضية SNMG 24000.00", joined)
        self.assertIn("فرق 7666.67", joined)

        self.assertFalse(self.scr._warnbar.isHidden())
        self.assertIn("لم تُراجَع", self.scr._warnbar.text())

    # ================================ منع تكرار الأنواع الفريدة
    def test_unique_line_types_not_duplicated(self):
        self.scr.add_line("panier")
        self.scr.add_line("panier")                       # فريد → يُتجاهَل
        self.scr.add_line("avance")
        self.scr.add_line("avance")                       # قابل للتكرار
        keys = [r.type_key for r in self.scr._rows]
        self.assertEqual(keys.count("panier"), 1)
        self.assertEqual(keys.count("avance"), 2)

    # ==================== المهمة ج/5: حفظ المسوّدة التلقائي ====================
    def test_draft_autosave_close_and_restore_roundtrip(self):
        """إغلاق الشاشة بتعديل غير محفوظ ثم إعادة فتحها يستعيد نفس الحالة."""
        self.scr._header.set_values(
            {"employe_nom": "مسوّدة تجريبية", "periode": "2026-09",
             "employe_date_entree": "2018-03-01"})
        self._line(0, montant="41250")
        self._add("panier", montant_mensuel="2500")
        self.assertTrue(self.scr.has_unsaved_changes())

        self.scr.on_deactivate()                          # = إغلاق → flush_draft
        self.scr.deleteLater()

        scr2 = BulletinScreen(conn=self.conn)
        self.assertFalse(scr2.has_unsaved_changes())      # قبل الاستعادة
        restored = scr2.maybe_restore_draft(ask=lambda: True)
        self.assertTrue(restored)

        hv = scr2._header.values()
        self.assertEqual(hv["employe_nom"], "مسوّدة تجريبية")
        self.assertEqual(hv["periode"], "2026-09")
        self.assertEqual(hv["employe_date_entree"], "2018-03-01")
        by_type = {r.type_key: r.form.values() for r in scr2._rows}
        self.assertEqual(by_type["salaire_base"]["montant"], "41250")
        self.assertEqual(by_type["panier"]["montant_mensuel"], "2500")
        self.assertTrue(scr2.has_unsaved_changes())       # مسوّدة مستعادة = غير محفوظة
        scr2.deleteLater()

    def test_successful_save_clears_unsaved_flag_and_draft(self):
        self.scr._header.set_values(
            {"employe_nom": "حفظ ناجح", "periode": "2026-09"})
        self._line(0, montant="45000")
        self.scr.recompute()
        self.assertTrue(self.scr.has_unsaved_changes())
        self.scr.flush_draft()
        self.assertTrue(os.path.exists(
            os.path.join(self._tmp, "paie_draft.json")))

        bid = self.scr.save()
        self.assertIsNotNone(bid)
        self.assertFalse(self.scr.has_unsaved_changes())
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp, "paie_draft.json")))

    def test_invalid_date_cannot_be_typed_freely(self):
        """حقل التاريخ الآن ``kind="date"`` — ``values()`` يردّ دائماً
        ISO صالحاً أو "" (لا «13/01/2016» صامتة)."""
        w = self.scr._header.widget("employe_date_entree")
        w.set_iso("13/01/2016")                           # صيغة خاطئة
        self.assertEqual(self.scr._header.values()["employe_date_entree"], "")
        w.set_iso("2016-01-13")
        self.assertEqual(
            self.scr._header.values()["employe_date_entree"], "2016-01-13")


if __name__ == "__main__":
    unittest.main()
