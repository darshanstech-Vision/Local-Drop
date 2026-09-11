import concurrent.futures
import http.client
import io
import socket
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from localdrop.network import select_adapters
from localdrop.server import SharedFile, TransferService


def request(service, suffix="", method="GET", headers=None, route=None):
    parsed = urlsplit(service.url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    conn.request(method, route if route is not None else parsed.path + suffix, headers=headers or {})
    response = conn.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    conn.close()
    return result


@pytest.fixture
def running(tmp_path):
    (tmp_path / "hello.txt").write_bytes(b"0123456789")
    service = TransferService()
    files = [SharedFile.create(tmp_path / "hello.txt")]
    service.start("127.0.0.1", files, 0, 0)
    yield service, files
    service.stop()


def test_page_single_file_headers_and_head(running):
    service, files = running
    status, headers, body = request(service)
    assert status == 200
    assert b"Your file is ready." in body
    assert b"hello.txt" in body and b"Download All" in body
    assert headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    status, headers, body = request(service, f"file/{files[0].id}", method="HEAD")
    assert status == 200 and headers["Content-Length"] == "10" and body == b""


def test_exact_files_only_and_host_validation(running):
    service, files = running
    for route in ("/", "/etc/passwd", "/s/wrong/", urlsplit(service.url).path + "file/../hello.txt",
                  urlsplit(service.url).path + "file/%2e%2e%2fhello.txt"):
        assert request(service, route=route)[0] == 404
    assert request(service, headers={"Host": "untrusted.example"})[0] == 403
    assert request(service, method="POST")[0] == 501
    assert request(service, "file/" + files[0].id)[2] == b"0123456789"


@pytest.mark.parametrize("value,code,body", [
    ("bytes=2-5", 206, b"2345"), ("bytes=-3", 206, b"789"),
    ("bytes=8-", 206, b"89"), ("bytes=2-999", 206, b"23456789"),
    ("bytes=99-", 416, b""), ("bytes=-0", 416, b""),
    ("bytes=5-2", 416, b""), ("bytes=0-1,4-5", 416, b""),
    ("bananas=0-2", 416, b"")])
def test_ranges(running, value, code, body):
    service, files = running
    status, _, data = request(service, "file/" + files[0].id, headers={"Range": value})
    assert (status, data) == (code, body)


def test_zip_duplicate_names_unicode_and_zero_size(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    paths = [tmp_path / "a" / "same.txt", tmp_path / "b" / "same.txt", tmp_path / "नमस्ते.txt"]
    for path, value in zip(paths, [b"one", b"two", b""]):
        path.write_bytes(value)
    files = [SharedFile.create(p) for p in paths]
    service = TransferService()
    try:
        service.start("127.0.0.1", files, 0, 0)
        status, _, data = request(service, "all.zip")
        assert status == 200
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            assert bundle.namelist() == ["same.txt", "same (2).txt", "नमस्ते.txt"]
            assert [bundle.read(n) for n in bundle.namelist()] == [b"one", b"two", b""]
        status, headers, data = request(service, "file/" + files[-1].id)
        assert status == 200 and data == b"" and headers["Content-Length"] == "0"
        assert "filename*=UTF-8''%" in headers["Content-Disposition"]
    finally:
        service.stop()


def test_changed_and_removed_files_are_not_served(running):
    service, files = running
    files[0].path.write_bytes(b"changed")
    assert request(service, "file/" + files[0].id)[0] == 410
    assert request(service, "all.zip")[0] == 409
    files[0].path.unlink()
    assert request(service, "file/" + files[0].id)[0] == 410


def test_port_conflict_restart_and_token_invalidation(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("hello")
    files = [SharedFile.create(path)]
    occupied = socket.socket()
    occupied.bind(("127.0.0.1", 0))
    occupied.listen()
    port = occupied.getsockname()[1]
    service = TransferService()
    try:
        service.start("127.0.0.1", files, port, min(port + 100, 65535))
        assert service.server.server_port > port
        old_path = urlsplit(service.url).path
        old_port = service.server.server_port
        service.stop()
        service.stop()
        service.start("127.0.0.1", files, old_port, old_port + 10)
        assert urlsplit(service.url).path != old_path
        assert request(service, route=old_path)[0] == 404
    finally:
        service.stop()
        occupied.close()


def test_concurrent_downloads_queue_update_and_html_escape(running, tmp_path):
    service, files = running
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: request(service, "file/" + files[0].id)[2], range(12)))
    assert all(body == b"0123456789" for body in results)
    path = tmp_path / "A & B.txt"
    path.write_text("more")
    service.update(files + [SharedFile.create(path)])
    body = request(service)[2]
    assert b"Your files are ready." in body and b"A &amp; B.txt" in body


def test_stop_closes_idle_connections_and_releases_port(running):
    service, _ = running
    port = service.server.server_port
    client = socket.create_connection(("127.0.0.1", port))
    client.sendall(b"GET / HTTP/1.1\r\n")
    deadline = time.monotonic() + 2
    while not service.server.connections and time.monotonic() < deadline:
        time.sleep(.01)
    started = time.monotonic()
    service.stop()
    assert time.monotonic() - started < 2
    client.close()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_adapters_prefer_physical_wifi_and_skip_unusable():
    def addr(ip):
        return [SimpleNamespace(family=socket.AF_INET, address=ip)]
    addresses = {"VMware": addr("192.168.56.1"), "Ethernet": addr("192.168.1.2"),
                 "Wi-Fi": addr("192.168.1.3"), "Loopback": addr("127.0.0.1"),
                 "Disconnected": addr("10.0.0.4"), "Broken": addr("169.254.1.1")}
    stats = {name: SimpleNamespace(isup=name != "Disconnected") for name in addresses}
    choices = select_adapters(addresses, stats, {"Ethernet", "Wi-Fi"})
    assert [a.name for a in choices] == ["Wi-Fi", "Ethernet", "VMware"]
    assert choices[0].recommended and not choices[-1].recommended


def test_folders_rejected(tmp_path):
    with pytest.raises(ValueError):
        SharedFile.create(tmp_path)


def test_stalled_large_download_is_cancelled(tmp_path):
    path = tmp_path / "large.bin"
    with path.open("wb") as stream:
        stream.truncate(64 * 1024 * 1024)
    files = [SharedFile.create(path)]
    service = TransferService()
    service.start("127.0.0.1", files, 0, 0)
    host, port = service.server.server_address
    client = socket.create_connection((host, port))
    client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
    route = urlsplit(service.url).path + "file/" + files[0].id
    client.sendall(f"GET {route} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    try:
        time.sleep(.15)
        started = time.monotonic()
        service.stop()
        assert time.monotonic() - started < 3
    finally:
        client.close()
        service.stop()


def test_zip_tempfile_closed_and_zip_limit(running, monkeypatch):
    import localdrop.server as module
    service, _ = running
    opened = []
    original = module.tempfile.TemporaryFile
    def track(*args, **kwargs):
        result = original(*args, **kwargs)
        opened.append(result)
        return result
    monkeypatch.setattr(module.tempfile, "TemporaryFile", track)
    assert request(service, "all.zip")[0] == 200
    deadline = time.monotonic() + 2
    while not all(stream.closed for stream in opened) and time.monotonic() < deadline:
        time.sleep(.01)
    assert opened and all(stream.closed for stream in opened)
    service.server.zip_slot.acquire()
    try:
        assert request(service, "all.zip")[0] == 429
    finally:
        service.server.zip_slot.release()
