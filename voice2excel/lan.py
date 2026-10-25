"""دسترسی از گوشی در شبکه محلی: فقط صفحه آپلود، با رمز.

قواعد امنیتی:
- درخواست از خود رایانه (loopback) بدون محدودیت است، مثل قبل.
- درخواست از دستگاه دیگر فقط به صفحه /m، فونت‌ها و API آپلود (/api/m/...) دسترسی دارد؛
  بقیه (رکوردها، اکسل، تنظیمات، فایل‌ها) فقط از روی خود رایانه.
- API آپلود رمز شش‌رقمی می‌خواهد؛ پس از چند تلاش ناموفق، آن دستگاه مدتی مسدود می‌شود.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import socket
import threading
import time

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
REMOTE_PAGES = {"/m", "/m/", "/static/m.js", "/static/recording-guide.html"}
REMOTE_PREFIXES = ("/api/m/", "/static/fonts/")
MAX_FAILURES = 8
WINDOW_SECONDS = 600


def is_local(host: str | None) -> bool:
    if not host:
        return False
    if host in LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def remote_path_allowed(path: str) -> bool:
    return path in REMOTE_PAGES or path.startswith(REMOTE_PREFIXES)


def needs_pin(path: str) -> bool:
    return path.startswith("/api/m/")


def new_device_token() -> str:
    """کلید هر گوشی پس از یک بار ورود با رمز؛ خود رمز روی گوشی ذخیره نمی‌شود."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """در پایگاه داده فقط هش کلید نگه داشته می‌شود."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def pin_ok(given: str | None, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(str(given or ""), expected)


class FailureLimiter:
    """محدودیت تلاش ناموفق رمز برای هر نشانی."""

    def __init__(self, max_failures: int = MAX_FAILURES, window: float = WINDOW_SECONDS):
        self.max_failures = max_failures
        self.window = window
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, host: str, now: float) -> list[float]:
        return [t for t in self._fails.get(host, []) if now - t < self.window]

    def blocked(self, host: str) -> bool:
        with self._lock:
            return len(self._recent(host, time.time())) >= self.max_failures

    def fail(self, host: str) -> None:
        with self._lock:
            now = time.time()
            self._fails[host] = self._recent(host, now) + [now]

    def reset(self, host: str) -> None:
        with self._lock:
            self._fails.pop(host, None)


def lan_addresses() -> list[str]:
    """نشانی‌های IPv4 خصوصی این رایانه در شبکه محلی."""
    found: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:  # نشانی رابطی که مسیر پیش‌فرض شبکه از آن می‌گذرد (بدون ارسال بسته)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.add(s.getsockname()[0])
    except OSError:
        pass
    out = []
    for a in sorted(found):
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback and not ip.is_link_local:
            out.append(a)
    return out
