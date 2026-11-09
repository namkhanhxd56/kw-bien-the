"""
Lưu trữ bằng file JSON trong DATA_DIR (đủ cho bản tạm; khi ghép app khác thay bằng DB).

  data/lists/<slug>/meta.json     thông tin bộ keyword (mã, tên, ASIN, bộ lọc)
  data/lists/<slug>/<ASIN>.json   dòng keyword của từng ASIN + kỳ đã dùng + nguồn
  data/jobs.json                  hàng đợi job lấy Cerebro cho extension
  data/analysis/<mã>.json         ghi chú phân tích ảnh sản phẩm
  data/usage.json                 số lượt Cerebro đã dùng theo ngày
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

KY_CHINH = "2025-12"      # kỳ Cerebro chuẩn: tháng 12/2025
KY_HIEN_TAI = "current"   # dự phòng khi kỳ chuẩn không có dữ liệu

khoa = threading.RLock()


class Store:
    def __init__(self, root: Path):
        self.root = root
        (root / "lists").mkdir(parents=True, exist_ok=True)
        (root / "analysis").mkdir(parents=True, exist_ok=True)
        self.agent_seen = 0.0
        self.agent_info = {}

    # ------------------------------------------------------------ tiện ích file
    def _read(self, p: Path, default):
        try:
            return json.loads(p.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _write(self, p: Path, obj) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(p)

    # ------------------------------------------------------------ tên bộ keyword
    @staticmethod
    def slugify(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    @classmethod
    def ten_bo(cls, ma: str, niche: str, product: str) -> tuple[str, str]:
        """Tên bộ = {Mã nội bộ}-{niche + product}. Trả (tên hiển thị, slug cho URL)."""
        niche, product = (niche or "").strip(), (product or "").strip()
        ten = niche
        if product and not cls.slugify(niche).endswith(cls.slugify(product)):
            ten = f"{niche} {product}".strip()
        ma_s = re.sub(r"[^A-Za-z0-9]+", "", ma or "")
        return f"{ma} - {ten}", f"{ma_s}-{cls.slugify(ten)}".strip("-")

    # ------------------------------------------------------------ bộ keyword
    def list_dir(self, slug: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", slug or ""):
            raise ValueError("Tên bộ keyword không hợp lệ")
        return self.root / "lists" / slug

    def get_list(self, slug: str) -> dict | None:
        return self._read(self.list_dir(slug) / "meta.json", None)

    def list_by_ma(self, ma: str) -> dict | None:
        with khoa:
            best = None
            for f in (self.root / "lists").glob("*/meta.json"):
                m = self._read(f, None)
                if m and m.get("ma") == ma and (best is None or m["updated_at"] > best["updated_at"]):
                    best = m
            return best

    def save_list(self, meta: dict) -> dict:
        with khoa:
            meta["updated_at"] = time.time()
            self._write(self.list_dir(meta["slug"]) / "meta.json", meta)
            return meta

    def upsert_list(self, *, ma, record_id, niche, product, asins, nguoi="") -> dict:
        ten, slug = self.ten_bo(ma, niche, product)
        if not slug or slug == ma:
            raise ValueError("Cần nhập niche hoặc product để đặt tên bộ keyword")
        with khoa:
            meta = self.get_list(slug) or {
                "slug": slug, "ma": ma, "created_at": time.time(), "created_by": nguoi,
            }
            meta.update(ten=ten, record_id=record_id, niche=niche, product=product, asins=asins)
            return self.save_list(meta)

    def asin_data(self, slug: str, asin: str) -> dict | None:
        return self._read(self.list_dir(slug) / f"{asin}.json", None)

    def save_asin_data(self, slug: str, asin: str, *, rows, period_used, nguon, canh_bao=None):
        with khoa:
            self._write(self.list_dir(slug) / f"{asin}.json", {
                "asin": asin, "rows": rows, "period_used": period_used, "nguon": nguon,
                "canh_bao": canh_bao or [], "fetched_at": time.time(),
            })

    def all_asin_data(self, slug: str, asins: list[str]) -> dict[str, dict]:
        out = {}
        for a in asins:
            d = self.asin_data(slug, a)
            if d is not None:
                out[a] = d
        return out

    # ------------------------------------------------------------ hàng đợi job
    def _jobs(self) -> list[dict]:
        return self._read(self.root / "jobs.json", [])

    def _save_jobs(self, jobs: list[dict]) -> None:
        cutoff = time.time() - 30 * 86400
        jobs = [j for j in jobs if j["created_at"] > cutoff or j["status"] in ("queued", "running")]
        self._write(self.root / "jobs.json", jobs)

    def jobs_for(self, slug: str) -> list[dict]:
        return [j for j in self._jobs() if j["slug"] == slug]

    def enqueue(self, slug: str, asin: str, period: str = KY_CHINH, attempt: int = 1) -> dict:
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["slug"] == slug and j["asin"] == asin and j["status"] in ("queued", "running"):
                    return j
            j = {"id": uuid.uuid4().hex[:12], "slug": slug, "asin": asin, "period": period,
                 "attempt": attempt, "status": "queued", "created_at": time.time(),
                 "started_at": None, "finished_at": None, "error": "", "rows": None}
            jobs.append(j)
            self._save_jobs(jobs)
            return j

    def cancel(self, slug: str, asin: str) -> None:
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["slug"] == slug and j["asin"] == asin and j["status"] == "queued":
                    j.update(status="cancelled", finished_at=time.time())
            self._save_jobs(jobs)

    def next_job(self, stale_sec: int = 600) -> dict | None:
        """Job cũ nhất đang chờ. Job 'running' quá stale_sec coi như extension đã rớt → trả lại hàng."""
        with khoa:
            jobs = self._jobs()
            now = time.time()
            for j in jobs:
                if j["status"] == "running" and now - (j["started_at"] or now) > stale_sec:
                    j.update(status="queued", started_at=None, error="Extension không trả kết quả, xếp lại")
            q = [j for j in jobs if j["status"] == "queued"]
            if not q:
                self._save_jobs(jobs)
                return None
            j = min(q, key=lambda x: x["created_at"])
            j.update(status="running", started_at=now)
            self._save_jobs(jobs)
            return dict(j)

    def update_job(self, job_id: str, **kw) -> dict | None:
        with khoa:
            jobs = self._jobs()
            for j in jobs:
                if j["id"] == job_id:
                    j.update(kw)
                    self._save_jobs(jobs)
                    return dict(j)
            return None

    def queue_size(self) -> int:
        return sum(1 for j in self._jobs() if j["status"] in ("queued", "running"))

    # ------------------------------------------------------------ lượt dùng / ngày
    def usage_today(self) -> int:
        return self._read(self.root / "usage.json", {}).get(datetime.now().strftime("%Y-%m-%d"), 0)

    def add_usage(self, n: int = 1) -> None:
        with khoa:
            u = self._read(self.root / "usage.json", {})
            d = datetime.now().strftime("%Y-%m-%d")
            u[d] = u.get(d, 0) + n
            self._write(self.root / "usage.json", dict(sorted(u.items())[-60:]))

    # ------------------------------------------------------------ phân tích ảnh
    def get_analysis(self, ma: str) -> dict:
        return self._read(self.root / "analysis" / f"{self.slugify(ma) or 'x'}.json", {})

    def save_analysis(self, ma: str, data: dict) -> dict:
        data = {**data, "ma": ma, "updated_at": time.time()}
        with khoa:
            self._write(self.root / "analysis" / f"{self.slugify(ma) or 'x'}.json", data)
        return data
