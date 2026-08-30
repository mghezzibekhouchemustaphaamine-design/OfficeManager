"""إعداد سجل مركزي للتطبيق.

السجل مخصص لأخطاء التشغيل والمشاكل التي يصعب تشخيصها من الواجهة فقط.
لا نسجل محتوى نماذج CD أو بيانات العملاء حتى لا نحول ملف السجل إلى مخزن
بيانات شخصية.
"""
import logging
import os
from logging.handlers import RotatingFileHandler


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(_PROJECT_ROOT, "office_manager.log")


def configure_logging():
    """يهيئ Logger واحداً للتطبيق ويعيده.

    الإعداد idempotent: يمكن استدعاؤه أكثر من مرة دون إضافة handlers
    مكررة. ملف السجل محدود الحجم حتى لا يكبر بلا نهاية.
    """
    logger = logging.getLogger("officemanager")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    try:
        handler = RotatingFileHandler(
            LOG_PATH,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        # فشل كتابة السجل لا يجب أن يمنع تشغيل البرنامج.
        logger.addHandler(logging.NullHandler())

    return logger
