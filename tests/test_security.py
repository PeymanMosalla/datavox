"""آزمون‌های امنیتی: هر حفره‌ای که پیدا و بسته شده، اینجا یک آزمون دارد تا دوباره باز نشود."""
from fastapi.testclient import TestClient

from voice2excel import server

LOCAL = {"client": ("127.0.0.1", 50000), "base_url": "http://127.0.0.1:8765"}


def _client(**headers):
    return TestClient(server.app, **LOCAL, headers=headers)


# ---------- ۱. فرمان یا خواندن داده از صفحه سایت‌های دیگر ----------
def test_foreign_site_cannot_send_commands(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with _client() as c:
        # درخواست «ساده» مرورگر از سایت دیگر (فرم، بدون کلید): پیش‌تر پذیرفته می‌شد
        for path in ("/api/lan/new-pin", "/api/files/retry-failed", "/api/records/revalidate-all", "/api/shutdown"):
            r = c.post(path, headers={"Origin": "https://evil.example", "Content-Type": "text/plain"})
            assert r.status_code == 403, path
        # حتی بدون Origin، فرمان بدون کلید محرمانه پذیرفته نمی‌شود
        assert c.post("/api/files/retry-failed").status_code == 403
        assert c.post("/api/files/retry-failed", headers={"X-V2X-Token": "wrong"}).status_code == 403
        assert c.post("/api/files/retry-failed", headers=server.auth_headers()).status_code == 200
        # خواندن (GET) از صفحه خود برنامه بدون کلید ممکن است (پخش صدا، دانلود)؛ خواندن از سایت دیگر را مرورگر نمی‌گذارد
        assert c.get("/api/status").status_code == 200


def test_dns_rebinding_host_is_rejected(db, monkeypatch):
    """دامنه مهاجم که به 127.0.0.1 اشاره می‌کند: مرورگر آن را هم‌مبدأ می‌داند، پس خود برنامه باید رد کند."""
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with TestClient(server.app, client=("127.0.0.1", 50000), base_url="http://evil.example:8765",
                    headers=server.auth_headers()) as c:
        assert c.get("/api/records?filter=all").status_code == 403
        assert c.get("/api/fs", params={"path": "C:/Users"}).status_code == 403
        assert c.get("/").status_code == 403
    for host in ("localhost:8765", "127.0.0.1:8765", "[::1]:8765"):
        with TestClient(server.app, client=("127.0.0.1", 50000), base_url=f"http://{host}") as c:
            assert c.get("/api/status").status_code == 200, host


def test_token_only_in_app_page(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    with _client() as c:
        page = c.get("/")
        assert server.API_TOKEN in page.text and page.headers["cache-control"] == "no-store"
        assert server.API_TOKEN not in c.get("/api/status").text
        assert server.API_TOKEN not in c.get("/static/index.html").text


def test_lan_ip_host_allowed_only_when_lan_enabled(db, monkeypatch):
    monkeypatch.setattr(server, "_inbox_loop", lambda: None)
    monkeypatch.setattr(server.lan, "lan_addresses", lambda: ["192.168.1.50"])
    server._lan_ips["at"] = 0
    with TestClient(server.app, client=("192.168.1.60", 50000), base_url="http://192.168.1.50:8765") as c:
        server.save_settings({"lan_enabled": False, "lan_pin": ""})
        assert c.get("/m").status_code == 403
        server.save_settings({"lan_enabled": True, "lan_pin": "123456"})
        server._lan_ips["at"] = 0
        assert c.get("/m").status_code == 200
        # گوشی فقط صفحه آپلود را دارد و رمز لازم است؛ کلید محرمانه برنامه را ندارد و لازم هم ندارد
        assert c.post("/api/m/check", headers={"X-PIN": "000000"}).status_code == 401
        assert c.post("/api/files/retry-failed").status_code == 403
    server.save_settings({"lan_enabled": False, "lan_pin": ""})
