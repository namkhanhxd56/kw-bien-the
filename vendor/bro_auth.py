"""
bro_auth — client Python cho dịch vụ đăng nhập/phân quyền dùng chung.

CHỈ DÙNG THƯ VIỆN CHUẨN. Không cần `pip install` gì cả — cố ý như vậy để
cắm thẳng vào Amazon-Listing-Tool (server.py hiện đang chạy bằng
http.server, không có dependency nào).

Cách dùng nhanh trong một BaseHTTPRequestHandler:

    from bro_auth import BroAuth

    auth = BroAuth(
        base_url=os.environ["BRO_AUTH_URL"],
        api_key=os.environ["BRO_AUTH_API_KEY"],
    )

    # Gọi 1 lần lúc khởi động: khai báo vai trò + màn hình của tool
    auth.register_app(
        roles=["ADMIN", "EDITOR", "VIEWER"],
        capabilities=[
            {"id": "listing.view",    "label": "Xem listing", "group": "Listing",
             "defaults": {"ADMIN": "edit", "EDITOR": "edit", "VIEWER": "view"}},
            {"id": "listing.publish", "label": "Đẩy lên Amazon", "group": "Listing",
             "defaults": {"ADMIN": "edit", "EDITOR": "none", "VIEWER": "none"}},
        ],
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Trang login + xử lý đăng xuất: để thư viện lo
            if auth.handle_auth_routes(self):
                return

            session = auth.require(self, "listing.view")   # chặn nếu thiếu quyền
            if session is None:
                return          # thư viện đã trả lời 302/403 rồi

            # ... code cũ của bạn, giờ đã biết ai đang đăng nhập:
            # session["user"]["email"], session["role"], session["capabilities"]

        def do_POST(self):
            if self.path == "/api/publish":
                session = auth.require(self, "listing.publish", "edit")
                if session is None:
                    return
                ...
"""

from __future__ import annotations

import http.cookies
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

COOKIE_NAME = "bro_session"
_LEVEL_RANK = {"none": 0, "view": 1, "edit": 2}


class BroAuthError(Exception):
    pass


class BroAuth:
    """
    Bọc REST API của bro-auth + quản lý cookie phiên cho tool Python.

    verify_ttl: số giây cache kết quả kiểm token, để không gọi mạng ở
    mỗi request. Mặc định 60 giây — đủ nhanh để admin khoá tài khoản
    thấy hiệu lực gần như tức thì, mà vẫn không tạo tải.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        login_path: str = "/login",
        logout_path: str = "/logout",
        app_name: str = "Tool nội bộ",
        verify_ttl: int = 60,
        timeout: int = 10,
        secure_cookie: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.login_path = login_path
        self.logout_path = logout_path
        self.app_name = app_name
        self.verify_ttl = verify_ttl
        self.timeout = timeout
        self.secure_cookie = secure_cookie
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    # ── Gọi API ──────────────────────────────────────────────────────────
    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/v1{path}",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "X-Api-Key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}"}
        except Exception as e:  # mạng chết, DNS hỏng…
            return {"ok": False, "error": f"không gọi được auth service: {e}"}

    def register_app(self, roles: List[str], capabilities: List[dict]) -> dict:
        """Khai báo vai trò + danh sách quyền của tool. Gọi lúc khởi động."""
        return self._post("/apps/register", {"roles": roles, "capabilities": capabilities})

    def login(self, email: str, password: str) -> dict:
        return self._post("/auth/login", {"email": email, "password": password})

    def verify(self, token: str) -> dict:
        return self._post("/auth/verify", {"token": token})

    def create_user(self, email: str, role: str, name: str = "", password: str = "") -> dict:
        payload: Dict[str, Any] = {"email": email, "role": role}
        if name:
            payload["name"] = name
        if password:
            payload["password"] = password
        return self._post("/users", payload)

    # ── Phiên (cookie) ───────────────────────────────────────────────────
    def _read_cookie(self, handler) -> Optional[str]:
        raw = handler.headers.get("Cookie")
        if not raw:
            return None
        try:
            c = http.cookies.SimpleCookie()
            c.load(raw)
            m = c.get(COOKIE_NAME)
            return m.value if m else None
        except Exception:
            return None

    def _set_cookie(self, handler, token: str, max_age: int) -> None:
        parts = [
            f"{COOKIE_NAME}={token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            f"Max-Age={max_age}",
        ]
        if self.secure_cookie:
            parts.append("Secure")
        handler.send_header("Set-Cookie", "; ".join(parts))

    def _clear_cookie(self, handler) -> None:
        handler.send_header("Set-Cookie", f"{COOKIE_NAME}=; Path=/; HttpOnly; Max-Age=0")

    def session(self, handler) -> Optional[dict]:
        """
        Trả về {"user":…, "role":…, "capabilities":{…}} nếu đang đăng nhập
        hợp lệ, ngược lại None. Có cache theo token.
        """
        token = self._read_cookie(handler)
        if not token:
            return None

        now = time.time()
        with self._lock:
            hit = self._cache.get(token)
            if hit and hit[0] > now:
                return hit[1]

        res = self.verify(token)
        if not res.get("ok"):
            with self._lock:
                self._cache.pop(token, None)
            return None

        data = {
            "user": res["user"],
            "role": res["role"],
            "capabilities": res.get("capabilities", {}),
            "token": token,
        }
        with self._lock:
            self._cache[token] = (now + self.verify_ttl, data)
            # Dọn cache cũ cho khỏi phình.
            if len(self._cache) > 500:
                for k in [k for k, v in self._cache.items() if v[0] < now]:
                    self._cache.pop(k, None)
        return data

    # ── Kiểm quyền ───────────────────────────────────────────────────────
    @staticmethod
    def allows(session: Optional[dict], capability_id: str, required: str = "view") -> bool:
        """Kiểm quyền thuần, không đụng HTTP — tiện để ẩn/hiện nút trên giao diện."""
        if not session:
            return False
        actual = session.get("capabilities", {}).get(capability_id, "none")
        return _LEVEL_RANK.get(actual, 0) >= _LEVEL_RANK.get(required, 1)

    def require(self, handler, capability_id: str, required: str = "view") -> Optional[dict]:
        """
        Chặn request nếu chưa đăng nhập hoặc thiếu quyền.

        Trả về session nếu qua; trả về None SAU KHI đã tự gửi trả lời
        (302 về trang login, hoặc 403). Nơi gọi chỉ cần `return`.
        """
        sess = self.session(handler)
        if sess is None:
            self._redirect_to_login(handler)
            return None
        if not self.allows(sess, capability_id, required):
            self._deny(handler, capability_id, required, sess["role"])
            return None
        return sess

    def _redirect_to_login(self, handler) -> None:
        nxt = urllib.parse.quote(handler.path, safe="")
        handler.send_response(302)
        handler.send_header("Location", f"{self.login_path}?next={nxt}")
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    def _deny(self, handler, capability_id: str, required: str, role: str) -> None:
        msg = (
            f"Vai trò {role} của bạn không có quyền '{required}' với "
            f"'{capability_id}'. Nhờ quản trị viên cấp thêm."
        )
        body = json.dumps({"ok": False, "error": msg}, ensure_ascii=False).encode("utf-8")
        handler.send_response(403)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    # ── Trang đăng nhập / đăng xuất ──────────────────────────────────────
    def handle_auth_routes(self, handler) -> bool:
        """
        Xử lý sẵn GET/POST cho /login và /logout.
        Trả về True nghĩa là đã trả lời xong, nơi gọi phải `return` ngay.
        """
        path = urllib.parse.urlparse(handler.path).path

        if path == self.logout_path:
            handler.send_response(302)
            self._clear_cookie(handler)
            handler.send_header("Location", self.login_path)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return True

        if path != self.login_path:
            return False

        if handler.command == "GET":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
            self._send_login_page(handler, next_url=(qs.get("next") or ["/"])[0])
            return True

        if handler.command == "POST":
            length = int(handler.headers.get("Content-Length") or 0)
            form = urllib.parse.parse_qs(handler.rfile.read(length).decode("utf-8"))
            email = (form.get("email") or [""])[0].strip()
            password = (form.get("password") or [""])[0]
            next_url = (form.get("next") or ["/"])[0] or "/"
            # Chỉ cho redirect nội bộ — chặn open-redirect.
            if not next_url.startswith("/"):
                next_url = "/"

            res = self.login(email, password)
            if not res.get("ok"):
                self._send_login_page(handler, next_url, error=res.get("error", "Đăng nhập thất bại"))
                return True

            handler.send_response(302)
            self._set_cookie(handler, res["token"], int(res.get("expiresIn", 43200)))
            handler.send_header("Location", next_url)
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return True

        return False

    def _send_login_page(self, handler, next_url: str = "/", error: str = "") -> None:
        safe_next = next_url if next_url.startswith("/") else "/"
        err_html = (
            f'<p style="color:#dc2626;font-size:13px;margin-top:12px">{_esc(error)}</p>'
            if error
            else ""
        )
        html = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đăng nhập — {_esc(self.app_name)}</title>
<style>
:root{{--bg:#fafafa;--fg:#18181b;--mut:#71717a;--brd:#e4e4e7;--card:#fff}}
@media(prefers-color-scheme:dark){{:root{{--bg:#09090b;--fg:#fafafa;--mut:#a1a1aa;--brd:#27272a;--card:#111113}}}}
body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}}
.box{{width:100%;max-width:340px;padding:20px}}
.card{{background:var(--card);border:1px solid var(--brd);border-radius:10px;padding:22px}}
h1{{font-size:20px;margin:0 0 4px;text-align:center}}
p.sub{{color:var(--mut);font-size:13px;text-align:center;margin:0 0 18px}}
label{{display:block;font-size:13px;font-weight:600;margin:12px 0 5px}}
input{{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid var(--brd);
border-radius:7px;background:var(--card);color:var(--fg);font-size:14px}}
button{{width:100%;margin-top:18px;padding:9px;border:0;border-radius:7px;
background:var(--fg);color:var(--bg);font-size:14px;font-weight:600;cursor:pointer}}
</style></head><body><div class="box">
<h1>{_esc(self.app_name)}</h1>
<p class="sub">Đăng nhập bằng tài khoản nội bộ</p>
<div class="card"><form method="post" action="{_esc(self.login_path)}">
<input type="hidden" name="next" value="{_esc(safe_next)}">
<label for="email">Email</label>
<input id="email" name="email" type="email" autocomplete="username" required autofocus>
<label for="password">Mật khẩu</label>
<input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Đăng nhập</button>
{err_html}
</form></div></div></body></html>"""
        body = html.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
