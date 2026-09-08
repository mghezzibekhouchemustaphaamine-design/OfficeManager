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
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from typing import Callable, Dict, Iterable, List, Optional, Tuple

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


def _m3_transient(cur: sqlite3.Cursor) -> None:
    """الهجرة 3 — عمود ``transient`` على ``entreprise``.

    ``transient = 1`` → «زبون عابر» أُنشئ لحظياً من شاشة الكشف باسم حرّ،
    لا يظهر في منتقي «زبون مسجَّل». ``transient = 0`` → زبون مسجَّل
    (صاحب سجل تجاري). :func:`promote_entreprise` يرفع 1 → 0."""
    cur.execute(
        "ALTER TABLE entreprise ADD COLUMN transient INTEGER NOT NULL "
        "DEFAULT 0 CHECK (transient IN (0, 1))"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_entreprise_transient "
        "ON entreprise (transient)"
    )


def _m4_drop_dead_invoice_tables(cur: sqlite3.Cursor) -> None:
    """الهجرة 4 — إسقاط ``invoices`` و``invoice_items``.

    جدولان أُنشئا في ``database.py`` ولم يُقرأهما أيّ كود قطّ (كانت
    ``programme/utils.generate_invoice_number`` وحدها تشير إلى ``invoices``،
    وهي نفسها غير مُستدعاة — حُذفت). الابن أولاً (``invoice_items`` يشير إلى
    ``invoices``).

    **حارس:** إن كان أيّ من الجدولين موجوداً وفيه صفوف، تتوقّف الهجرة
    برفع استثناء بدل الإسقاط الصامت — إسقاط جدول فيه بيانات قرار واعٍ لا
    تلقائي. على قاعدة جديدة الجدولان غير موجودين بعد (الهجرات تُشغَّل قبل
    ``CREATE TABLE`` في ``init_db``) فتُتخطّى بأمان."""
    for tbl in ("invoice_items", "invoices"):
        exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (tbl,),
        ).fetchone()
        if not exists:
            continue
        n = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        if n:
            raise RuntimeError(
                f"الهجرة 4 متوقّفة: الجدول «{tbl}» فيه {n} صفّ بيانات. "
                f"إسقاط جدول فيه بيانات قرار واعٍ — راجِعه يدوياً ثم عدّل "
                f"هذه الهجرة."
            )
        cur.execute(f"DROP TABLE {tbl}")


_MIGRATIONS: List[Tuple[int, Callable[[sqlite3.Cursor], None]]] = [
    (1, _m1_baseline),
    (2, _m2_payroll),
    (3, _m3_transient),
    (4, _m4_drop_dead_invoice_tables),
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


# =====================================================================
#  طبقة القراءة/الكتابة (CRUD) لجداول الأجور الست
# =====================================================================
#
#  قواعد صارمة:
#   • كل مبلغ أو نسبة يُخزَّن نصّاً TEXT عبر ``str(Decimal(...))`` ويُقرأ
#     ``Decimal(value)`` — لا ``float`` إطلاقاً في أي مسار (SPEC §5.4).
#   • ``convention`` غير قابلة للتعديل (trigger ``convention_no_update``):
#     كل تغيير = صف جديد ``version + 1``. حتى «التأكيد» (confirme=1) يُنشئ
#     نسخة جديدة — راجع :func:`confirm_convention`.
#   • ``rubrique_catalogue``: ``cotisable`` و``imposable`` إلزاميان بلا
#     افتراض (SPEC §2.1 / V7) — :func:`create_rubrique` ترفع ``ValueError``
#     إن غابا.
#   • أي عملية تمسّ عدّة جداول (كشف + عدّة أسطر) تجري داخل معاملة واحدة
#     عبر :func:`transaction` — إمّا الكل أو لا شيء.
#   • هذه الوحدة لا تستورد ``ui/`` ولا ``ui2/`` ولا ``tkinter``.
#
#  ملاحظة تصميم — CNAS وIRG ليسا في الكتالوج: هما السطران النظاميان
#  ‎[B]‎ و‎[D]‎ يولّدهما المحرّك (SPEC §2.3.1)، ولا ينطبق عليهما سؤالا
#  ``cotisable``/``imposable`` (لذا لا يخرقان قاعدة NOT NULL).


# --------------------------- أدوات مساعدة ---------------------------

def _money(value) -> str:
    """مبلغ/نسبة → نصّ TEXT للتخزين. يقبل ``Decimal``/``int``/``str``.
    ``float`` ممنوع صراحةً (يفقد الدقّة قبل أن يصل هنا)."""
    if isinstance(value, float):
        raise TypeError("float ممنوع في طبقة الأجور — مرّر Decimal أو str")
    return str(Decimal(str(value)))


def _dec(value) -> Optional[Decimal]:
    """نصّ TEXT مُخزَّن → ``Decimal`` (أو ``None``)."""
    return None if value is None else Decimal(value)


def _row_to_dict(row: Optional[sqlite3.Row], *, money: Iterable[str] = (),
                 json_fields: Iterable[str] = ()) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    for f in money:
        if d.get(f) is not None:
            d[f] = Decimal(d[f])
    for f in json_fields:
        if isinstance(d.get(f), str):
            try:
                d[f] = json.loads(d[f])
            except (ValueError, TypeError):
                pass
    return d


def _insert(cur: sqlite3.Cursor, table: str, cols: Tuple[str, ...],
            data: Dict) -> int:
    keys = [c for c in cols if c in data]
    if not keys:
        raise ValueError(f"{table}: لا حقول صالحة للإدراج")
    placeholders = ", ".join("?" for _ in keys)
    cur.execute(
        f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({placeholders})",
        [data[k] for k in keys],
    )
    return int(cur.lastrowid)


def _update(cur: sqlite3.Cursor, table: str, cols: Tuple[str, ...],
            row_id: int, data: Dict) -> None:
    keys = [c for c in cols if c in data]
    if not keys:
        return
    sets = ", ".join(f"{k} = ?" for k in keys)
    cur.execute(
        f"UPDATE {table} SET {sets}, updated_at = datetime('now','localtime') "
        f"WHERE id = ?",
        [data[k] for k in keys] + [row_id],
    )


@contextmanager
def transaction(conn: Optional[sqlite3.Connection] = None):
    """معاملة ذرّية: ``commit`` عند النجاح، ``rollback`` عند أي استثناء.

    ``conn=None`` → يفتح اتصالاً خاصاً (ويُفعّل ``PRAGMA foreign_keys``)
    ويغلقه في النهاية. ``conn`` مُمرَّر → يُستعمل بلا إغلاق، ويُطبَّق
    عليه ``commit``/``rollback`` نفسه.

    كل كتابة في هذه الوحدة تمرّ من هنا؛ ودمج «كشف + أسطره» في
    :func:`create_bulletin` يستعمل معاملة واحدة فيتراجع كلّياً عند فشل
    أي سطر.
    """
    own = conn is None
    if own:
        from programme.database import get_connection  # محلّي: لا دور دائري
        conn = get_connection()
        conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


@contextmanager
def _reading(conn: Optional[sqlite3.Connection] = None):
    own = conn is None
    if own:
        from programme.database import get_connection
        conn = get_connection()
    try:
        yield conn
    finally:
        if own:
            conn.close()


# ----------------------------- entreprise -----------------------------

_ENTREPRISE_COLS = (
    "raison_sociale", "forme_juridique", "nif", "nis", "rc", "art_imposition",
    "num_employeur_cnas", "adresse", "gerant_nom", "gerant_qualite", "tel",
    "actif", "transient",
)


def create_entreprise(data: Dict, conn: Optional[sqlite3.Connection] = None) -> int:
    if not data.get("raison_sociale"):
        raise ValueError("entreprise: 'raison_sociale' إلزامي")
    with transaction(conn) as c:
        return _insert(c.cursor(), "entreprise", _ENTREPRISE_COLS, data)


def promote_entreprise(entreprise_id: int,
                       conn: Optional[sqlite3.Connection] = None) -> None:
    """يرفع «زبوناً عابراً» (transient=1) إلى «زبون مسجَّل» (transient=0)."""
    with transaction(conn) as c:
        c.execute(
            "UPDATE entreprise SET transient = 0, "
            "updated_at = datetime('now','localtime') WHERE id = ?",
            (entreprise_id,))


def get_entreprise(entreprise_id: int,
                   conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    with _reading(conn) as c:
        row = c.execute("SELECT * FROM entreprise WHERE id = ?",
                        (entreprise_id,)).fetchone()
    return _row_to_dict(row)


def list_entreprises(*, actif_only: bool = True, registered_only: bool = False,
                     conn: Optional[sqlite3.Connection] = None) -> List[dict]:
    clauses = []
    if actif_only:
        clauses.append("actif = 1")
    if registered_only:
        clauses.append("transient = 0")
    sql = "SELECT * FROM entreprise"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY raison_sociale"
    with _reading(conn) as c:
        rows = c.execute(sql).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_entreprise(entreprise_id: int, data: Dict,
                      conn: Optional[sqlite3.Connection] = None) -> None:
    with transaction(conn) as c:
        _update(c.cursor(), "entreprise", _ENTREPRISE_COLS, entreprise_id, data)


# ----------------------------- convention -----------------------------

_CONVENTION_COLS = (
    "entreprise_id", "version", "confirme", "base_iep", "base_pri",
    "prorata_panier_transport", "retard_reduit_heures_presence",
    "taux_hs_jour", "taux_hs_nuit", "taux_hs_ferie",
)
_CONVENTION_MONEY = ("taux_hs_jour", "taux_hs_nuit", "taux_hs_ferie")


def create_convention(entreprise_id: int, params: Dict,
                      conn: Optional[sqlite3.Connection] = None) -> int:
    """يُنشئ نسخة اتفاقية جديدة (``version`` = أعلى نسخة + 1). لا تعديل
    لنسخة قائمة إطلاقاً (trigger). ``confirme`` تبدأ 0 ما لم تُمرَّر."""
    with transaction(conn) as c:
        cur = c.cursor()
        nxt = cur.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM convention "
            "WHERE entreprise_id = ?", (entreprise_id,)).fetchone()[0]
        data = dict(params)
        data["entreprise_id"] = entreprise_id
        data["version"] = nxt
        for f in _CONVENTION_MONEY:
            if f in data and data[f] is not None:
                data[f] = _money(data[f])
        return _insert(cur, "convention", _CONVENTION_COLS, data)


def get_active_convention(entreprise_id: int,
                          conn: Optional[sqlite3.Connection] = None
                          ) -> Optional[dict]:
    """أحدث نسخة اتفاقية للشركة (أعلى ``version``)."""
    with _reading(conn) as c:
        row = c.execute(
            "SELECT * FROM convention WHERE entreprise_id = ? "
            "ORDER BY version DESC LIMIT 1", (entreprise_id,)).fetchone()
    return _row_to_dict(row, money=_CONVENTION_MONEY)


def list_conventions(entreprise_id: int,
                     conn: Optional[sqlite3.Connection] = None) -> List[dict]:
    with _reading(conn) as c:
        rows = c.execute(
            "SELECT * FROM convention WHERE entreprise_id = ? "
            "ORDER BY version DESC", (entreprise_id,)).fetchall()
    return [_row_to_dict(r, money=_CONVENTION_MONEY) for r in rows]


def confirm_convention(entreprise_id: int,
                       conn: Optional[sqlite3.Connection] = None) -> int:
    """يؤكّد اتفاقية الشركة (V15 / SPEC §1.2.2).

    الاتفاقية غير قابلة للتعديل، لذا التأكيد = إدراج نسخة جديدة
    (``version + 1``) بنفس المعاملات و``confirme = 1``. يرجّع ``id``
    النسخة المؤكَّدة (أو القائمة إن كانت مؤكَّدة أصلاً)."""
    with transaction(conn) as c:
        cur = c.cursor()
        latest = cur.execute(
            "SELECT * FROM convention WHERE entreprise_id = ? "
            "ORDER BY version DESC LIMIT 1", (entreprise_id,)).fetchone()
        if latest is None:
            raise ValueError(
                f"لا اتفاقية للشركة {entreprise_id} — أنشئ واحدة أولاً")
        if latest["confirme"] == 1:
            return int(latest["id"])
        data = {k: latest[k] for k in _CONVENTION_COLS}
        data["version"] = latest["version"] + 1
        data["confirme"] = 1
        return _insert(cur, "convention", _CONVENTION_COLS, data)


# ------------------------- rubrique_catalogue -------------------------

_RUBRIQUE_COLS = (
    "entreprise_id", "code", "libelle_fr", "libelle_ar", "sens", "mode",
    "base_calcul", "cotisable", "imposable", "regime_irg", "proratisable",
    "depend_de", "ordre_affichage", "actif",
)
_RUBRIQUE_JSON = ("base_calcul", "depend_de")


def _encode_rubrique_json(data: Dict) -> Dict:
    d = dict(data)
    for f in _RUBRIQUE_JSON:
        if f in d and not isinstance(d[f], str):
            d[f] = json.dumps(d[f], ensure_ascii=False)
    return d


def create_rubrique(entreprise_id: int, data: Dict,
                    conn: Optional[sqlite3.Connection] = None) -> int:
    """قاعدة V7: ``cotisable`` و``imposable`` إلزاميان صراحةً — غيابهما
    ``ValueError`` قبل أي كتابة."""
    for k in ("cotisable", "imposable"):
        if data.get(k) is None:
            raise ValueError(
                f"rubrique: '{k}' إلزامي بلا افتراض (SPEC §2.1 / V7)")
    d = _encode_rubrique_json(data)
    d["entreprise_id"] = entreprise_id
    with transaction(conn) as c:
        return _insert(c.cursor(), "rubrique_catalogue", _RUBRIQUE_COLS, d)


def get_rubrique(rubrique_id: int,
                 conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    with _reading(conn) as c:
        row = c.execute("SELECT * FROM rubrique_catalogue WHERE id = ?",
                        (rubrique_id,)).fetchone()
    return _row_to_dict(row, json_fields=_RUBRIQUE_JSON)


def list_rubriques(entreprise_id: int, *, actif_only: bool = True,
                   conn: Optional[sqlite3.Connection] = None) -> List[dict]:
    sql = "SELECT * FROM rubrique_catalogue WHERE entreprise_id = ?"
    if actif_only:
        sql += " AND actif = 1"
    sql += " ORDER BY sens, ordre_affichage, code"
    with _reading(conn) as c:
        rows = c.execute(sql, (entreprise_id,)).fetchall()
    return [_row_to_dict(r, json_fields=_RUBRIQUE_JSON) for r in rows]


def update_rubrique(rubrique_id: int, data: Dict,
                    conn: Optional[sqlite3.Connection] = None) -> None:
    if "cotisable" in data and data["cotisable"] is None:
        raise ValueError("rubrique: 'cotisable' لا يُفرَّغ (V7)")
    if "imposable" in data and data["imposable"] is None:
        raise ValueError("rubrique: 'imposable' لا يُفرَّغ (V7)")
    d = _encode_rubrique_json(data)
    with transaction(conn) as c:
        _update(c.cursor(), "rubrique_catalogue", _RUBRIQUE_COLS,
                rubrique_id, d)


# ------------------------------- employe -------------------------------

_EMPLOYE_COLS = (
    "entreprise_id", "nom", "prenom", "num_ss", "date_entree", "poste",
    "classe_indice", "type_contrat", "rib", "salaire_base", "taux_iep",
    "nb_enfants", "temps_partiel_ratio", "date_sortie", "actif",
)
_EMPLOYE_MONEY = ("salaire_base", "taux_iep", "temps_partiel_ratio")


def _encode_employe_money(data: Dict) -> Dict:
    d = dict(data)
    for f in _EMPLOYE_MONEY:
        if f in d and d[f] is not None:
            d[f] = _money(d[f])
    return d


def create_employe(entreprise_id: int, data: Dict,
                   conn: Optional[sqlite3.Connection] = None) -> int:
    if not data.get("nom"):
        raise ValueError("employe: 'nom' إلزامي")
    d = _encode_employe_money(data)
    d["entreprise_id"] = entreprise_id
    with transaction(conn) as c:
        return _insert(c.cursor(), "employe", _EMPLOYE_COLS, d)


def get_employe(employe_id: int,
                conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    with _reading(conn) as c:
        row = c.execute("SELECT * FROM employe WHERE id = ?",
                        (employe_id,)).fetchone()
    return _row_to_dict(row, money=_EMPLOYE_MONEY)


def list_employes(entreprise_id: int, *, actif_only: bool = True,
                  conn: Optional[sqlite3.Connection] = None) -> List[dict]:
    sql = "SELECT * FROM employe WHERE entreprise_id = ?"
    if actif_only:
        sql += " AND actif = 1"
    sql += " ORDER BY nom, prenom"
    with _reading(conn) as c:
        rows = c.execute(sql, (entreprise_id,)).fetchall()
    return [_row_to_dict(r, money=_EMPLOYE_MONEY) for r in rows]


def update_employe(employe_id: int, data: Dict,
                   conn: Optional[sqlite3.Connection] = None) -> None:
    d = _encode_employe_money(data)
    with transaction(conn) as c:
        _update(c.cursor(), "employe", _EMPLOYE_COLS, employe_id, d)


# ------------------------ bulletin + bulletin_ligne ------------------------

_BULLETIN_COLS = (
    "employe_id", "periode", "type", "remplace_bulletin_id", "etat",
    "numero_serie", "fige_at", "params_version", "convention_version",
    "total_a", "total_b", "total_c", "total_d", "net_e",
    "avertissements_json", "pdf_path",
)
_BULLETIN_MONEY = ("total_a", "total_b", "total_c", "total_d", "net_e")

_LIGNE_COLS = (
    "bulletin_id", "ordre_affichage", "zone", "ligne_systeme",
    "code_snapshot", "libelle_snapshot", "sens_snapshot",
    "cotisable_snapshot", "imposable_snapshot", "regime_irg_snapshot",
    "base", "taux", "montant",
)
_LIGNE_MONEY = ("base", "taux", "montant")

#  الأسطر النظامية ↔ مجاميع الكشف (§2.3.1). كلاهما يُخزَّن: الأسطر
#  لإعادة الطباعة الحرفية، والمجاميع للاستعلام — ويجب ألّا يتباعدا.
_SYS_LIGNE_TO_TOTAL = {"A": "total_a", "B": "total_b", "C": "total_c",
                       "D": "total_d", "E": "net_e"}


def create_bulletin(bulletin: Dict, lignes: Iterable[Dict],
                    conn: Optional[sqlite3.Connection] = None) -> int:
    """يُدرج الكشف وكلّ أسطره في **معاملة واحدة**. فشل أي سطر (خرق
    ``CHECK`` مثلاً) يتراجع بالكشف كلّه — لا كشف بلا أسطره ولا العكس.

    حارس اتّساق: كل سطر نظامي ``ligne_systeme`` في ``A..E`` يجب أن
    يطابق مبلغُه ``total_a..net_e`` المقابل — يُرفَع ``ValueError`` عند
    الاختلاف قبل أي كتابة."""
    b = dict(bulletin)
    for f in _BULLETIN_MONEY:
        if f in b and b[f] is not None:
            b[f] = _money(b[f])
    av = b.get("avertissements_json")
    if av is not None and not isinstance(av, str):
        b["avertissements_json"] = json.dumps(av, ensure_ascii=False)

    lignes = [dict(ln) for ln in lignes]

    # --- حارس التباعد بين bulletin_ligne و bulletin.total_* ---
    for ln in lignes:
        code = ln.get("ligne_systeme")
        tkey = _SYS_LIGNE_TO_TOTAL.get(code)
        if tkey is None:
            continue
        ligne_m = _money(ln.get("montant", "0"))
        total_m = b.get(tkey)
        if total_m is None or ligne_m != total_m:
            raise ValueError(
                f"عدم اتّساق الكشف: السطر النظامي [{code}] = {ligne_m} "
                f"≠ {tkey} = {total_m}. الأسطر والمجاميع يجب أن تتطابق.")

    with transaction(conn) as c:
        cur = c.cursor()
        bid = _insert(cur, "bulletin", _BULLETIN_COLS, b)
        for ln in lignes:
            d = dict(ln)
            d["bulletin_id"] = bid
            for f in _LIGNE_MONEY:
                if f in d and d[f] is not None:
                    d[f] = _money(d[f])
            _insert(cur, "bulletin_ligne", _LIGNE_COLS, d)
        return bid


def get_bulletin(bulletin_id: int,
                 conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    """الكشف مع مفتاح ``lignes`` (قائمة أسطره مرتّبة). كل المبالغ
    ``Decimal``، و``avertissements_json`` مُحلَّلة قائمةً."""
    with _reading(conn) as c:
        row = c.execute("SELECT * FROM bulletin WHERE id = ?",
                        (bulletin_id,)).fetchone()
        if row is None:
            return None
        lignes = c.execute(
            "SELECT * FROM bulletin_ligne WHERE bulletin_id = ? "
            "ORDER BY ordre_affichage, id", (bulletin_id,)).fetchall()
    out = _row_to_dict(row, money=_BULLETIN_MONEY,
                       json_fields=("avertissements_json",))
    out["lignes"] = [_row_to_dict(l, money=_LIGNE_MONEY) for l in lignes]
    return out


def list_bulletins(employe_id: int,
                   conn: Optional[sqlite3.Connection] = None) -> List[dict]:
    with _reading(conn) as c:
        rows = c.execute(
            "SELECT * FROM bulletin WHERE employe_id = ? "
            "ORDER BY periode DESC, id DESC", (employe_id,)).fetchall()
    return [_row_to_dict(r, money=_BULLETIN_MONEY,
                         json_fields=("avertissements_json",)) for r in rows]


def fige_bulletin(bulletin_id: int,
                  conn: Optional[sqlite3.Connection] = None) -> str:
    """يثبّت الكشف: يولّد ``numero_serie``، ويضبط ``etat = 'FIGE'`` و
    ``fige_at``. يرجّع رقم السلسلة. عملية غير عكوسة."""
    with transaction(conn) as c:
        cur = c.cursor()
        row = cur.execute(
            "SELECT periode, etat, numero_serie FROM bulletin WHERE id = ?",
            (bulletin_id,)).fetchone()
        if row is None:
            raise ValueError(f"لا كشف id={bulletin_id}")
        if row["etat"] == "FIGE":
            return row["numero_serie"]
        numero = f"PAIE-{row['periode']}-{bulletin_id:05d}"
        cur.execute(
            "UPDATE bulletin SET etat = 'FIGE', numero_serie = ?, "
            "fige_at = datetime('now','localtime'), "
            "updated_at = datetime('now','localtime') WHERE id = ?",
            (numero, bulletin_id))
        return numero


# --------------------- بذرة الكتالوج الافتراضي (SPEC §2.2) ---------------------
#
#  (code, libelle_fr, libelle_ar, sens, mode, cotisable, imposable, proratisable)
#  regime_irg = 'BAREME' للجميع في هذه النسخة (SPEC §2.4).
#  CNAS/IRG غير مدرجَين — سطران نظاميّان [B]/[D] لا رُبريكتان.

_DEFAULT_CATALOGUE: Tuple[Tuple, ...] = (
    # --- Z1 : GAIN خاضع للاشتراك ---
    ("1000", "Salaire de base", "الأجر القاعدي",
     "GAIN", "MONTANT", 1, 1, 1),
    ("1010", "Heures supplémentaires", "الساعات الإضافية",
     "GAIN", "QUANTITE_X_PU", 1, 1, 0),
    ("1020", "Prime d'ancienneté (IEP)", "منحة الأقدمية IEP",
     "GAIN", "TAUX_SUR_BASE", 1, 1, 1),
    ("1030", "Prime de rendement (PRI/PRC)", "منحة المردودية PRI/PRC",
     "GAIN", "TAUX_SUR_BASE", 1, 1, 1),
    ("1040", "Prime de poste", "منحة العمل بالتناوب (poste)",
     "GAIN", "MONTANT", 1, 1, 1),
    ("1050", "Prime de nuisance", "منحة الضرر/الخطر (nuisance)",
     "GAIN", "MONTANT", 1, 1, 1),
    ("1060", "Indemnité de congé payé", "تعويض العطلة المدفوعة",
     "GAIN", "MONTANT", 1, 1, 0),
    ("1070", "Prime de travail de nuit", "منحة ليلية",
     "GAIN", "MONTANT", 1, 1, 1),
    # --- Z2 : GAIN غير خاضع للاشتراك، خاضع للضريبة ---
    ("2000", "Prime de panier", "منحة السلة (panier)",
     "GAIN", "QUANTITE_X_PU", 0, 1, 1),
    ("2010", "Prime de transport", "منحة النقل",
     "GAIN", "MONTANT", 0, 1, 1),
    ("2020", "Indemnité de véhicule", "منحة السيارة",
     "GAIN", "MONTANT", 0, 1, 0),
    # --- Z3 : GAIN غير خاضع لا للاشتراك ولا للضريبة ---
    ("3010", "Allocations familiales", "المنح العائلية",
     "GAIN", "MONTANT", 0, 0, 0),
    ("3020", "Prime de scolarité / salaire unique",
     "المنحة المدرسية / الأجر الوحيد", "GAIN", "MONTANT", 0, 0, 0),
    ("3030", "Frais de mission (sur justificatifs)", "مصاريف المهمة",
     "GAIN", "MONTANT", 0, 0, 0),
    # --- Z1 (سالب) : اقتطاعات الغياب (SPEC §2.2 محدَّث) ---
    #  الأيام والساعات مقاماهما مختلفان (÷30 مقابل ÷173,33) ولا يُدمجان.
    #  «اقتطاع ساعات غياب» يجمع كل الدوافع (مبرر/غير مبرر/مغادرة) — الفصل
    #  حسابي لا إداري. «اقتطاع ساعات تأخّر» يبقى منفصلاً إجبارياً (لا
    #  يُطرح من ساعات الحضور في تنسيب السلة/النقل، §1.2.3).
    ("4000", "Retenue jours d'absence", "اقتطاع أيام غياب",
     "RETENUE", "QUANTITE_X_PU", 1, 1, 0),
    ("4010", "Retenue heures d'absence", "اقتطاع ساعات غياب",
     "RETENUE", "QUANTITE_X_PU", 1, 1, 0),
    ("4020", "Retenue heures de retard", "اقتطاع ساعات تأخّر",
     "RETENUE", "QUANTITE_X_PU", 1, 1, 0),
    # --- Z4 : اقتطاعات غير CNAS/IRG ---
    ("5010", "Avance sur salaire", "تسبيق على الراتب",
     "RETENUE", "MONTANT", 0, 0, 0),
    ("5030", "Cotisation syndicale", "الاشتراك النقابي",
     "RETENUE", "MONTANT", 0, 0, 0),
)
#  حُذفت (المراجعة الميدانية — يغطّيها السطر الحرّ): 3000 منحة المنطقة ·
#  1080 منحة إنابة/معلّم تمهين · 5000 اقتطاع تعاضدية · 5020 اقتطاع قضائي.


def seed_catalogue(entreprise_id: int,
                   conn: Optional[sqlite3.Connection] = None) -> int:
    """يُحمّل الجدول المرجعي الافتراضي (SPEC §2.2) لشركة جديدة. يرجّع عدد
    الرُبريكات المُدرَجة. لا يفعل شيئاً (يرجّع 0) إن كان للشركة كتالوج
    أصلاً — كل الإدراج في معاملة واحدة."""
    with transaction(conn) as c:
        cur = c.cursor()
        exists = cur.execute(
            "SELECT 1 FROM rubrique_catalogue WHERE entreprise_id = ? LIMIT 1",
            (entreprise_id,)).fetchone()
        if exists:
            return 0
        n = 0
        for ordre, (code, fr, ar, sens, mode, cot, imp, prorat) in enumerate(
                _DEFAULT_CATALOGUE):
            _insert(cur, "rubrique_catalogue", _RUBRIQUE_COLS, {
                "entreprise_id": entreprise_id,
                "code": code,
                "libelle_fr": fr,
                "libelle_ar": ar,
                "sens": sens,
                "mode": mode,
                "base_calcul": "[]",
                "cotisable": cot,
                "imposable": imp,
                "regime_irg": "BAREME",
                "proratisable": prorat,
                "depend_de": "[]",
                "ordre_affichage": ordre,
                "actif": 1,
            })
            n += 1
        return n


# --------------------- زبون افتراضي عند أول تشغيل ---------------------

DEFAULT_CLIENT_NAME = "الزبون الافتراضي"


def ensure_default_client(conn: Optional[sqlite3.Connection] = None) -> int:
    """يضمن وجود زبون مسجَّل واحد على الأقل. عند أول تشغيل (لا زبون
    مسجَّلاً) يُنشئ زبوناً افتراضياً + كتالوجه الافتراضي + اتفاقية
    **مؤكَّدة تلقائياً** بقيم §1.2.1 (كلّها DEFAULT في المخطط) حتى لا
    تمنع V15 توليد الكشوف. يرجّع ``id`` زبون مسجَّل قابل للاستعمال."""
    with transaction(conn) as c:
        cur = c.cursor()
        row = cur.execute(
            "SELECT id FROM entreprise WHERE transient = 0 "
            "ORDER BY id LIMIT 1").fetchone()
        if row is not None:
            return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])
        ent_id = _insert(cur, "entreprise", _ENTREPRISE_COLS, {
            "raison_sociale": DEFAULT_CLIENT_NAME, "actif": 1, "transient": 0,
        })
        # كتالوج §2.2
        for ordre, (code, fr, ar, sens, mode, cot, imp, prorat) in enumerate(
                _DEFAULT_CATALOGUE):
            _insert(cur, "rubrique_catalogue", _RUBRIQUE_COLS, {
                "entreprise_id": ent_id, "code": code, "libelle_fr": fr,
                "libelle_ar": ar, "sens": sens, "mode": mode,
                "base_calcul": "[]", "cotisable": cot, "imposable": imp,
                "regime_irg": "BAREME", "proratisable": prorat,
                "depend_de": "[]", "ordre_affichage": ordre, "actif": 1,
            })
        # اتفاقية v1 مؤكَّدة (كل المعاملات DEFAULT = §1.2.1)
        _insert(cur, "convention", _CONVENTION_COLS,
                {"entreprise_id": ent_id, "version": 1, "confirme": 1})
        return ent_id
