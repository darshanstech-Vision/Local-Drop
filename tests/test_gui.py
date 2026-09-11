import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from localdrop.app import STYLE, Window, make_qr


def settle(app, window, timeout=15):
    deadline = time.monotonic() + timeout
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    app.processEvents()
    assert not window.busy


def test_gui_drop_start_stop_clear_and_close(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    settle(app, window)
    # Deliberately use loopback for automated validation, never advertised to users.
    window.adapters.clear()
    window.adapters.addItem("Test loopback", "127.0.0.1")
    path = tmp_path / "sample.txt"
    path.write_text("LocalDrop GUI test")
    try:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.drop.dropEvent(event)
        settle(app, window)
        assert len(window.files) == 1
        assert window.service.server and window.url
        assert not window.qr.pixmap().isNull()
        assert window.start_button.text() == "Stop Server"
        assert not window.adapters.isEnabled()
        window.resize(window.minimumSize())
        app.processEvents()
        assert window.endpoint.geometry().top() >= window.qr.geometry().bottom()
        window.stop()
        settle(app, window)
        assert not window.service.server and not window.url
        assert len(window.files) == 1
        window.start()
        settle(app, window)
        window.clear()
        settle(app, window)
        assert not window.files and not window.service.server
    finally:
        window.close()
        settle(app, window)


def test_qr_is_png():
    assert make_qr("http://192.168.1.10:8000/s/example/").startswith(b"\x89PNG\r\n\x1a\n")
