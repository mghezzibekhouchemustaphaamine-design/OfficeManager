# CLAUDE.md — دليل العمل على OfficeManager

## نظرة سريعة

برنامج سطح مكتب (Python 3.12 + Tkinter + SQLite) لمكتب خدمات جزائري:
توليد مستندات العمل من استمارات فوق صورة النموذج، مع أرشفة وسجلّ. الواجهة
عربية، المستندات بالفرنسية. نقطة التشغيل الوحيدة: `python main.py`.

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
python -m unittest discover -s programme/payroll/tests      # النواة — 38 اختباراً
python -m unittest discover -s ui2/tests                    # قاعدة الشاشة Screen — 10
python -m unittest discover -s ui2/paie/tests               # شاشة الكشف (pinning) — 8
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

**الحالة:** الطبقة التحتية موجودة وتخدم، الواجهة ما تستعملهاش.

- جدول `rubrique_catalogue` لكل شركة موجود؛ `programme/payroll/repository.py`
  فيه `create_rubrique` / `update_rubrique` / `list_rubriques` /
  `seed_catalogue` (يعبّي ~19 بنداً افتراضياً عند إنشاء شركة).
- **لكن** `ui2/paie/bulletin.py` يبني قائمة «＋ إضافة سطر» من
  `programme/payroll/lignes.py::LINE_TYPES` الثابتة فقط
  (`_MENU_BASE` / `_MENU_AUTRES` / `_MENU_LIBRE`) — لا يقرأ
  `list_rubriques` إطلاقاً. يستدعي `seed_catalogue` عند أول حفظ فقط.
- `ui2/paie/companies.py` تدير الشركات (إضافة/تعديل) فقط — لا واجهة CRUD
  للبنود.

**النتيجة:** المستخدم يقدر يزيد **سطراً حرّاً** لمرّة واحدة (نوع `libre`:
تسمية + مبلغ + تصنيف cotisable/imposable إلزامي)، لكن **ما يقدرش يعرّف
بنداً دائماً جديداً** بمنطق حسابه الخاص يظهر في قائمة كل كشف.

**المطلوب لاحقاً:** ربط قائمة شاشة الكشف بـ`list_rubriques(entreprise_id)`
إلى جانب `LINE_TYPES`، + واجهة إدارة البنود (على الأرجح توسيع
`companies.py` أو شاشة مستقلّة خلف `SHOW_ADMIN_SCREENS`).
