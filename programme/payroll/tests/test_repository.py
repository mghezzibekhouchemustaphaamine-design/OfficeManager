"""اختبارات طبقة القراءة/الكتابة لوحدة الأجور (``programme.payroll.repository``).

كل اختبار يفتح قاعدة ``:memory:`` مستقلّة ويشغّل الهجرات عليها — لا مساس
بقاعدة المكتب الحقيقية. يُغطّى:

  • دورة كاملة: شركة → بذرة كتالوج → عامل → كشف بأسطره.
  • كل المبالغ المقروءة من القاعدة ترجع ``Decimal`` لا ``float``.
  • :func:`transaction` تتراجع كلّياً عند فشل أي سطر (لا كشف يتيم).
  • قيود التصميم: convention غير قابلة للتعديل، cotisable/imposable إلزاميان.
"""
import sqlite3
import unittest
from decimal import Decimal

from programme.payroll import repository as repo


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    applied = repo.run_migrations(conn)
    assert applied == [1, 2, 3, 4, 5], applied  # قاعدة جديدة: 1..5 بالترتيب
    return conn


class TestRepositoryCycle(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_db()

    def tearDown(self):
        self.conn.close()

    # ---------------------------------------------------------------
    def test_full_cycle_company_catalogue_employe_bulletin(self):
        c = self.conn

        ent_id = repo.create_entreprise(
            {"raison_sociale": "SARL Test", "nif": "000000000000001",
             "num_employeur_cnas": "12345678"}, conn=c)
        self.assertIsInstance(ent_id, int)
        self.assertEqual(repo.get_entreprise(ent_id, conn=c)["raison_sociale"],
                         "SARL Test")
        self.assertEqual([e["id"] for e in repo.list_entreprises(conn=c)],
                         [ent_id])

        # --- بذرة الكتالوج (SPEC §2.2) ---
        n = repo.seed_catalogue(ent_id, conn=c)
        self.assertEqual(n, 19)  # 23 ناقص 4 رُبريكات حُذفت (يغطّيها السطر الحرّ)
        self.assertEqual(repo.seed_catalogue(ent_id, conn=c), 0)  # لا تكرار

        rubs = repo.list_rubriques(ent_id, conn=c)
        self.assertEqual(len(rubs), 19)
        by_code = {r["code"]: r for r in rubs}
        # حُذفت نهائياً: منطقة · إنابة · تعاضدية · اقتطاع قضائي
        for code in ("3000", "1080", "5000", "5020"):
            self.assertNotIn(code, by_code)
        # السلة والنقل: معفاتان من CNAS، خاضعتان لـ IRG (SPEC §2.2)
        self.assertEqual((by_code["2000"]["cotisable"],
                          by_code["2000"]["imposable"]), (0, 1))
        self.assertEqual((by_code["2010"]["cotisable"],
                          by_code["2010"]["imposable"]), (0, 1))
        # الأجر القاعدي: خاضع للاثنين
        self.assertEqual((by_code["1000"]["cotisable"],
                          by_code["1000"]["imposable"]), (1, 1))
        # المنح العائلية: لا اشتراك ولا ضريبة
        self.assertEqual((by_code["3010"]["cotisable"],
                          by_code["3010"]["imposable"]), (0, 0))
        # اقتطاع غياب غير مبرر: سالب على الوعاءين
        self.assertEqual((by_code["4010"]["sens"], by_code["4010"]["cotisable"],
                          by_code["4010"]["imposable"]), ("RETENUE", 1, 1))
        self.assertTrue(all(r["regime_irg"] == "BAREME" for r in rubs))
        self.assertIsInstance(by_code["1000"]["base_calcul"], list)
        # CNAS/IRG ليسا رُبريكتين في الكتالوج
        self.assertNotIn("CNAS", by_code)
        self.assertNotIn("IRG", by_code)

        # --- الاتفاقية + تأكيدها ---
        conv_id = repo.create_convention(
            ent_id, {"taux_hs_jour": Decimal("1.50"),
                     "taux_hs_nuit": Decimal("2.00"),
                     "taux_hs_ferie": Decimal("2.00")}, conn=c)
        self.assertIsInstance(conv_id, int)
        conv = repo.get_active_convention(ent_id, conn=c)
        self.assertEqual(conv["version"], 1)
        self.assertEqual(conv["confirme"], 0)
        self.assertIsInstance(conv["taux_hs_jour"], Decimal)

        confirmed_id = repo.confirm_convention(ent_id, conn=c)
        self.assertNotEqual(confirmed_id, conv_id)  # نسخة جديدة لا تعديل
        conv2 = repo.get_active_convention(ent_id, conn=c)
        self.assertEqual(conv2["version"], 2)
        self.assertEqual(conv2["confirme"], 1)
        self.assertEqual(repo.confirm_convention(ent_id, conn=c), confirmed_id)
        self.assertEqual(len(repo.list_conventions(ent_id, conn=c)), 2)

        # --- العامل ---
        emp_id = repo.create_employe(
            ent_id, {"nom": "MGHEZZI", "prenom": "Amine",
                     "num_ss": "212345678901234",
                     "salaire_base": Decimal("45000.50"),
                     "taux_iep": Decimal("0.08"),
                     "temps_partiel_ratio": Decimal("1"),
                     "nb_enfants": 2, "type_contrat": "CDI"}, conn=c)
        emp = repo.get_employe(emp_id, conn=c)
        self.assertEqual(emp["nom"], "MGHEZZI")
        self.assertEqual(emp["salaire_base"], Decimal("45000.50"))
        self.assertEqual([e["id"] for e in repo.list_employes(ent_id, conn=c)],
                         [emp_id])

        # --- الكشف + أسطره في معاملة واحدة ---
        bulletin = {
            "employe_id": emp_id, "periode": "2026-09", "type": "NORMAL",
            "etat": "CALCULE", "params_version": "2026.1",
            "convention_version": 2,
            "total_a": Decimal("48600.54"), "total_b": Decimal("4374.05"),
            "total_c": Decimal("47226.49"), "total_d": Decimal("5580.00"),
            "net_e": Decimal("41646.49"),
            "avertissements_json": ["V2: exemple d'avertissement"],
        }
        lignes = [
            {"ordre_affichage": 0, "zone": "Z1", "code_snapshot": "1000",
             "libelle_snapshot": "Salaire de base", "sens_snapshot": "GAIN",
             "cotisable_snapshot": 1, "imposable_snapshot": 1,
             "regime_irg_snapshot": "BAREME",
             "montant": Decimal("45000.50")},
            {"ordre_affichage": 1, "zone": "SYSTEME", "ligne_systeme": "A",
             "code_snapshot": "[A]", "libelle_snapshot": "SALAIRE DE POSTE",
             "sens_snapshot": "GAIN", "montant": Decimal("48600.54")},
            {"ordre_affichage": 2, "zone": "SYSTEME", "ligne_systeme": "B",
             "code_snapshot": "[B]", "libelle_snapshot": "CNAS 9%",
             "sens_snapshot": "RETENUE", "taux": Decimal("0.09"),
             "base": Decimal("48600.54"), "montant": Decimal("4374.05")},
        ]
        bid = repo.create_bulletin(bulletin, lignes, conn=c)
        got = repo.get_bulletin(bid, conn=c)
        self.assertEqual(got["periode"], "2026-09")
        self.assertEqual(len(got["lignes"]), 3)
        self.assertEqual(got["avertissements_json"],
                         ["V2: exemple d'avertissement"])

        # --- التثبيت يولّد رقم السلسلة ---
        numero = repo.fige_bulletin(bid, conn=c)
        self.assertEqual(numero, f"PAIE-2026-09-{bid:05d}")
        figed = repo.get_bulletin(bid, conn=c)
        self.assertEqual(figed["etat"], "FIGE")
        self.assertIsNotNone(figed["fige_at"])
        self.assertEqual(repo.fige_bulletin(bid, conn=c), numero)  # idempotent

    # ---------------------------------------------------------------
    def test_amounts_return_decimal_never_float(self):
        c = self.conn
        ent_id = repo.create_entreprise({"raison_sociale": "X"}, conn=c)
        repo.create_convention(ent_id, {}, conn=c)
        emp_id = repo.create_employe(
            ent_id, {"nom": "Y", "salaire_base": Decimal("30000.33"),
                     "taux_iep": Decimal("0.05")}, conn=c)

        emp = repo.get_employe(emp_id, conn=c)
        for field in ("salaire_base", "taux_iep", "temps_partiel_ratio"):
            self.assertIsInstance(emp[field], Decimal, field)
            self.assertNotIsInstance(emp[field], float, field)
        self.assertEqual(emp["salaire_base"], Decimal("30000.33"))

        conv = repo.get_active_convention(ent_id, conn=c)
        for field in ("taux_hs_jour", "taux_hs_nuit", "taux_hs_ferie"):
            self.assertIsInstance(conv[field], Decimal, field)

        bid = repo.create_bulletin(
            {"employe_id": emp_id, "periode": "2026-01",
             "params_version": "2026.1", "convention_version": 1,
             "total_a": Decimal("30000.33"), "net_e": Decimal("25123.45")},
            [{"ordre_affichage": 0, "zone": "Z1", "code_snapshot": "1000",
              "libelle_snapshot": "Base", "sens_snapshot": "GAIN",
              "base": Decimal("30000.33"), "taux": Decimal("1"),
              "montant": Decimal("30000.33")}],
            conn=c)
        got = repo.get_bulletin(bid, conn=c)
        for field in ("total_a", "total_b", "net_e"):
            self.assertIsInstance(got[field], Decimal, field)
            self.assertNotIsInstance(got[field], float, field)
        for field in ("base", "taux", "montant"):
            self.assertIsInstance(got["lignes"][0][field], Decimal, field)
            self.assertNotIsInstance(got["lignes"][0][field], float, field)

        # القيمة كما خُزّنت نصّاً — بلا انزياح ثنائي
        raw = c.execute("SELECT salaire_base FROM employe WHERE id = ?",
                        (emp_id,)).fetchone()[0]
        self.assertEqual(raw, "30000.33")
        self.assertIsInstance(raw, str)

    def test_float_rejected_on_write(self):
        c = self.conn
        ent_id = repo.create_entreprise({"raison_sociale": "F"}, conn=c)
        with self.assertRaises(TypeError):
            repo.create_employe(ent_id, {"nom": "Z", "salaire_base": 45000.5},
                                conn=c)

    # ---------------------------------------------------------------
    def test_transaction_rolls_back_on_error(self):
        """كشف بثلاثة أسطر، الثالث يخرق ``CHECK`` (zone غير صالحة). يجب
        ألّا يبقى أثر: لا صف في ``bulletin`` ولا في ``bulletin_ligne``."""
        c = self.conn
        ent_id = repo.create_entreprise({"raison_sociale": "RB"}, conn=c)
        emp_id = repo.create_employe(ent_id, {"nom": "RB"}, conn=c)

        bulletin = {"employe_id": emp_id, "periode": "2026-05",
                    "params_version": "2026.1", "convention_version": 1,
                    "net_e": Decimal("1000")}
        lignes = [
            {"ordre_affichage": 0, "zone": "Z1", "code_snapshot": "1000",
             "libelle_snapshot": "ok1", "sens_snapshot": "GAIN",
             "montant": Decimal("100")},
            {"ordre_affichage": 1, "zone": "Z1", "code_snapshot": "1010",
             "libelle_snapshot": "ok2", "sens_snapshot": "GAIN",
             "montant": Decimal("200")},
            {"ordre_affichage": 2, "zone": "ZONE_INVALIDE",
             "code_snapshot": "x", "libelle_snapshot": "bad",
             "sens_snapshot": "GAIN", "montant": Decimal("300")},
        ]
        with self.assertRaises(sqlite3.IntegrityError):
            repo.create_bulletin(bulletin, lignes, conn=c)

        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM bulletin").fetchone()[0], 0)
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM bulletin_ligne").fetchone()[0], 0)
        self.assertEqual(repo.list_bulletins(emp_id, conn=c), [])

    def test_systeme_lignes_doivent_matcher_les_totaux(self):
        """حارس التباعد (§2.3.1): سطر نظامي [A]..[E] لا يطابق
        total_a..net_e → ``ValueError`` قبل أي كتابة."""
        c = self.conn
        ent_id = repo.create_entreprise({"raison_sociale": "SG"}, conn=c)
        emp_id = repo.create_employe(ent_id, {"nom": "SG"}, conn=c)
        bull = {"employe_id": emp_id, "periode": "2026-04",
                "params_version": "2026.1", "convention_version": 1,
                "total_a": Decimal("50000.00"), "total_b": Decimal("4500.00"),
                "total_c": Decimal("45500.00"), "total_d": Decimal("6000.00"),
                "net_e": Decimal("39500.00")}
        good = [{"ordre_affichage": i, "zone": "SYSTEME", "ligne_systeme": code,
                 "code_snapshot": f"[{code}]", "libelle_snapshot": code,
                 "sens_snapshot": "GAIN", "montant": m}
                for i, (code, m) in enumerate(
                    [("A", Decimal("50000.00")), ("B", Decimal("4500.00")),
                     ("C", Decimal("45500.00")), ("D", Decimal("6000.00")),
                     ("E", Decimal("39500.00"))])]
        # مطابق → ينجح
        bid = repo.create_bulletin(bull, good, conn=c)
        self.assertIsInstance(bid, int)

        # [C] مُتباعد بسنتيم → يُرفَض، ولا صفّ جديد
        bad = [dict(g) for g in good]
        bad[2]["montant"] = Decimal("45500.01")
        n_before = c.execute("SELECT COUNT(*) FROM bulletin").fetchone()[0]
        with self.assertRaises(ValueError):
            repo.create_bulletin(
                dict(bull, periode="2026-05"), bad, conn=c)
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM bulletin").fetchone()[0], n_before)

    def test_transaction_own_connection_commits_then_closes(self):
        """مسار ``conn=None``: :func:`transaction` تفتح اتصالاً عبر
        ``programme.database.get_connection``، ثم ``commit`` عند النجاح و
        ``rollback`` عند الخطأ، و``close`` في الحالتين."""
        import unittest.mock as mock

        made = []

        def fake_get_connection():
            k = sqlite3.connect(":memory:")
            k.row_factory = sqlite3.Row
            k.execute("CREATE TABLE t (v INTEGER CHECK (v IN (0, 1)))")
            k.commit()
            spy = mock.Mock(wraps=k)
            made.append(spy)
            return spy

        with mock.patch("programme.database.get_connection",
                        side_effect=fake_get_connection):
            with repo.transaction(None) as tconn:
                tconn.execute("INSERT INTO t (v) VALUES (1)")
            made[-1].commit.assert_called()
            made[-1].close.assert_called()

            with self.assertRaises(sqlite3.IntegrityError):
                with repo.transaction(None) as tconn:
                    tconn.execute("INSERT INTO t (v) VALUES (9)")
            made[-1].rollback.assert_called()
            made[-1].close.assert_called()

    # ---------------------------------------------------------------
    def test_convention_is_immutable(self):
        c = self.conn
        ent_id = repo.create_entreprise({"raison_sociale": "IMM"}, conn=c)
        repo.create_convention(ent_id, {}, conn=c)
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("UPDATE convention SET confirme = 1 "
                      "WHERE entreprise_id = ?", (ent_id,))
            c.commit()

    def test_rubrique_requires_explicit_cotisable_imposable(self):
        c = self.conn
        ent_id = repo.create_entreprise({"raison_sociale": "V7"}, conn=c)
        base = {"code": "9000", "libelle_fr": "x", "libelle_ar": "س",
                "sens": "GAIN", "mode": "MONTANT"}
        with self.assertRaises(ValueError):
            repo.create_rubrique(ent_id, dict(base, imposable=1), conn=c)
        with self.assertRaises(ValueError):
            repo.create_rubrique(ent_id, dict(base, cotisable=1), conn=c)
        # مع الاثنين صراحةً: ينجح
        rid = repo.create_rubrique(
            ent_id, dict(base, cotisable=0, imposable=1), conn=c)
        self.assertIsInstance(rid, int)

    def test_transient_column_and_promotion(self):
        """الهجرة 3: عمود transient + منتقي «مسجَّل» + الترقية."""
        c = self.conn
        reg = repo.create_entreprise(
            {"raison_sociale": "Enregistré", "transient": 0}, conn=c)
        tra = repo.create_entreprise(
            {"raison_sociale": "Passager", "transient": 1}, conn=c)

        regs = {e["id"] for e in repo.list_entreprises(registered_only=True,
                                                       conn=c)}
        self.assertIn(reg, regs)
        self.assertNotIn(tra, regs)
        allids = {e["id"] for e in repo.list_entreprises(conn=c)}
        self.assertEqual(allids, {reg, tra})

        repo.promote_entreprise(tra, conn=c)
        regs2 = {e["id"] for e in repo.list_entreprises(registered_only=True,
                                                        conn=c)}
        self.assertIn(tra, regs2)
        self.assertEqual(repo.get_entreprise(tra, conn=c)["transient"], 0)

    def test_m4_drops_dead_invoice_tables_on_fresh_db(self):
        """الهجرة 4: قاعدة جديدة → invoices/invoice_items غير موجودين
        (تُشغَّل قبل CREATE TABLE في init_db، والجدولان حُذفا من هناك)."""
        c = self.conn
        for tbl in ("invoices", "invoice_items"):
            self.assertIsNone(
                c.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name=?", (tbl,)).fetchone())
        # tasks/documents محجوزان — يبقيان
        for tbl in ("tasks", "documents"):
            pass  # لا يُنشئهما repository؛ init_db يفعل (خارج نطاق هذا الاختبار)

    def test_m4_refuses_to_drop_populated_invoice_table(self):
        """حارس الهجرة 4: جدول invoices فيه صفوف → RuntimeError، لا إسقاط."""
        c = self.conn
        c.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, x TEXT)")
        c.execute("INSERT INTO invoices (x) VALUES ('بيانات')")
        with self.assertRaises(RuntimeError):
            repo._m4_drop_dead_invoice_tables(c.cursor())
        # لم يُسقَط
        self.assertIsNotNone(
            c.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                      "AND name='invoices'").fetchone())
        self.assertEqual(
            c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0], 1)

    def test_m5_employe_nom_index_exists(self):
        """الهجرة 5: فهرس (entreprise_id, nom) على employe موجود."""
        c = self.conn
        idx = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' "
            "AND name='idx_employe_ent_nom'").fetchone()
        self.assertIsNotNone(idx)

    def test_get_employe_by_nom_direct_lookup(self):
        c = self.conn
        ent = repo.create_entreprise({"raison_sociale": "SARL X"}, conn=c)
        repo.create_employe(ent, {"nom": "بن علي", "taux_iep": "0.09"}, conn=c)
        repo.create_employe(ent, {"nom": "قاسمي"}, conn=c)
        other = repo.create_entreprise({"raison_sociale": "SARL Y"}, conn=c)
        repo.create_employe(other, {"nom": "بن علي", "taux_iep": "0.05"}, conn=c)

        hit = repo.get_employe_by_nom(ent, "بن علي", conn=c)
        self.assertIsNotNone(hit)
        self.assertEqual(str(hit["taux_iep"]), "0.09")           # لا يخلط الشركتين
        self.assertIsNone(repo.get_employe_by_nom(ent, "غير موجود", conn=c))

    def test_ensure_default_client_first_run(self):
        """أول تشغيل: زبون افتراضي + كتالوج + اتفاقية مؤكَّدة (V15 لا تمنع)."""
        c = self.conn
        self.assertEqual(repo.list_entreprises(registered_only=True, conn=c), [])
        cid = repo.ensure_default_client(conn=c)
        self.assertIsInstance(cid, int)
        # نداء ثانٍ لا يُنشئ زبوناً جديداً
        self.assertEqual(repo.ensure_default_client(conn=c), cid)
        self.assertEqual(
            len(repo.list_entreprises(registered_only=True, conn=c)), 1)
        self.assertEqual(len(repo.list_rubriques(cid, conn=c)), 19)
        conv = repo.get_active_convention(cid, conn=c)
        self.assertEqual(conv["confirme"], 1)
        self.assertEqual(conv["base_iep"], "SAL_BASE_BRUT")   # §1.2.1
        self.assertEqual(str(conv["taux_hs_jour"]), "1.50")

    def test_convention_blocks_bulletin_when_unconfirmed_is_caller_concern(self):
        """التخزين لا يمنع — منع V15 منطق واجهة. لكن نتأكّد أنّ الحقل
        المطلوب للفحص (confirme) يُقرأ صحيحاً."""
        c = self.conn
        ent_id = repo.create_entreprise({"raison_sociale": "V15"}, conn=c)
        repo.create_convention(ent_id, {}, conn=c)
        self.assertEqual(
            repo.get_active_convention(ent_id, conn=c)["confirme"], 0)
        repo.confirm_convention(ent_id, conn=c)
        self.assertEqual(
            repo.get_active_convention(ent_id, conn=c)["confirme"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
