"""Sao lưu dữ liệu tool cho máy khác kéo về (Mac mini Niche System).

  GET /api/sao-luu/dau        dấu nội dung (sha256) + số file + dung lượng — rẻ, gọi trước
  GET /api/sao-luu.tar.gz     toàn bộ DATA_DIR nén lại, kèm header X-Sao-Luu-Dau

Bỏ: img/ (ảnh cache, tải lại được), capture/ (request H10 đã ghi — dữ liệu tài khoản, chỉ đi
đường /api/agent/captures có AGENT_TOKEN), file *.tmp đang ghi dở. Phần còn lại đúng là thứ
/api/lists và /api/products đang trả ra, nên đi cùng quyền kw.view.
Giải nén bản sao vào một DATA_DIR trống là tool chạy lại y nguyên.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import os
import tarfile
import tempfile
import threading
from pathlib import Path

BO_QUA_THU_MUC = {"img", "capture"}
_cache: dict[str, tuple[int, int, str]] = {}   # đường tương đối → (size, mtime_ns, sha256)
_khoa = threading.Lock()


def _cac_file(goc: Path) -> list[Path]:
    out = []
    for p in goc.rglob("*"):
        if not p.is_file() or p.name.endswith(".tmp") or p.name.startswith("."):
            continue
        rel = p.relative_to(goc)
        if rel.parts[0] in BO_QUA_THU_MUC:
            continue
        out.append(p)
    return sorted(out, key=lambda p: p.relative_to(goc).as_posix())


def _sha(p: Path, rel: str) -> str:
    st = p.stat()
    c = _cache.get(rel)
    if c and c[0] == st.st_size and c[1] == st.st_mtime_ns:
        return c[2]
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    _cache[rel] = (st.st_size, st.st_mtime_ns, h)
    return h


def dau(goc: Path) -> dict:
    """Dấu nội dung toàn kho: đổi bất kỳ file nào thì dấu đổi; không đổi thì máy kéo khỏi tải."""
    with _khoa:
        tong = hashlib.sha256()
        so = byte = 0
        so_bo = 0
        for p in _cac_file(goc):
            rel = p.relative_to(goc).as_posix()
            try:
                h = _sha(p, rel)
                byte += p.stat().st_size
            except FileNotFoundError:      # vừa bị thay giữa chừng: bỏ qua, lượt sau kéo lại
                continue
            tong.update(f"{rel}\0{h}\n".encode())
            so += 1
            if rel.startswith("lists/") and rel.endswith("/meta.json"):
                so_bo += 1
        return {"ok": True, "dau": tong.hexdigest(), "so_file": so, "so_bo": so_bo, "byte": byte,
                "bo_qua": sorted(BO_QUA_THU_MUC)}


_nen_khoa = threading.Lock()                   # mỗi lúc chỉ nén một bản (trước đây mỗi lượt kéo nén riêng trong RAM)
_nen_cu: dict = {}                             # bản nén gần nhất: {"file": Path, "dau": str, "so_file": int}


def nen(goc: Path, thu_muc_tam: Path | None = None) -> tuple[Path, dict]:
    """tar.gz ghi ra FILE TẠM trên ổ (không giữ trong RAM) + dấu đúng những file đã đóng gói.
    Dữ liệu chưa đổi so với lần nén trước thì trả lại đúng file đó, khỏi nén lại.
    Ngày 24/11/2026 bản nén trong RAM (mỗi lượt kéo một bản, kéo lại khi chậm) góp phần đẩy RAM lên 8 GB."""
    thu_muc_tam = Path(thu_muc_tam or tempfile.gettempdir())
    with _nen_khoa:
        hien = dau(goc)["dau"]
        cu = _nen_cu.get("file")
        if cu and _nen_cu.get("dau") == hien and cu.is_file():
            return cu, {"dau": _nen_cu["dau"], "so_file": _nen_cu["so_file"]}
        fd, ten = tempfile.mkstemp(prefix="kw-sao-luu-", suffix=".tar.gz", dir=thu_muc_tam)
        moi = Path(ten)
        tong = hashlib.sha256()
        so = 0
        try:
            with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz, \
                    tarfile.open(fileobj=gz, mode="w") as tar:
                for p in _cac_file(goc):
                    rel = p.relative_to(goc).as_posix()
                    try:
                        data = p.read_bytes()
                        st = p.stat()
                    except FileNotFoundError:
                        continue
                    ti = tarfile.TarInfo(rel)
                    ti.size = len(data)
                    ti.mtime = int(st.st_mtime)
                    ti.mode = 0o644
                    tar.addfile(ti, io.BytesIO(data))
                    tong.update(f"{rel}\0{hashlib.sha256(data).hexdigest()}\n".encode())
                    so += 1
                    del data
        except BaseException:
            moi.unlink(missing_ok=True)
            raise
        if cu and cu != moi:
            cu.unlink(missing_ok=True)     # người đang tải bản cũ vẫn đọc tiếp được (file đã mở trên Linux)
        _nen_cu.update(file=moi, dau=tong.hexdigest(), so_file=so)
        return moi, {"dau": _nen_cu["dau"], "so_file": so}
