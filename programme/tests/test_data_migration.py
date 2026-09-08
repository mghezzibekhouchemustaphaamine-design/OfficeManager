"""اختبارات ترحيل بيانات المستخدم إلى مجلد دائم (المهمة د).

:func:`programme.paths.ensure_user_data_migrated` تنسخ (لا تنقل) قاعدة
البيانات وملفات المعاملات من المكان القديم إلى :func:`get_data_dir`، مرّة
واحدة (علامة)، وتفشل بأمان لو الوجهة غير قابلة للكتابة.

كل اختبار يعزل ``get_data_dir`` و ``_legacy_db_path`` في مجلد مؤقّت —
لا مساس بـ``%APPDATA%`` الحقيقي ولا بقاعدة المكتب.
"""
import logging
import os
import shutil
import tempfile
import unittest
from unittest import mock

from programme import paths


class _QuietLog:
    """سجلّ يبتلع كل شيء — نتحقّق من الرسائل عبر السجلّ عند الحاجة."""
    def __init__(self):
        self.records = []

    def info(self, msg, *a):
        self.records.append(("info", msg % a if a else msg))

    def warning(self, msg, *a):
        self.records.append(("warning", msg % a if a else msg))


class DataMigrationTest(unittest.TestCase):

    def setUp(self):
        self._root = tempfile.mkdtemp(prefix="om_datamig_")
        self._data_dir = os.path.join(self._root, "appdata", "OfficeManager")
        self._legacy_db = os.path.join(self._root, "proj", "office_system.db")
        os.makedirs(os.path.dirname(self._legacy_db))
        # قاعدة قديمة فيها «بيانات»
        with open(self._legacy_db, "wb") as fh:
            fh.write(b"SQLite format 3\x00" + b"OLD-DB-CONTENT")

        self._p_data = mock.patch.object(
            paths, "get_data_dir", lambda: self._data_dir)
        self._p_legacy = mock.patch.object(
            paths, "_legacy_db_path", lambda: self._legacy_db)
        self._p_data.start()
        self._p_legacy.start()
        self.log = _QuietLog()

    def tearDown(self):
        self._p_data.stop()
        self._p_legacy.stop()
        shutil.rmtree(self._root, ignore_errors=True)

    def _new_db(self):
        return os.path.join(self._data_dir, "office_system.db")

    def _marker(self):
        return os.path.join(self._data_dir, ".data_migrated_v1")

    @staticmethod
    def _read(path):
        with open(path, "rb") as fh:
            return fh.read()

    # ---------------------------------------------------------------
    def test_copies_db_keeps_old_writes_marker(self):
        paths.ensure_user_data_migrated(self.log)

        self.assertTrue(os.path.exists(self._new_db()))
        self.assertEqual(self._read(self._new_db()),
                         self._read(self._legacy_db))
        self.assertTrue(os.path.exists(self._legacy_db))      # القديمة باقية
        self.assertTrue(os.path.exists(self._marker()))
        # params_paie نُسخت (كل ملفّات params_*.json المشحونة)
        new_params = os.path.join(self._data_dir, "params_paie")
        shipped = {n for n in os.listdir(paths._SHIPPED_PARAMS_DIR)
                   if n.startswith("params_") and n.endswith(".json")}
        self.assertTrue(shipped)
        self.assertEqual(set(os.listdir(new_params)) & shipped, shipped)
        # get_db_path يقرأ من الجديد الآن
        self.assertEqual(paths.get_db_path(), self._new_db())

    def test_idempotent_second_run_no_recopy_no_overwrite(self):
        paths.ensure_user_data_migrated(self.log)
        # عدّل نسخة الجديد يدوياً — تشغيل ثانٍ يجب ألّا يدهسها بالقديمة
        with open(self._new_db(), "wb") as fh:
            fh.write(b"NEW-DB-EDITED-LOCALLY")
        mtime_before = os.path.getmtime(self._new_db())

        paths.ensure_user_data_migrated(self.log)             # مرّة ثانية

        self.assertEqual(self._read(self._new_db()),
                         b"NEW-DB-EDITED-LOCALLY")            # لم تُدهَس
        self.assertEqual(os.path.getmtime(self._new_db()), mtime_before)

    def test_appdata_db_present_without_marker_not_overwritten(self):
        # نسخة APPDATA موجودة أصلاً (بلا علامة) — الترحيل يحترمها
        os.makedirs(self._data_dir)
        with open(self._new_db(), "wb") as fh:
            fh.write(b"EXISTING-APPDATA-DB")

        paths.ensure_user_data_migrated(self.log)

        self.assertEqual(self._read(self._new_db()),
                         b"EXISTING-APPDATA-DB")
        self.assertTrue(os.path.exists(self._marker()))

    def test_fresh_install_no_old_db(self):
        os.remove(self._legacy_db)                            # لا قديمة
        paths.ensure_user_data_migrated(self.log)
        # لا تُنشأ قاعدة فارغة — init_db مسؤول عنها لاحقاً
        self.assertFalse(os.path.exists(self._new_db()))
        self.assertTrue(os.path.exists(self._marker()))       # لكن العلامة تُكتب
        # وملفات المعاملات نُسخت
        self.assertTrue(os.path.isdir(
            os.path.join(self._data_dir, "params_paie")))

    def test_unwritable_target_does_not_crash_falls_back(self):
        # get_data_dir يشير إلى مسار داخل ملفّ (لا مجلد) → makedirs يفشل
        blocker = os.path.join(self._root, "blocker-file")
        open(blocker, "w").close()
        with mock.patch.object(
                paths, "get_data_dir",
                lambda: os.path.join(blocker, "OfficeManager")):
            paths.ensure_user_data_migrated(self.log)         # لا استثناء
            self.assertTrue(
                any(lvl == "warning" for lvl, _ in self.log.records),
                self.log.records)
            # لا علامة، والتدرّج يرجع للمكان القديم
            self.assertEqual(paths.get_db_path(), self._legacy_db)

    def test_marker_written_only_after_success(self):
        # نُفشل نسخ قاعدة البيانات في منتصف الترحيل → لا علامة
        real_copy = paths._copy_atomic

        def boom(src, dst):
            if dst.endswith("office_system.db"):
                raise OSError("قرص ممتلئ (محاكاة)")
            return real_copy(src, dst)

        with mock.patch.object(paths, "_copy_atomic", boom):
            paths.ensure_user_data_migrated(self.log)

        self.assertFalse(os.path.exists(self._marker()))
        self.assertTrue(any(lvl == "warning" for lvl, _ in self.log.records))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
