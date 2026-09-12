"""تزاوجات (Adapters) Shell↔خدمة حقيقية — P3.

كلّ ملفٍ هنا يعرف **الطرفين**: عقد ``WorkSession``/``WorkspaceManager``
من جهة، وAPI العامّ لشاشة الخدمة الحقيقية من جهةٍ أخرى (P3 §3/§28).
Shell core (``workspace.py``/``workspace_manager.py``/``command_
manager.py``/``close_controller.py``) لا يستورد من هنا، والعكس أيضاً —
الربط يتمّ بتسجيل factory عبر ``ui2.shell.services.
register_new_work_factory`` من نقطة الدخول (``ui2/shell/__main__.py``)
قبل إنشاء ``OfficeMainWindow`` الأولى."""
