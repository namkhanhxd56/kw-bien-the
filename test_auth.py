#!/usr/bin/env python3
"""Kiểm phân tầng quyền. Chạy: python3 test_auth.py (không cần bro-auth, không gọi mạng).

Hai bài quan trọng nhất:
1. Mọi đường trong server.py đều khớp một dòng khai báo trong auth.ROUTES (không rơi vào mặc định).
2. Payload register_app đúng hợp đồng validateRegistry của bro-auth (label, group…).
"""
import os
import re

os.environ.pop("BRO_AUTH_URL", None)
os.environ.pop("BRO_AUTH_API_KEY", None)
import auth  # noqa: E402

ok = fail = 0


def t(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ok   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}\n       got={got!r}\n       want={want!r}")


print("── mọi đường trong server.py đều được khai quyền ──")
src = open("server.py", encoding="utf-8").read()
# Tách theo nhánh GET / POST của _route để biết method của từng đường
nhanh_get, nhanh_post = src.split('            if method == "GET":\n                if path == "/":', 1)[1].split("            else:\n", 1)
nhanh_post = nhanh_post.split("            return self._err(404", 1)[0]
nhanh_get = 'if path == "/":' + nhanh_get


def mau(chuoi):
    """Biến các path trong một nhánh thành path mẫu cụ thể để thử."""
    out = set(re.findall(r'path == "(/[^"]*)"', chuoi))
    out |= {"/kw-list/abc"} if 'path.startswith("/kw-list/")' in chuoi else set()
    out |= {"/static/style.css"} if 'path.startswith("/static/")' in chuoi else set()
    for rx in re.findall(r're\.fullmatch\(r"([^"]+)"', chuoi):
        p = rx.replace("([^/]+)", "X").replace("([a-f0-9]+)", "abc123").replace(r"\.", ".")
        p = re.sub(r"\(([a-z\-|]+)\)", lambda m: m.group(1).split("|")[0], p)
        out.add(p)
    return out


for method, nhanh in (("GET", nhanh_get), ("POST", nhanh_post)):
    paths = mau(nhanh)
    agent = {p for p in paths if p.startswith(auth.AGENT_PREFIX)}
    thuong = paths - agent
    chua_khai = sorted(p for p in thuong
                       if not any(m == method and rx.fullmatch(p) for m, rx, _, _ in auth._ROUTES))
    t(f"{method}: {len(thuong)} đường + {len(agent)} đường agent, không sót đường nào", chua_khai, [])

print("\n── payload register_app khớp hợp đồng bro-auth ──")
payload = [{"id": i, "label": l, "group": g, "defaults": d} for i, l, g, d in auth.CAPS]


def validate_registry(roles, caps):
    """Bản Python của validateRegistry (bro-auth/src/lib/capabilities.ts)."""
    if not isinstance(roles, list) or not roles:
        return "roles phải là mảng không rỗng"
    for r in roles:
        if not isinstance(r, str) or not re.fullmatch(r"[A-Z0-9_]{1,32}", r):
            return "role sai"
    seen = set()
    for c in caps:
        if not isinstance(c.get("id"), str) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,64}", c["id"]):
            return f"capability id không hợp lệ: {c.get('id')}"
        if c["id"] in seen:
            return f"capability id trùng: {c['id']}"
        seen.add(c["id"])
        if not isinstance(c.get("label"), str) or not c["label"]:
            return f"capability {c['id']} thiếu label"
        if not isinstance(c.get("group"), str) or not c["group"]:
            return f"capability {c['id']} thiếu group"
        for role, lvl in (c.get("defaults") or {}).items():
            if role not in roles:
                return f"capability {c['id']}: role \"{role}\" không có trong danh sách roles"
            if lvl not in ("none", "view", "edit"):
                return f"capability {c['id']}: mức \"{lvl}\" sai"
    return None


t("payload hiện tại hợp lệ", validate_registry(auth.ROLES, payload), None)
t("  → gửi 'name' thay 'label' bị bắt",
  validate_registry(auth.ROLES, [{"id": "x.y", "name": "L", "group": "G", "defaults": {}}]),
  "capability x.y thiếu label")

print("\n── quyền theo đường ──")
LV = {"none": 0, "view": 1, "edit": 2}
by_id = {i: d for i, _, _, d in auth.CAPS}


def duoc(role, path, method):
    cap, need = auth.rule(path, method)
    return LV[by_id[cap][role]] >= LV[need]


t("đường lạ vẫn đòi đăng nhập (kw.view)", auth.rule("/api/chua-khai", "GET"), ("kw.view", "view"))
t("POST lạ cũng không được mở", auth.rule("/api/chua-khai", "POST"), ("kw.view", "view"))
t("VIEWER xem được bộ keyword", duoc("VIEWER", "/kw-list/BSV627-x", "GET"), True)
t("VIEWER tải được CSV", duoc("VIEWER", "/api/lists/BSV627-x/export.csv", "GET"), True)
t("VIEWER KHÔNG tạo bộ", duoc("VIEWER", "/api/lists", "POST"), False)
t("VIEWER KHÔNG xếp job Cerebro", duoc("VIEWER", "/api/lists/BSV627-x/fetch", "POST"), False)
t("VIEWER KHÔNG tải file tay", duoc("VIEWER", "/api/lists/BSV627-x/upload", "POST"), False)
t("VIEWER KHÔNG ghi phân tích", duoc("VIEWER", "/api/analysis/BSV627", "POST"), False)
t("VIEWER KHÔNG ghi link Lark", duoc("VIEWER", "/api/lists/BSV627-x/lark-link", "POST"), False)
t("EDITOR xếp job được", duoc("EDITOR", "/api/lists/BSV627-x/fetch", "POST"), True)
t("EDITOR ghi link Lark được", duoc("EDITOR", "/api/lists/BSV627-x/lark-link", "POST"), True)
t("lark-link dùng kw.lark", auth.rule("/api/lists/a/lark-link", "POST")[0], "kw.lark")


class FakeH:
    headers = {}


print("\n── chốt an toàn ──")
t("chưa cấu hình", auth.configured(), False)
try:
    auth.init("0.0.0.0")
    t("bind 0.0.0.0 phải thoát", "không thoát", "SystemExit")
except SystemExit as e:
    t("bind 0.0.0.0 mà chưa cấu hình → thoát", "chưa cấu hình bro-auth" in str(e), True)
auth.init("127.0.0.1")
t("bind loopback → chạy, auth tắt", auth.enabled(), False)
t("BRO_AUTH_URL thiếu scheme được thêm https", auth._normalize_url("abc.up.railway.app"), "https://abc.up.railway.app")
t("localhost thì http", auth._normalize_url("localhost:4000"), "http://localhost:4000")

# Auth bật: đường agent không đòi phiên (extension tự gửi token), đường khác thì có
class FakeAuth:
    def require(self, handler, cap, need):
        handler.da_hoi = (cap, need)
        return None


auth._auth = FakeAuth()
h = FakeH()
t("auth bật: /api/agent/next không đòi phiên", auth.guard(h, "/api/agent/next", "GET"), (True, None))
t("auth bật: /healthz công khai", auth.guard(h, "/healthz", "GET"), (True, None))
t("auth bật: trang chính đòi phiên", auth.guard(h, "/", "GET")[0], False)
t("  → hỏi đúng quyền", h.da_hoi, ("kw.view", "view"))
t("auth bật: /static/style.css đòi phiên", auth.guard(h, "/static/style.css", "GET")[0], False)
auth._auth = None

print(f"\n{ok} ok, {fail} hỏng")
raise SystemExit(1 if fail else 0)
