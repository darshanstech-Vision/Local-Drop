from __future__ import annotations

import errno
import html
import os
from pathlib import Path
import secrets
import socket
import stat
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit


@dataclass(frozen=True)
class SharedFile:
    id: str
    path: Path
    name: str
    size: int
    modified: int
    device: int
    inode: int

    @classmethod
    def create(cls, value):
        path = Path(value).resolve(strict=True)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Only individual files can be shared.")
        # Opening now catches unreadable files before they enter the queue.
        with path.open("rb"):
            pass
        return cls(secrets.token_urlsafe(12), path, path.name, info.st_size,
                   info.st_mtime_ns, info.st_dev, info.st_ino)

    def open(self):
        if self.path.resolve(strict=True) != self.path:
            raise OSError("The queued file was replaced.")
        stream = self.path.open("rb")
        info = os.fstat(stream.fileno())
        if (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino) != (
                self.size, self.modified, self.device, self.inode):
            stream.close()
            raise OSError("The queued file changed. Clear the queue and add it again.")
        return stream


def size_text(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def page(files, prefix):
    count = len(files)
    rows = "".join(
        f'<li><span class="number">{i:02d}</span><div class="details">'
        f'<strong>{html.escape(f.name)}</strong><small>{size_text(f.size)}</small></div>'
        f'<a class="download" href="{prefix}/file/{f.id}" download>Download</a></li>'
        for i, f in enumerate(files, 1))
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LocalDrop · Files from your PC</title><style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#191b1e;color:#f3f4f5}
*{box-sizing:border-box}body{margin:0}main{max-width:740px;margin:auto;padding:38px 22px 130px}
header{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:52px}
.brand{font-size:20px;font-weight:750;letter-spacing:-.6px}.badge{font-size:12px;color:#b5bac2;border:1px solid #41454c;padding:7px 10px;border-radius:24px}
h1{font-size:clamp(30px,6vw,42px);line-height:1.15;letter-spacing:-1.4px;margin:0 0 14px}
p{color:#aeb3bc;line-height:1.6}ul{list-style:none;padding:0;margin:30px 0}li{display:flex;align-items:center;gap:16px;padding:22px 18px;background:#24272c;border:1px solid #383d45;border-radius:12px;margin-bottom:12px}
.number{color:#89919d;font-size:13px}.details{flex:1;min-width:0}strong{display:block;font-size:16px;overflow-wrap:anywhere}small{display:block;color:#9da5b0;margin-top:7px}
a{color:inherit}.download{display:inline-block;text-align:center;background:#33ad73;color:#081c12;text-decoration:none;font-size:14px;font-weight:750;border-radius:8px;padding:12px 16px;white-space:nowrap}
a:focus-visible{outline:3px solid white;outline-offset:4px}.note{font-size:13px}.footer{position:fixed;bottom:0;left:0;right:0;background:#191b1ef5;border-top:1px solid #383d45;padding:16px 22px max(16px,env(safe-area-inset-bottom))}.bar{max-width:696px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:16px}.bar small{margin:0}.bar .download{padding:14px 24px}
@media(max-width:420px){li{flex-wrap:wrap;gap:12px}.details{flex-basis:75%}li .download{width:100%}header{margin-bottom:36px}.bar small{max-width:100px}.number{align-self:flex-start;padding-top:3px}}
</style></head><body><main><header><div class="brand">LocalDrop</div><span class="badge">Local network</span></header>'''
        + f'<h1>{"Your file is ready." if count == 1 else "Your files are ready."}</h1>'
        + f'<p>{count} file{"s" if count != 1 else ""} · {size_text(sum(f.size for f in files))} · From your PC</p>'
        + f'<ul>{rows}</ul><p class="note">Keep LocalDrop open on your PC until downloads finish. '
          'Download All prepares a ZIP; large queues may take a moment. '
        + f'<a href="{prefix}/">Refresh file list</a>.</p></main>'
        + f'<div class="footer"><div class="bar"><small>{count} file{"s" if count != 1 else ""} · One ZIP</small>'
        + f'<a class="download" href="{prefix}/all.zip" download>Download All ↓</a></div></div></body></html>').encode()


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, files):
        self.token = secrets.token_urlsafe(24)
        self.files = tuple(files)
        self.stopping = threading.Event()
        self.lock = threading.Lock()
        self.connections = set()
        self.slots = threading.BoundedSemaphore(12)
        self.zip_slot = threading.BoundedSemaphore(1)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if self.stopping.is_set() or not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        with self.lock:
            self.connections.add(request)
        try:
            super().process_request(request, client_address)
        except Exception:
            with self.lock:
                self.connections.discard(request)
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.lock:
                self.connections.discard(request)
            self.slots.release()

    def handle_error(self, request, client_address):
        # Expected disconnects must not display paths or session tokens in logs.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalDrop"
    sys_version = ""

    def setup(self):
        # Windows may leave a blocking read asleep after shutdown from another
        # thread. A short poll bound also makes incomplete headers cancellable.
        self.request.settimeout(1)
        super().setup()

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header("Connection", "close")
        super().end_headers()

    def do_HEAD(self):
        self.serve(head=True)

    def do_GET(self):
        self.serve(head=False)

    def serve(self, head):
        srv = self.server
        host, port = srv.server_address
        if self.headers.get("Host") != f"{host}:{port}":
            self.send_error(403, "Use the exact address shown in LocalDrop.")
            return
        prefix = f"/s/{srv.token}"
        route = urlsplit(self.path).path
        with srv.lock:
            files = srv.files
        if srv.stopping.is_set():
            self.send_error(503, "Sharing stopped.")
            return
        if route in (prefix, prefix + "/"):
            data = page(files, prefix)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not head:
                self.wfile.write(data)
        elif route == prefix + "/all.zip":
            self.serve_zip(files, head)
        elif route.startswith(prefix + "/file/"):
            file_id = route[len(prefix + "/file/"):]
            match = next((f for f in files if f.id == file_id), None)
            if match:
                self.serve_file(match, head)
            else:
                self.send_error(404, "File not shared.")
        else:
            self.send_error(404, "This sharing link is unavailable.")

    def transfer(self, stream, count):
        last_progress = time.monotonic()
        while count and not self.server.stopping.is_set():
            chunk = stream.read(min(count, 1024 * 1024))
            if not chunk:
                break
            pending = memoryview(chunk)
            while pending and not self.server.stopping.is_set():
                try:
                    sent = self.connection.send(pending)
                    if not sent:
                        return
                    pending = pending[sent:]
                    last_progress = time.monotonic()
                except socket.timeout:
                    if time.monotonic() - last_progress > 30:
                        return
            count -= len(chunk)

    def serve_file(self, item, head):
        try:
            stream = item.open()
        except OSError:
            self.send_error(410, "File moved, changed, or became unreadable. Add it again on the PC.")
            return
        with stream:
            start, end, partial = 0, item.size - 1, False
            requested = self.headers.get("Range")
            if requested:
                try:
                    unit, value = requested.split("=", 1)
                    first, last = value.split("-", 1)
                    if unit != "bytes" or "," in value or not (first or last):
                        raise ValueError()
                    if first:
                        start = int(first)
                        end = min(int(last), end) if last else end
                    else:
                        suffix = int(last)
                        if suffix <= 0:
                            raise ValueError()
                        start = max(0, item.size - suffix)
                    if start < 0 or end < start or start >= item.size:
                        raise ValueError()
                    partial = True
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{item.size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename=\"download\"; filename*=UTF-8''" + quote(item.name, safe=""))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{item.size}")
            self.end_headers()
            if not head:
                stream.seek(start)
                self.transfer(stream, end - start + 1)

    def serve_zip(self, files, head):
        if not self.server.zip_slot.acquire(False):
            self.send_error(429, "Another ZIP is being prepared or downloaded. Try again shortly.")
            return
        try:
            # Disk-backed and automatically removed, including on disconnect/stop.
            with tempfile.TemporaryFile(prefix="localdrop-", suffix=".zip") as archive:
                try:
                    used = set()
                    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
                        for item in files:
                            name = item.name
                            suffix = 2
                            while name.casefold() in used:
                                name = f"{Path(item.name).stem} ({suffix}){Path(item.name).suffix}"
                                suffix += 1
                            used.add(name.casefold())
                            with item.open() as source, bundle.open(name, "w", force_zip64=True) as target:
                                while chunk := source.read(1024 * 1024):
                                    if self.server.stopping.is_set():
                                        return
                                    target.write(chunk)
                    length = archive.tell()
                    archive.seek(0)
                except OSError:
                    self.send_error(409, "Cannot prepare ZIP. Check files and free temporary disk space on the PC.")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="LocalDrop-files.zip"')
                self.send_header("Content-Length", str(length))
                self.end_headers()
                if not head:
                    self.transfer(archive, length)
        finally:
            self.server.zip_slot.release()


class TransferService:
    """Lifecycle methods are called serially by the GUI's worker executor."""

    def __init__(self):
        self.server = None
        self.thread = None

    @property
    def url(self):
        if not self.server:
            return ""
        host, port = self.server.server_address
        return f"http://{host}:{port}/s/{self.server.token}/"

    def start(self, ip, files, first_port=8000, last_port=8099):
        if self.server:
            raise RuntimeError("Stop the existing session first.")
        if not files:
            raise ValueError("Add at least one file first.")
        for port in range(first_port, last_port + 1):
            try:
                server = LocalHTTPServer((ip, port), files)
                break
            except OSError as error:
                if error.errno not in (errno.EADDRINUSE, errno.EACCES, 10048, 10013):
                    raise
        else:
            raise OSError(f"No available port between {first_port} and {last_port}.")
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, name="LocalDrop-listener")
        self.thread.start()
        return self.url

    def update(self, files):
        if self.server:
            with self.server.lock:
                self.server.files = tuple(files)

    def stop(self):
        server = self.server
        if not server:
            return
        server.stopping.set()
        server.shutdown()
        with server.lock:
            connections = tuple(server.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        server.server_close()
        self.thread.join()
        self.server = self.thread = None
