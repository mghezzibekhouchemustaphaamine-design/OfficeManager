"""أيقونات CommandBar — Qt Standard Icons حيث تُناسب دلالياً، وplaceholder
مركزيّ واحد (لا Emoji) لما لا يوجد له مقابلٌ قياسيّ مناسب (P2.1 §9).

SAVE/UNDO/REDO لها مقابلٌ بصريّ مألوف ضمن ``QStyle.StandardPixmap`` —
تُستعمَل مباشرةً (تتبع Style/Theme النظام تلقائياً). PRINT/FINALIZE/
DUPLICATE ليس لها مقابلٌ قياسيّ دقيق في Qt؛ بدل أيقوناتٍ عشوائية
متفرّقة لكلٍّ منها، دالّةٌ واحدة مركزية (``_placeholder_icon``) ترسم
بادجاً حرفياً محايداً بألوان الـtheme الحالية."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

from ui2 import theme
from ui2.shell.commands import CommandId

#  ‏مقابلٌ دلاليّ معقول ضمن أيقونات Qt القياسية (تتبع Style النظام).
_STANDARD_ICON_MAP = {
    CommandId.SAVE: QStyle.SP_DialogSaveButton,
    CommandId.UNDO: QStyle.SP_ArrowBack,
    CommandId.REDO: QStyle.SP_ArrowForward,
}

#  ‏لا مقابل Qt Standard دقيق لهذه الأوامر — بادجٌ حرفيّ محايد بدل
#  أيقوناتٍ Emoji أو ملفّات صور عشوائية (P2.1 §9).
_PLACEHOLDER_GLYPH = {
    CommandId.PRINT: "P",
    CommandId.FINALIZE: "F",
    CommandId.DUPLICATE: "D",
}

_PLACEHOLDER_SIZE = 16


def _placeholder_icon(glyph: str) -> QIcon:
    """بادجٌ مركزيّ واحد — مربّعٌ مستدير الزوايا بحرفٍ واحد، بلا Emoji
    وبلا أصولٍ خارجية؛ تلوينه من الـtheme الحاليّ فيبقى متّسقاً بصرياً."""
    pix = QPixmap(_PLACEHOLDER_SIZE, _PLACEHOLDER_SIZE)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(theme.TEXT_DIM))
    painter.drawRoundedRect(QRectF(0.5, 0.5, _PLACEHOLDER_SIZE - 1, _PLACEHOLDER_SIZE - 1), 3, 3)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(10)
    painter.setFont(font)
    painter.setPen(QColor(theme.SURFACE))
    painter.drawText(pix.rect(), Qt.AlignCenter, glyph)
    painter.end()
    return QIcon(pix)


def command_icon(command_id: CommandId) -> QIcon:
    """أيقونة Command واحدة — Standard إن وُجد مقابلٌ مناسب، وإلا
    placeholder مركزيّ. لا حالة، بلا كاش — رخيصةٌ بما يكفي للاستدعاء
    عند كلّ إنشاء QAction (مرّةً واحدة لكلّ Command في عمر التطبيق)."""
    std = _STANDARD_ICON_MAP.get(command_id)
    if std is not None:
        app = QApplication.instance()
        if app is not None:
            return app.style().standardIcon(std)
    return _placeholder_icon(_PLACEHOLDER_GLYPH.get(command_id, "?"))
