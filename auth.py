"""Phân tầng quyền cho KW Biến Thể, dựa trên bro-auth.

Gác một chỗ: bảng ROUTES map (method, mẫu path) → (capability, mức). `guard()` được gọi
đúng một lần ở đầu mỗi request. Path không khớp dòng nào vẫn đòi đăng nhập ở mức view của
kw.view: thêm endpoint mà quên khai quyền thì nó đóng, không hở.

Đường /api/agent/* KHÔNG đi qua phiên đăng nhập: extension không có cookie bro-auth, nó gửi
X-Agent-Token và server tự kiểm (server.py `_agent_ok`). Chạy trên mạng mà thiếu AGENT_TOKEN
thì server chỉ nhận agent từ loopback, tức là chặn hết.

Không có auth (chưa cấu hình BRO_AUTH_URL) chỉ được phép khi bind loopback, hoặc khi đặt rõ
ALLOW_NO_AUTH=1 (giai đoạn tạm, chưa gắn đăng nhập). Bind ra ngoài mà thiếu cả hai thì thoát luôn,
để không đẩy một tool không khoá lên mạng chỉ vì quên biến.
"""
import os
import re
import sys
from pathlib import Path

# Railway chỉ deploy repo này nên client nằm trong vendor/; cạnh nhà thì lấy bản gốc.
_HERE = Path(__file__).parent
for _c in (_HERE.parent / "bro-auth" / "clients" / "python", _HERE / "vendor"):
    if (_c / "bro_auth.py").is_file():
        sys.path.insert(0, str(_c))
        break

try:
    from bro_auth import BroAuth
except ImportError:
    BroAuth = None


def _normalize_url(raw: str) -> str:
    """Railway hiện domain không kèm scheme; thiếu https:// thì urllib báo "unknown url type"."""
    u = (raw or "").strip().rstrip("/")
    if not u or "://" in u:
        return u
    host = u.split("/")[0].split(":")[0]
    return ("http" if host in ("localhost", "127.0.0.1", "::1") else "https") + "://" + u


BASE_URL = _normalize_url(os.environ.get("BRO_AUTH_URL"))
API_KEY = os.environ.get("BRO_AUTH_API_KEY") or ""
LOOPBACK = ("127.0.0.1", "localhost", "::1")

ROLES = ["ADMIN", "EDITOR", "VIEWER"]

# (id, label, group, defaults): đúng hợp đồng validateRegistry của bro-auth
# (label chứ không phải name; group bắt buộc).
CAPS = [
    ("kw.view", "Xem sản phẩm và bộ keyword", "KW Biến Thể",
     {"ADMIN": "edit", "EDITOR": "edit", "VIEWER": "view"}),
    # Tạo bộ, xếp job Cerebro (tốn lượt H10 dùng chung), tải file, ghi phân tích ảnh
    ("kw.edit", "Tạo bộ keyword và lấy Cerebro", "KW Biến Thể",
     {"ADMIN": "edit", "EDITOR": "edit", "VIEWER": "none"}),
    # Ghi link ngược vào bảng Lark của cả nhóm
    ("kw.lark", "Ghi link bộ keyword vào Lark", "KW Biến Thể",
     {"ADMIN": "edit", "EDITOR": "edit", "VIEWER": "none"}),
]

# (method, mẫu path đầy đủ) → (capability, mức). Đi từ trên xuống, dòng khớp đầu tiên thắng.
ROUTES = [
    ("GET", r"/", "kw.view", "view"),
    ("GET", r"/kw-list/.+", "kw.view", "view"),
    ("GET", r"/static/.+", "kw.view", "view"),
    ("GET", r"/hang-doi", "kw.view", "view"),
    ("GET", r"/extension\.zip", "kw.view", "view"),
    ("GET", r"/api/hang-doi", "kw.view", "view"),
    ("GET", r"/api/status", "kw.view", "view"),
    ("GET", r"/api/products", "kw.view", "view"),
    ("GET", r"/api/products/[^/]+/image", "kw.view", "view"),
    ("GET", r"/api/analysis/[^/]+", "kw.view", "view"),
    ("GET", r"/api/lists/[^/]+", "kw.view", "view"),
    ("GET", r"/api/lists/[^/]+/export\.csv", "kw.view", "view"),
    ("GET", r"/api/lists/[^/]+/final\.(xlsx|md)", "kw.view", "view"),
    ("GET", r"/huong-dan-agent(\.md)?", "kw.view", "view"),
    ("GET", r"/api/lists/[^/]+/bien-the", "kw.view", "view"),
    ("GET", r"/api/bo-nho", "kw.view", "view"),
    ("GET", r"/api/sao-luu/dau", "kw.view", "view"),
    ("GET", r"/api/sao-luu\.tar\.gz", "kw.view", "view"),
    ("POST", r"/api/analysis/[^/]+", "kw.edit", "edit"),
    ("POST", r"/api/lists", "kw.edit", "edit"),
    ("POST", r"/api/bulk/(luu|lay)", "kw.edit", "edit"),
    ("POST", r"/api/tool/dung", "kw.edit", "edit"),
    ("POST", r"/api/hang-doi/bo", "kw.edit", "edit"),
    ("POST", r"/api/hang-doi/uu-tien", "kw.edit", "edit"),
    ("POST", r"/api/dung-lai", "kw.edit", "edit"),
    ("POST", r"/api/lists/[^/]+/(fetch|cancel|upload)", "kw.edit", "edit"),
    ("POST", r"/api/lists/[^/]+/lark-link", "kw.lark", "edit"),
    ("POST", r"/api/lists/[^/]+/bien-the/nhan", "kw.edit", "edit"),
    ("POST", r"/api/lists/[^/]+/xoa", "kw.edit", "edit"),
]
_ROUTES = [(m, re.compile(p), c, n) for m, p, c, n in ROUTES]
MAC_DINH = ("kw.view", "view")

# Không cần phiên: health check, file trang login tự dùng, và đường của extension (tự kiểm token)
PUBLIC = {"/healthz", "/favicon.ico", "/static/authui.js"}
AGENT_PREFIX = "/api/agent/"

_auth = None


def configured() -> bool:
    return bool(BASE_URL and API_KEY and BroAuth)


def init(bind_host: str) -> None:
    global _auth
    if not configured():
        if bind_host not in LOOPBACK:
            # Chạy hở ra mạng phải là quyết định có chủ ý (ALLOW_NO_AUTH=1), không phải do quên biến
            if os.environ.get("ALLOW_NO_AUTH") == "1":
                print(f"  auth    : TẮT dù đang bind {bind_host} (ALLOW_NO_AUTH=1) — ai có link cũng dùng được")
                return
            sys.exit(
                f"\n  DỪNG: đang bind {bind_host} (ra ngoài) mà chưa cấu hình bro-auth.\n"
                f"  Đặt BRO_AUTH_URL + BRO_AUTH_API_KEY, hoặc ALLOW_NO_AUTH=1 để chạy không đăng nhập.\n"
            )
        if BASE_URL and not API_KEY:
            print("  auth    : có BRO_AUTH_URL nhưng THIẾU BRO_AUTH_API_KEY → tắt auth")
        return
    _auth = BroAuth(BASE_URL, API_KEY, app_name="KW Biến Thể",
                    secure_cookie=bind_host not in LOOPBACK)
    # register_app chỉ gieo quyền mặc định. Hỏng thì quyền rỗng = chặn hết (fail-closed),
    # không để nó làm sập container.
    try:
        res = _auth.register_app(ROLES, [{"id": i, "label": l, "group": g, "defaults": d}
                                         for i, l, g, d in CAPS])
        if not res.get("ok"):
            print(f"  auth    : register_app lỗi — {res.get('error')}; vẫn chạy, quyền rỗng tới khi đăng ký được")
    except Exception as e:  # noqa: BLE001
        print(f"  auth    : không gọi được {BASE_URL} — {e}; vẫn chạy, /login báo lỗi tới khi auth lên")


def enabled() -> bool:
    return _auth is not None


def rule(path: str, method: str) -> tuple[str, str]:
    for m, rx, cap, need in _ROUTES:
        if m == method and rx.fullmatch(path):
            return cap, need
    return MAC_DINH


def handle_routes(handler) -> bool:
    """True nghĩa là /login hoặc /logout đã trả lời xong."""
    return _auth.handle_auth_routes(handler) if _auth else False


def guard(handler, path: str, method: str):
    """(True, session) nếu được đi tiếp; (False, None) khi đã tự trả 302/403."""
    if not _auth or path in PUBLIC or path.startswith(AGENT_PREFIX):
        return True, None
    cap, need = rule(path, method)
    sess = _auth.require(handler, cap, need)
    return (sess is not None), sess


def me(handler) -> dict:
    if not _auth:
        return {"auth": False, "caps": {i: "edit" for i, _, _, _ in CAPS}}
    s = _auth.session(handler)
    if not s:
        return {"auth": True, "user": None, "caps": {}}
    return {"auth": True, "user": s["user"], "role": s["role"],
            "caps": {i: s.get("capabilities", {}).get(i, "none") for i, _, _, _ in CAPS}}
