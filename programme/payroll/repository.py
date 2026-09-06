"""طبقة قاعدة بيانات وحدة الأجور + نظام هجرات مرقّم.

جداول الأجور مستقلّة تماماً عن جداول CD/الزبائن (لا FOREIGN KEY بينها
وبينها). المخطّط الكامل: docs/specs/SCHEMA_PAIE.md.

نظام الهجرات (``_MIGRATIONS`` + جدول ``schema_migrations``) مستقلّ عن
``programme/database.py:init_db()``؛ الأخير يبقى مسؤولاً عن الجداول
المشتركة (CD/الزبائن/الدخول) — «الحالة الأساسية» السابقة لنظام الهجرات.

  - الهجرة 1: علامة نسخة فقط (بلا DDL).
  - الهجرة 2: جداول الأجور الست + الفهارس + trigger منع تعديل convention.

``run_migrations`` يُستدعى من بداية ``init_db()`` عبر استيراد محلّي.
هذه الوحدة **لا تستورد** ``tkinter`` ولا ``ui/`` ولا ``programme.database``
على مستوى الوحدة (الاستيراد محلّي عند الحاجة فقط).
"""
import sqlite3
from typing import Callable, List, Optional, Tuple

_TRACKING_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def _m1_baseline(cur: sqlite3.Cursor) -> None:
    """الهجرة 1 — علامة نسخة فقط. الجداول المشتركة (clients, cd_documents,
    hr_documents, users…) يُنشئها ``programme.database.init_db()`` — لا
    DDL هنا."""


# --- الهجرة 2: جداول الأجور (مطابقة docs/specs/SCHEMA_PAIE.md) ---
_M2_PAYROLL_DDL = """
-- 1. entreprise ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS entreprise (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    raison_sociale      TEXT    NOT NULL,
    forme_juridique     TEXT,
    nif                 TEXT,
    nis                 TEXT,
    rc                  TEXT,
    art_imposition      TEXT,
    num_employeur_cnas  TEXT,
    adresse             TEXT,
    gerant_nom          TEXT,
    gerant_qualite      TEXT,
    tel                 TEXT,
    actif               INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_entreprise_nif
    ON entreprise (nif) WHERE nif IS NOT NULL;

-- 2. convention (immuable) ---------------------------------------------
CREATE TABLE IF NOT EXISTS convention (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id                 INTEGER NOT NULL
                                    REFERENCES entreprise(id) ON DELETE RESTRICT,
    version                       INTEGER NOT NULL,
    confirme                      INTEGER NOT NULL DEFAULT 0
                                    CHECK (confirme IN (0, 1)),
    base_iep                      TEXT NOT NULL DEFAULT 'SAL_BASE_BRUT'
                                    CHECK (base_iep IN ('SAL_BASE_BRUT',
                                                        'SAL_BASE_APRES_ABSENCES')),
    base_pri                      TEXT NOT NULL DEFAULT 'SAL_BASE_BRUT'
                                    CHECK (base_pri IN ('SAL_BASE_BRUT',
                                                        'SAL_BASE_APRES_ABSENCES')),
    prorata_panier_transport      TEXT NOT NULL DEFAULT 'PRORATA_HEURES'
                                    CHECK (prorata_panier_transport IN ('AUCUN',
                                           'PRORATA_HEURES', 'PRORATA_JOURS')),
    retard_reduit_heures_presence INTEGER NOT NULL DEFAULT 0
                                    CHECK (retard_reduit_heures_presence IN (0, 1)),
    taux_hs_jour                  TEXT NOT NULL DEFAULT '1.50'
                                    CHECK (CAST(taux_hs_jour  AS REAL) >= 1.5),
    taux_hs_nuit                  TEXT NOT NULL DEFAULT '2.00'
                                    CHECK (CAST(taux_hs_nuit  AS REAL) >= 1.5),
    taux_hs_ferie                 TEXT NOT NULL DEFAULT '2.00'
                                    CHECK (CAST(taux_hs_ferie AS REAL) >= 1.5),
    created_at                    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (entreprise_id, version)
);
CREATE TRIGGER IF NOT EXISTS convention_no_update
BEFORE UPDATE ON convention
BEGIN
    SELECT RAISE(ABORT,
        'convention immuable — chaque changement = nouvelle ligne (version +1)');
END;
CREATE INDEX IF NOT EXISTS idx_convention_entreprise
    ON convention (entreprise_id, version DESC);

-- 3. rubrique_catalogue ---------------------------------------------------
CREATE TABLE IF NOT EXISTS rubrique_catalogue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id   INTEGER NOT NULL
                      REFERENCES entreprise(id) ON DELETE CASCADE,
    code            TEXT    NOT NULL,
    libelle_fr      TEXT    NOT NULL,
    libelle_ar      TEXT    NOT NULL,
    sens            TEXT    NOT NULL CHECK (sens IN ('GAIN', 'RETENUE')),
    mode            TEXT    NOT NULL CHECK (mode IN ('MONTANT', 'TAUX_SUR_BASE',
                                                    'QUANTITE_X_PU', 'FORMULE')),
    base_calcul     TEXT    NOT NULL DEFAULT '[]',
    cotisable       INTEGER NOT NULL CHECK (cotisable IN (0, 1)),
    imposable       INTEGER NOT NULL CHECK (imposable IN (0, 1)),
    regime_irg      TEXT    NOT NULL DEFAULT 'BAREME'
                      CHECK (regime_irg IN ('BAREME', 'TAUX_10')),
    proratisable    INTEGER NOT NULL DEFAULT 0 CHECK (proratisable IN (0, 1)),
    depend_de       TEXT    NOT NULL DEFAULT '[]',
    ordre_affichage INTEGER NOT NULL DEFAULT 0,
    actif           INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT,
    UNIQUE (entreprise_id, code)
);
CREATE INDEX IF NOT EXISTS idx_rubrique_entreprise
    ON rubrique_catalogue (entreprise_id);

-- 4. employe ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employe (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id        INTEGER NOT NULL
                           REFERENCES entreprise(id) ON DELETE RESTRICT,
    nom                  TEXT    NOT NULL,
    prenom               TEXT,
    num_ss               TEXT,
    date_entree          TEXT,
    poste                TEXT,
    classe_indice        TEXT,
    type_contrat         TEXT    CHECK (type_contrat IN ('CDI', 'CDD')),
    rib                  TEXT,
    salaire_base         TEXT    NOT NULL DEFAULT '0',
    taux_iep             TEXT,
    nb_enfants           INTEGER NOT NULL DEFAULT 0 CHECK (nb_enfants >= 0),
    temps_partiel_ratio  TEXT    NOT NULL DEFAULT '1',
    date_sortie          TEXT,
    actif                INTEGER NOT NULL DEFAULT 1 CHECK (actif IN (0, 1)),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_employe_entreprise
    ON employe (entreprise_id);

-- 5. bulletin ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS bulletin (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    employe_id           INTEGER NOT NULL
                           REFERENCES employe(id) ON DELETE RESTRICT,
    periode              TEXT    NOT NULL,
    type                 TEXT    NOT NULL DEFAULT 'NORMAL'
                           CHECK (type IN ('NORMAL', 'CORRECTIF')),
    remplace_bulletin_id INTEGER REFERENCES bulletin(id) ON DELETE RESTRICT,
    etat                 TEXT    NOT NULL DEFAULT 'BROUILLON'
                           CHECK (etat IN ('BROUILLON', 'CALCULE', 'FIGE')),
    numero_serie         TEXT    UNIQUE,
    fige_at              TEXT,
    params_version       TEXT    NOT NULL,
    convention_version   INTEGER NOT NULL,
    total_a              TEXT    NOT NULL DEFAULT '0',
    total_b              TEXT    NOT NULL DEFAULT '0',
    total_c              TEXT    NOT NULL DEFAULT '0',
    total_d              TEXT    NOT NULL DEFAULT '0',
    net_e                TEXT    NOT NULL DEFAULT '0',
    avertissements_json  TEXT    NOT NULL DEFAULT '[]',
    pdf_path             TEXT,
    date_generation      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at           TEXT,
    CHECK ((type = 'NORMAL'    AND remplace_bulletin_id IS NULL)
        OR (type = 'CORRECTIF' AND remplace_bulletin_id IS NOT NULL)),
    CHECK (etat != 'FIGE'
        OR (numero_serie IS NOT NULL AND fige_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bulletin_normal_periode
    ON bulletin (employe_id, periode) WHERE type = 'NORMAL';
CREATE INDEX IF NOT EXISTS idx_bulletin_employe
    ON bulletin (employe_id, periode);

-- 6. bulletin_ligne -------------------------------------------------------
CREATE TABLE IF NOT EXISTS bulletin_ligne (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bulletin_id         INTEGER NOT NULL
                          REFERENCES bulletin(id) ON DELETE CASCADE,
    ordre_affichage     INTEGER NOT NULL DEFAULT 0,
    zone                TEXT    NOT NULL
                          CHECK (zone IN ('Z1', 'Z2', 'Z3', 'Z4', 'SYSTEME')),
    ligne_systeme       TEXT    CHECK (ligne_systeme IN ('A', 'B', 'C', 'D', 'E')),
    code_snapshot       TEXT    NOT NULL,
    libelle_snapshot    TEXT    NOT NULL,
    sens_snapshot       TEXT    NOT NULL
                          CHECK (sens_snapshot IN ('GAIN', 'RETENUE')),
    cotisable_snapshot  INTEGER CHECK (cotisable_snapshot IN (0, 1)),
    imposable_snapshot  INTEGER CHECK (imposable_snapshot IN (0, 1)),
    regime_irg_snapshot TEXT    CHECK (regime_irg_snapshot IN ('BAREME', 'TAUX_10')),
    base                TEXT,
    taux                TEXT,
    montant             TEXT    NOT NULL DEFAULT '0',
    created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT,
    CHECK ((zone = 'SYSTEME') = (ligne_systeme IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_ligne_bulletin
    ON bulletin_ligne (bulletin_id, ordre_affichage);
"""


def _m2_payroll(cur: sqlite3.Cursor) -> None:
    """الهجرة 2 — جداول الأجور الست + الفهارس + trigger convention."""
    cur.executescript(_M2_PAYROLL_DDL)


_MIGRATIONS: List[Tuple[int, Callable[[sqlite3.Cursor], None]]] = [
    (1, _m1_baseline),
    (2, _m2_payroll),
]


def _legacy_db_present(cur: sqlite3.Cursor) -> bool:
    """True لو القاعدة سبقت نظام الهجرات (جدول cd_documents موجود). يُفحَص
    **قبل** أن يُنشئ init_db الجداول المشتركة، فيميّز قاعدة موجودة عن جديدة."""
    row = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cd_documents'"
    ).fetchone()
    return row is not None


def run_migrations(conn: Optional[sqlite3.Connection] = None) -> List[int]:
    """يطبّق الهجرات غير المسجَّلة بالترتيب. يرجّع قائمة النُّسخ التي
    طُبِّقت فعلياً في هذا النداء.

    conn: اتصال قائم (يُستعمله بلا إغلاق) — يمرّره init_db. None: يفتح
    اتصالاً خاصاً ويغلقه (تشغيل مستقل / اختبارات).
    """
    own = conn is None
    if own:
        from programme.database import get_connection  # استيراد محلّي: لا دور دائري
        conn = get_connection()

    try:
        cur = conn.cursor()
        cur.executescript(_TRACKING_DDL)

        applied = {r[0] for r in cur.execute("SELECT version FROM schema_migrations")}

        # قاعدة موجودة سبقت نظام الهجرات → الهجرة 1 «حالة أساسية» بلا تنفيذ
        if 1 not in applied and _legacy_db_present(cur):
            cur.execute("INSERT INTO schema_migrations (version) VALUES (1)")
            applied.add(1)
        conn.commit()

        done: List[int] = []
        for version, fn in _MIGRATIONS:
            if version in applied:
                continue
            fn(cur)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            conn.commit()
            done.append(version)
        return done
    finally:
        if own:
            conn.close()


def current_version(conn: Optional[sqlite3.Connection] = None) -> int:
    """أعلى نسخة هجرة مطبَّقة (0 لو لا شيء)."""
    own = conn is None
    if own:
        from programme.database import get_connection
        conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()
        return row[0] or 0 if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        if own:
            conn.close()
