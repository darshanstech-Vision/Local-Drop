import ipaddress
import json
import os
import socket
import subprocess
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class Adapter:
    name: str
    ip: str
    recommended: bool

    @property
    def label(self):
        return f"{self.name} · {self.ip}" + ("" if self.recommended else " (other adapter)")


def discover():
    physical = None
    if os.name == "nt":
        try:
            # Read-only. Hidden, bounded query; never requests administrator rights.
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-NetAdapter -Physical | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress"],
                capture_output=True, timeout=8, encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
            names = json.loads(result.stdout or "[]")
            physical = {names} if isinstance(names, str) else set(names or [])
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return select_adapters(psutil.net_if_addrs(), psutil.net_if_stats(), physical)


def select_adapters(addresses, stats, physical=None):
    choices = []
    virtual = ("virtual", "vmware", "vbox", "virtualbox", "wsl", "vethernet", "hyper-v",
               "vpn", "tap-", "tun", "tailscale", "zerotier", "loopback", "bluetooth")
    for name, entries in addresses.items():
        if name not in stats or not stats[name].isup:
            continue
        normal = not any(marker in name.lower() for marker in virtual)
        preferred = normal and (physical is None or name in physical)
        for entry in entries:
            if entry.family != socket.AF_INET:
                continue
            ip = ipaddress.ip_address(entry.address)
            if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                continue
            choices.append(Adapter(name, str(ip), preferred))
    return sorted(choices, key=lambda a: (not a.recommended,
                                         not any(s in a.name.lower() for s in ("wi-fi", "wifi", "wireless")), a.name, a.ip))
