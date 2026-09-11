from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import socket
import sys

import psutil
import qrcode
from qrcode.image.pure import PyPNGImage
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget)

from .network import discover
from .server import SharedFile, TransferService, size_text


STYLE = """
QWidget{background:#191b1e;color:#f2f3f5;font-family:'Segoe UI';font-size:14px}
QLabel{background:transparent}QLabel#eyebrow{color:#949ca8;font-size:11px;font-weight:650;letter-spacing:2px}
QLabel#title{font-size:34px;font-weight:700;letter-spacing:-1px}QLabel#muted{color:#9da5b0}
QFrame#panel{background:#24272c;border:1px solid #383d45;border-radius:14px}
QFrame#drop{background:#202328;border:2px dashed #505762;border-radius:14px}
QPushButton{background:#2c3037;border:1px solid #454c56;border-radius:8px;padding:10px 16px;font-weight:600}
QPushButton:hover{background:#393f48}QPushButton:pressed{background:#454d59}
QPushButton#primary{background:#f2f3f5;color:#1c2025;border:1px solid #f2f3f5}
QPushButton#primary:hover{background:#dce0e6}QPushButton:disabled{color:#747b85;background:#23262b;border-color:#343941}
QComboBox{background:#24272c;border:1px solid #454c56;border-radius:7px;padding:9px 12px;min-height:22px}
QComboBox QAbstractItemView{background:#24272c;selection-background-color:#454d59}
QListWidget{background:#202328;border:1px solid #383d45;border-radius:10px;outline:none;padding:6px}
QListWidget::item{padding:13px 10px;border-bottom:1px solid #353a42}
QListWidget::item:selected{background:#343a44;border-radius:5px}
QToolTip{background:#f3f4f5;color:#202328;border:0;padding:5px}
"""


HELP = """Connect your phone and PC to the same trusted home or office network. Scan the QR with your phone camera, then open the link in Chrome or Edge. No phone app is required.

If the phone cannot connect:
• Check the selected adapter and IP. Choose your real Wi-Fi or Ethernet connection. Stop sharing before changing it, then Start Server and scan the new QR.
• If Windows asks about network access, allow LocalDrop only on your trusted Private network. For source runs the prompt may name Python. LocalDrop never edits firewall settings or elevates itself.
• If you previously blocked access, open Windows Security → Firewall & network protection → Allow an app through firewall. Allow the LocalDrop executable on Private networks only. For a tighter rule, an administrator can restrict inbound TCP to the displayed port, selected local IP, and Local Subnet. Remove the rule when no longer needed. Do not turn off the firewall.
• Guest Wi-Fi, school/hotel networks, or router AP/client isolation can prevent devices from talking even on the same Wi-Fi name. Use a trusted non-guest network or a phone hotspot with the PC connected. A timeout alone cannot prove isolation; firewall, VPN, routing, or an incorrect IP can also cause it.
• Stop and refresh adapters after changing networks. VPNs may alter routing.

Online means the local listener is running; it does not prove the phone can reach it. If Wi-Fi disconnects, LocalDrop stops sharing when it notices the selected address is gone.

Privacy and limits:
Anyone with the session link on a reachable network can download the queue. HTTP is unencrypted: use a trusted local network, and do not port-forward this app. Stop Server invalidates the link and cancels transfers; Clear Queue also removes the queue. Files already downloaded stay on the phone.

Download All builds one uncompressed ZIP on the PC's temporary disk, requiring roughly the queued files' total size in free space. One ZIP at a time is supported. Temporary ZIPs are removed when the request finishes or sharing stops. Individual downloads support byte ranges; ZIP downloads restart from the beginning. Keep queued files unchanged during transfers; no permanent snapshot is made. Folders are not accepted; zip folders yourself first.
"""


class Bridge(QObject):
    finished = Signal(object, object)


class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self, pick):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(205)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        label = QLabel("Drop files here")
        label.setStyleSheet("font-size:20px;font-weight:600")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        hint = QLabel("A few photos. A big video. Anything you need.")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        button = QPushButton("Choose files")
        button.setObjectName("primary")
        button.clicked.connect(pick)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.files_dropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


def make_qr(url):
    image = qrcode.make(url, image_factory=PyPNGImage, box_size=5, border=4)
    stream = io.BytesIO()
    image.save(stream)
    return stream.getvalue()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LocalDrop")
        self.resize(1050, 800)
        self.setMinimumSize(900, 760)
        self.service = TransferService()
        self.files = []
        self.busy = False
        self.closing = False
        self.allow_close = False
        self.url = ""
        self.address = ""
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="LocalDrop-actions")
        self.bridge = Bridge()
        self.bridge.finished.connect(self.finished)
        self.callback = None
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(32, 26, 32, 22)
        outer.setSpacing(19)
        top = QHBoxLayout()
        brand = QLabel("LocalDrop")
        brand.setStyleSheet("font-size:20px;font-weight:700")
        top.addWidget(brand)
        top.addStretch()
        self.status = QLabel("●  Offline")
        self.status.setObjectName("muted")
        top.addWidget(self.status)
        outer.addLayout(top)
        title = QLabel("From your PC. To your phone.")
        title.setObjectName("title")
        outer.addWidget(title)
        subtitle = QLabel("Add files, scan the code, and download. All on your local network.")
        subtitle.setObjectName("muted")
        outer.addWidget(subtitle)
        body = QHBoxLayout()
        body.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(14)
        self.drop = DropZone(self.pick)
        self.drop.files_dropped.connect(self.add_files)
        left.addWidget(self.drop)
        self.queue_label = QLabel("QUEUE  /  0 FILES")
        self.queue_label.setObjectName("eyebrow")
        left.addWidget(self.queue_label)
        self.queue = QListWidget()
        self.queue.setMinimumHeight(125)
        self.queue.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        left.addWidget(self.queue, 1)
        controls = QHBoxLayout()
        self.start_button = QPushButton("Start Server")
        self.start_button.clicked.connect(self.toggle_server)
        self.clear_button = QPushButton("Clear Queue")
        self.clear_button.clicked.connect(self.clear)
        controls.addWidget(self.start_button)
        controls.addWidget(self.clear_button)
        controls.addStretch()
        left.addLayout(controls)
        body.addLayout(left, 1)
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(306)
        panel.setMinimumHeight(460)
        right = QVBoxLayout(panel)
        right.setContentsMargins(23, 23, 23, 23)
        right.setSpacing(12)
        caption = QLabel("SCAN & SAVE")
        caption.setObjectName("eyebrow")
        right.addWidget(caption)
        self.qr = QLabel("Add files to create\nyour QR code")
        self.qr.setFixedSize(230, 230)
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setStyleSheet("background:#1c1f23;border:1px solid #424852;border-radius:10px;color:#aeb5c0")
        right.addWidget(self.qr, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.endpoint = QLabel("Server offline")
        self.endpoint.setWordWrap(True)
        self.endpoint.setMinimumHeight(38)
        self.endpoint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.endpoint)
        self.copy_button = QPushButton("Copy sharing link")
        self.copy_button.clicked.connect(self.copy_link)
        right.addWidget(self.copy_button)
        hint = QLabel("Scan with your phone camera.\nOpen the link in Chrome or Edge.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setMinimumHeight(36)
        hint.setStyleSheet("line-height:1.5;font-size:12px")
        right.addWidget(hint)
        right.addStretch()
        body.addWidget(panel)
        outer.addLayout(body, 1)
        network_row = QHBoxLayout()
        network_row.addWidget(QLabel("Network"))
        self.adapters = QComboBox()
        self.adapters.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        network_row.addWidget(self.adapters, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        network_row.addWidget(self.refresh_button)
        help_button = QPushButton("Connection help")
        help_button.clicked.connect(self.help)
        network_row.addWidget(help_button)
        outer.addLayout(network_row)
        self.notice = QLabel("Finding your network adapters…")
        self.notice.setWordWrap(True)
        self.notice.setObjectName("muted")
        self.notice.setMinimumHeight(38)
        outer.addWidget(self.notice)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.check_network)
        self.timer.start()
        self.refresh()

    def submit(self, action, callback, message):
        self.busy = True
        self.callback = callback
        self.notice.setText(message)
        self.sync_controls()
        future = self.executor.submit(action)
        def complete(f):
            try:
                result, error = f.result(), None
            except Exception as exc:
                result, error = None, exc
            self.bridge.finished.emit(result, error)
        future.add_done_callback(complete)

    def finished(self, result, error):
        self.busy = False
        callback = self.callback
        self.callback = None
        if error:
            self.notice.setText(f"Could not complete the action: {error}")
        elif callback:
            callback(result)
        self.sync_controls()
        if self.closing and not self.busy:
            self.finish_close()

    def sync_controls(self):
        active = bool(self.service.server)
        self.drop.setEnabled(not self.busy and not self.closing)
        self.start_button.setEnabled(not self.busy and bool(self.files) and (active or self.adapters.currentData() is not None))
        self.start_button.setText("Stop Server" if active else "Start Server")
        self.clear_button.setEnabled(not self.busy and bool(self.files))
        self.adapters.setEnabled(not active and not self.busy)
        self.refresh_button.setEnabled(not active and not self.busy)
        self.copy_button.setEnabled(active and not self.busy and bool(self.url))
        self.status.setText("●  Online" if active else "●  Offline")
        self.status.setStyleSheet("color:#63c795" if active else "color:#9da5b0")

    def refresh(self):
        if not self.busy:
            self.submit(discover, self.set_adapters, "Finding your network adapters…")

    def set_adapters(self, choices):
        previous = self.adapters.currentData()
        self.adapters.clear()
        for adapter in choices:
            self.adapters.addItem(adapter.label, adapter.ip)
        index = self.adapters.findData(previous)
        if index >= 0:
            self.adapters.setCurrentIndex(index)
        self.notice.setText("Ready. Adding files starts sharing automatically. Use a trusted local network."
                            if choices else "No usable IPv4 connection. Connect to Wi-Fi or Ethernet, then Refresh.")

    def pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose files to share")
        if paths:
            self.add_files(paths)

    def add_files(self, paths):
        if self.busy or not paths:
            return
        existing = tuple(self.files)
        def collect():
            files, rejected = list(existing), []
            known = {str(f.path).casefold() for f in files}
            for path in paths:
                try:
                    entry = SharedFile.create(path)
                    key = str(entry.path).casefold()
                    if key not in known:
                        files.append(entry)
                        known.add(key)
                except (OSError, ValueError):
                    rejected.append(str(path))
            self.service.update(files)
            return files, rejected
        def done(result):
            self.files, rejected = result
            self.render_queue()
            if rejected:
                QMessageBox.information(self, "Some items were skipped", "Folders or unreadable files were skipped:\n" + "\n".join(rejected[:8]))
            if self.files and not self.service.server and self.adapters.currentData():
                self.start()
            else:
                self.notice.setText("Queue updated. Refresh the page on your phone to see added files." if self.service.server else "Files queued. Connect to a network, Refresh, then Start Server.")
        self.submit(collect, done, "Adding files…")

    def render_queue(self):
        self.queue.clear()
        for i, file in enumerate(self.files, 1):
            item = QListWidgetItem(f"{i:02d}   {file.name}   ·   {size_text(file.size)}")
            item.setToolTip(str(file.path))
            self.queue.addItem(item)
        self.queue_label.setText(f"QUEUE  /  {len(self.files)} FILES  ·  {size_text(sum(f.size for f in self.files))}")

    def start(self):
        ip = self.adapters.currentData()
        if not ip:
            return
        files = tuple(self.files)
        def action():
            url = self.service.start(ip, files)
            try:
                return url, make_qr(url), ip
            except Exception:
                self.service.stop()
                raise
        def ready(result):
            self.url, png, self.address = result
            pixmap = QPixmap()
            pixmap.loadFromData(png)
            # Keep QR modules at their original integer pixel size.
            self.qr.setStyleSheet("background:white;border:0;border-radius:0")
            self.qr.setPixmap(pixmap)
            self.endpoint.setText(f"{ip}:{self.service.server.server_port}\nLocal server is running")
            self.notice.setText("Scan the QR on your phone. If Windows asks, allow access on your trusted Private network.")
        self.submit(action, ready, "Starting a private sharing session…")

    def toggle_server(self):
        if self.service.server:
            self.stop()
        else:
            self.start()

    def reset_connection(self):
        self.url = self.address = ""
        self.qr.clear()
        self.qr.setStyleSheet("background:#1c1f23;border:1px solid #424852;border-radius:10px;color:#aeb5c0")
        self.qr.setText("Sharing is stopped\nStart Server for a new QR")
        self.endpoint.setText("Server offline")

    def stop(self, message="Sharing stopped. The previous link no longer works."):
        def done(_):
            self.reset_connection()
            self.notice.setText(message)
        self.submit(self.service.stop, done, "Stopping sharing and closing transfers…")

    def clear(self):
        def done(_):
            self.files = []
            self.render_queue()
            self.reset_connection()
            self.qr.setText("Add files to create\nyour QR code")
            self.notice.setText("Queue cleared and server stopped. Your original files are unchanged.")
        self.submit(self.service.stop, done, "Clearing the queue and closing transfers…")

    def copy_link(self):
        QApplication.clipboard().setText(self.url)
        self.notice.setText("Sharing link copied. Anyone on a reachable network with this link can download the queue.")

    def help(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Connecting your phone")
        dialog.setText("LocalDrop connection guide")
        dialog.setInformativeText(HELP)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def check_network(self):
        if self.busy or not self.address:
            return
        try:
            stats = psutil.net_if_stats()
            active = {a.address for name, entries in psutil.net_if_addrs().items()
                      if name in stats and stats[name].isup for a in entries if a.family == socket.AF_INET}
            if self.address not in active:
                self.stop("The selected network disconnected. Reconnect, Refresh, then Start Server.")
        except OSError:
            pass

    def finish_close(self):
        if self.service.server:
            self.submit(self.service.stop, lambda _: None, "Closing active transfers…")
        else:
            self.allow_close = True
            self.executor.shutdown(wait=False)
            self.close()

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.closing = True
        self.timer.stop()
        self.sync_controls()
        if not self.busy:
            self.finish_close()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .selftest import run
        return run(sys.argv[2])
    app = QApplication(sys.argv)
    app.setApplicationName("LocalDrop")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    return app.exec()
