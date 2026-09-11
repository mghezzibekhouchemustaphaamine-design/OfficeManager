"""Shell — الهيكل الأم للبرنامج (Prototype).

هذا الحزمة تجسّد `OfficeMainWindow` كإطار عامّ يحتضن الخدمات مستقبلاً:
TopBar + Explorer placeholder + WorkspaceHost (CommandBar/WorkTabBar/
ContentStack). **لا** ربط حقيقي بخدمات Paie/CD هنا، و**لا** Explorer
حقيقي، و**لا** Login/Lock حقيقي — راجع docs/CHANGELOG.md لتفاصيل النطاق.

هذا لا يستبدل `ui2/window.py` القديم (المُستخدَم اليوم فعلياً)؛ الاثنان
يتعايشان إلى أن يُعتمَد Shell الجديد رسمياً.

التشغيل التجريبي المستقل:
    python -m ui2.shell
"""
