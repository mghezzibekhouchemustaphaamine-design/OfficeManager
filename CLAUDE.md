# CLAUDE.md — دليل العمل على OfficeManager

## نظرة سريعة

برنامج سطح مكتب (Python 3.12 + Tkinter + SQLite) لمكتب خدمات جزائري:
توليد مستندات العمل من استمارات فوق صورة النموذج، مع أرشفة وسجلّ. الواجهة
عربية، المستندات بالفرنسية. نقطة التشغيل الوحيدة: `python main.py`.

**مكان البيانات:** `office_system.db` وملفات `params_paie` تعيش في
`%APPDATA%\OfficeManager\` (‏`programme.paths.get_db_path` /
`get_params_paie_dir`). ترحيل تلقائي لمرّة واحدة من جذر المشروع عند أوّل
تشغيل (`ensure_user_data_migrated` في `main()`)؛ النسخة القديمة بجذر
المشروع تبقى كاحتياط. الاختبارات تتجاوز المكان بمتغيّر البيئة
`OFFICEMANAGER_DATA_DIR`.

## الوثائق المرجعية (اقرأها قبل التعديل)

- `README.md` — البنية والخدمات والتشغيل.
- `docs/CHANGELOG.md` — سجلّ مرجعي، كل دفعة = قسم مربوط بكوميت «مرجع N».
- `docs/ARCHITECTURE_REVIEW.md` — مراجعة معمارية (سبتمبر 2026): الطبقات،
  نقاط الضعف، الدَّين التقني، خطة المراحل 0→4.
- `docs/specs/SPEC_PAIE_DZ.md` — **المرجع الإلزامي** لحساب الأجور. أي
  تعديل على منطق الحساب يلتزم به حرفياً.
- `docs/specs/SCHEMA_PAIE.md` · `docs/AUDIT_DB.md` — مخطّط قاعدة الأجور.

## قواعد ثابتة

- **فصل صارم:** لا شيء تحت `programme/` يستورد `tkinter` أو `ui/` أو
  `ui2/`. الواجهة تستورد من النواة، لا العكس.
- **`Decimal` حصراً** في كل ما يتعلق بالمال — ممنوع `float`.
- **لا رقم قانوني في الكود** — كلّه في `programme/data/params_paie/params_<سنة>.json`.
- **لا ميزة جديدة في `ui/` (Tkinter) بعد اليوم.** كل ما يُضاف يُضاف في
  `ui2/` (PySide6). إصلاح خلل في `ui/` بأقل تدخّل ممكن.
- **سير عمل الكوميت:** كوميتات «مرجع N» متسلسلة، كلٌّ مع قسم مقابل في
  `docs/CHANGELOG.md`، مباشرةً على `master`.

## الاختبارات

```
python -m unittest discover -s programme/payroll/tests      # النواة — 49 اختباراً
python -m unittest discover -s programme/tests              # ترحيل بيانات المستخدم — 6
python -m unittest discover -s ui2/tests                    # قاعدة الشاشة Screen — 10
python -m unittest discover -s ui2/paie/tests               # شاشة الكشف (pinning + مسوّدة + كاش) — 17
python programme/payroll/tests/test_golden.py               # تقرير IRG المقروء
QT_QPA_PLATFORM=offscreen python demos/ui2_paie_gallery.py --selftest
```

## واجهتان متعايشتان

- `ui/` (Tkinter، ~8 200 سطر) — التطبيق الحيّ: CD + وثائق HR.
- `ui2/` (PySide6) — الجديدة: مكتبة مكوّنات + `screen.py` (قاعدة شاشة
  مشتركة: هيكل + دورة حياة اختصارات + مسوّدة + سياق زبون — سترث منها HR
  و CD) + `paie/` (شاشة كشف الراتب، مبنيّة فوق `Screen`).
- شاشة الكشف الجديدة تُطلَق كعملية منفصلة: `python -m ui2.paie`، أو من
  الشاشة الرئيسية عبر بطاقة «كشف راتب (PySide6)» (`OfficeApp.open_paie_v2`).

---

## مهام معلّقة

### ربط البند الدائم (rubrique_catalogue ↔ شاشة الكشف)

**تمّ جزئياً (مرجع سبعة وأربعون):** الحساب يقرأ الكتالوج الآن.
`compute_bulletin(entries, cfg, convention, catalogue)` تقبل
`{code: {cotisable, imposable}}`؛ `bulletin.py::_catalogue()` تبنيه من
`list_rubriques(client_id)` (مُخزَّن مؤقتاً، يُبطَل مثل كاش الاتفاقية).
تصنيف الرمز المطابق يُعلو على الثابت في `LINE_TYPES`، والمنطقة تُشتقّ منه
ثم تُقفَل. رمز بلا صفّ كتالوج → الثابت + تحذير غير حاجب.

**لا يزال ناقصاً:**
- **قائمة «＋ إضافة سطر»** لا تزال من `LINE_TYPES` الثابتة فقط
  (`_MENU_BASE`/`_MENU_AUTRES`/`_MENU_LIBRE`) — لا رُبريكات مخصَّصة جديدة
  في القائمة.
- **واجهة إدارة الكتالوج**: `ui2/paie/companies.py` تدير الشركات فقط، لا
  CRUD للرُبريكات. تعديل تصنيف رُبريكة اليوم = `repository.update_rubrique`
  مباشرة أو سكربت. (على الأرجح توسيع `companies.py` أو شاشة خلف
  `SHOW_ADMIN_SCREENS`.)
- **قيد موثَّق:** `panier`/`transport` المُعاد تصنيفهما عبر الكتالوج
  (غير `(cotisable=0, imposable=1)`) يُطويان كـ Prime عامّ **بلا تنسيب
  §1.2.3** — تنسيب السلة/النقل مقصور على مسارهما الخاصّ في `calc.py`.
