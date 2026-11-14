// Bộ lấy Cerebro theo cách C (Dearmine): thao tác giao diện Cerebro như người (nhập ASIN, tick Exclude
// variations, Get Keywords, chọn kỳ, Export) và đọc JSON chính trang nhận về qua sổ `window.__kwbtNet`
// (capture-main.js ghi). Không tự gọi API của H10, không đọc token; file Export bị chặn không tải về máy.
//
// Hàm `run` được tiêm vào tab Cerebro (world MAIN) nên phải tự đủ: không dùng biến bên ngoài,
// vì Chrome chỉ chuyển mã nguồn của hàm sang trang.
//
// Luồng soi tay ngày 09/11/2026 (data/capture): ô "Enter a keyword…" → validate-asin → label
// [data-testid=excludevariations] → [data-testid=getkeywords] → (đã tìm trước đó) [data-testid=runnewsearch]
// → POST /rta/cerebro/v1/amazon/search/single → trang /view/<id> → ô Time Period "Current" chọn "Dec"
// → [data-testid=applyfilters] → POST …/search/history {periodFrom, periodTo} → …/history/<id>/data
// → [data-testid=exportdata] → [data-testid=xlsx|csv] → GET …/export/ trả JSON toàn bộ dòng.
//
// Hợp đồng trả về:
//   { ok: true, period_used: "2025-12" | "current", rows: [{ keyword, search_volume, search_volume_trend, organic_rank }] }
//   { ok: false, error, login?: true, het_luot?: true, khoa?: true, log: [...], debug: "..." }
// khoa: tài khoản H10 đang chọn chỉ có bản demo Cerebro (ô ASIN xám, bấm vào đòi Upgrade Now).
// khoa / het_luot: nền đổi sang tài khoản khác qua menu avatar → Switch Accounts (hàm dsTaiKhoan) rồi chạy lại.
// rows rỗng ở kỳ 2025-12 là bình thường (sản phẩm mới): server tự xếp lại job với kỳ hiện tại, lượt đó
// không chọn Time Period và không lọc SV/organic rank.

export const ADAPTER = {
  ready: true,
  version: "ui-2026-11-14",
  cerebroUrl: "https://members.helium10.com/cerebro-new",

  // Viết dạng `function` (không viết `async run() {}`): Chrome tiêm hàm bằng mã nguồn của nó, mà mã nguồn
  // của method rút gọn không phải một hàm hợp lệ khi đứng riêng.
  run: async function run(asin, filters) {
    const T0 = Date.now();
    const LOG = [];
    const log = m => LOG.push(`${((Date.now() - T0) / 1000).toFixed(1)}s ${m}`);
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const nghi = (a = 700, b = 1800) => sleep(a + Math.random() * (b - a));   // nghỉ như người
    const thay = el => !!el && el.getClientRects().length > 0;
    const q = (sel, root = document) => [...root.querySelectorAll(sel)].find(thay);
    const theoChu = (re, sel) => [...document.querySelectorAll(sel)]
      .find(el => thay(el) && re.test((el.innerText || "").trim()));
    const so = () => window.__kwbtNet || [];
    const json = x => { try { return JSON.parse(x.body); } catch { return null; } };
    const loiH10 = x => { const d = json(x) || {}; return d.message || d.error?.message || d.errors?.[0]?.message || d.data?.message || `HTTP ${x.status}`; };
    const HET_LUOT = /limit|uses|quota|upgrade|credit|exceed/i;

    async function cho(fn, ms, ten) {
      const het = Date.now() + ms;
      while (Date.now() < het) {
        if (/\/(login|signin)/i.test(location.pathname)) throw Object.assign(new Error("H10 bị đăng xuất giữa chừng"), { login: true });
        const v = fn();
        if (v) return v;
        await sleep(300);
      }
      throw new Error(`Hết giờ chờ: ${ten}`);
    }
    const tim = (re, method, sau) => so().find(x => x.t >= sau && re.test(x.url) && (!method || x.method === method));
    // Bấm như chuột thật: chuột thật đưa focus vào phần tử trước (ô Time Period chỉ mở khung tháng khi focus)
    function bam(el) {
      el.scrollIntoView({ block: "center" });
      const r = el.getBoundingClientRect();
      const o = { bubbles: true, cancelable: true, view: window, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
      el.dispatchEvent(new PointerEvent("pointerdown", o));
      el.dispatchEvent(new MouseEvent("mousedown", o));
      if (typeof el.focus === "function") {
        el.focus();
        // Tab chạy nền không có focus: focus() chỉ đổi activeElement, không phát sự kiện, nên phát tay
        if (!document.hasFocus()) {
          el.dispatchEvent(new FocusEvent("focus"));
          el.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
        }
      }
      el.dispatchEvent(new PointerEvent("pointerup", o));
      el.dispatchEvent(new MouseEvent("mouseup", o));
      el.click();
    }
    function go(el, v) {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      el.focus();
      set.call(el, v);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
    let gan = null;   // phần tử đang thao tác, để chụp giao diện quanh nó khi lỗi
    let sauExport = null;   // các request trang gửi sau cú bấm Export, khi không thấy dữ liệu
    function debug() {
      const hop = [...document.querySelectorAll('[role=dialog], [role=listbox], [class*="odal"], [class*="opover"], [class*="icker"], [class*="ropdown"], [class*="enu"]')]
        .filter(thay).map(e => e.outerHTML.slice(0, 2500));
      let quanh = null;
      if (gan) { let e = gan; for (let i = 0; i < 4 && e.parentElement; i++) e = e.parentElement; quanh = e.outerHTML.slice(0, 4000); }
      return JSON.stringify({ url: location.href, hop: hop.slice(0, 3), quanh, sauExport, focus: document.activeElement?.outerHTML?.slice(0, 300),
                              chu: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 1500) }).slice(0, 9000);
    }
    // Kỳ 12/2025: lọc SV ≥ 50, organic rank 1–100. Kỳ hiện tại (ASIN không có keyword ở 12/2025, tức sản phẩm
    // mới): không lọc gì, giữ mọi dòng Cerebro trả về.
    const doiDong = (rs, ky) => {
      const loc = ky !== "current";
      const svMin = filters.search_volume_min ?? 50, rankMin = filters.organic_rank_min ?? 1, rankMax = filters.organic_rank_max ?? 100;
      const rows = rs.map(r => ({
        keyword: String(r.phrase ?? r.keyword ?? "").trim(),
        search_volume: r.impressionExact30 ?? r.searchVolume ?? null,
        search_volume_trend: r.searchVolumeTrend30 ?? r.searchVolumeTrend ?? null,
        organic_rank: r.organicPosition || r.organicRank || null,
      })).filter(r => r.keyword && (!loc || ((r.search_volume ?? 0) >= svMin && r.organic_rank != null && r.organic_rank >= rankMin && r.organic_rank <= rankMax)));
      log(loc ? `${rs.length} dòng Cerebro → ${rows.length} dòng sau lọc SV ≥ ${svMin}, rank ${rankMin}–${rankMax} (${ky})`
              : `${rs.length} dòng Cerebro, giữ cả ${rows.length} dòng: kỳ hiện tại không lọc SV/rank (sản phẩm mới)`);
      return rows;
    };

    async function exportJson(sau) {
      const nut = await cho(() => q('[data-testid="exportdata"]'), 20000, "nút Export Data");
      await nghi();
      bam(nut);
      const kieu = await cho(() => q('[data-testid="csv"]') || q('[data-testid="xlsx"]'), 10000, "menu Export (CSV/XLSX)");
      window.__kwbtChanTai = true;
      window.__kwbtDaChan = 0;
      await nghi(400, 900);
      bam(kieu);
      log(`bấm Export ${kieu.dataset.testid}`);
      // Phản hồi Export: lúc soi (kỳ cũ) là GET …/export/ trả {data: [ {phrase…} ]}. Nhận mọi phản hồi sau cú bấm
      // có danh sách dòng keyword, không bám một đường dẫn cố định.
      const dongCua = x => {
        if (x.status >= 400) return null;
        const d = json(x);
        const ds = Array.isArray(d?.data) ? d.data : Array.isArray(d?.data?.data) ? d.data.data : Array.isArray(d) ? d : null;
        return ds && (ds.length === 0 ? /export/i.test(x.url) : ds[0] && "phrase" in ds[0]) ? ds : null;
      };
      try {
        let ds = null;
        try {
          const x = await cho(() => so().find(x => x.t >= sau && (dongCua(x) || (/export/i.test(x.url) && x.status >= 400))), 180000, "dữ liệu Export");
          if (x.status >= 400) throw new Error(`Export lỗi: ${loiH10(x)}`);
          ds = dongCua(x);
          log(`Export qua ${x.method} ${x.url.replace(/^https?:\/\/[^/]+/, "").split("?")[0]}`);
          const conLoc = (x.url.match(/(impressionExact30From|organicPositionFrom|timePeriod|wordCount\w*)=/g) || []).join(" ");
          if (conLoc) log(`Export còn bộ lọc của H10: ${conLoc}`);
        } catch (e) {
          sauExport = so().filter(x => x.t >= sau).map(x => `${x.method} ${x.status} ${x.url.split("?")[0]} (${(x.body || "").length}b)`);
          throw e;
        }
        await sleep(2500);   // chờ trang dựng file xong để chặn nốt lượt tải
        log(`Export: ${ds.length} dòng, đã chặn ${window.__kwbtDaChan} file tải về`);
        return ds;
      } finally {
        window.__kwbtChanTai = false;
      }
    }

    try {
      if (!window.__kwbtNet) return { ok: false, error: "Chưa gắn được sổ dữ liệu (cần extension 0.1.2 và tải lại tab Cerebro)", log: LOG };

      // 1. Nhập ASIN. Tài khoản chỉ có bản demo: băng "You are viewing a demo of Cerebro", ô ASIN xám với chữ
      // "… available for Platinum and above", bấm vào đòi Upgrade Now → báo khoa để nền chuyển tài khoản.
      const DEMO = /viewing a demo of Cerebro|available for Platinum and above/i;
      const vao = await cho(() => {
        const i = q('input[placeholder^="Enter a keyword"]');
        const demo = DEMO.test(document.body?.innerText || "");
        if (i && !i.disabled && !demo) return { o: i };
        if (demo || (i && i.disabled)) return { khoa: true };
        return null;
      }, 40000, "ô nhập ASIN");
      if (vao.khoa) return { ok: false, khoa: true, error: "Tài khoản H10 đang chọn chỉ có bản demo Cerebro (ô ASIN bị khoá, đòi Upgrade)", log: LOG };
      const o = vao.o;
      await nghi();
      bam(o);
      go(o, asin);
      log(`nhập ${asin}`);
      let v = await cho(() => tim(/validate-asin/, "GET", T0), 8000, "kiểm tra ASIN").catch(() => null);
      if (!v) {
        o.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
        v = await cho(() => tim(/validate-asin/, "GET", T0), 10000, "kiểm tra ASIN");
      }
      if (v.status >= 400 || !json(v)?.asin) return { ok: false, error: `H10 không nhận ASIN ${asin}: ${loiH10(v)}`, log: LOG };
      log(`ASIN hợp lệ: ${json(v).title?.slice(0, 60) || ""}`);

      // 2. Exclude variations
      await nghi();
      const ex = await cho(() => document.querySelector('input[name="excludeVariations"]'), 10000, "ô Exclude variations");
      if (!ex.checked) bam(q('[data-testid="excludevariations"]') || ex);
      await cho(() => ex.checked, 5000, "tick Exclude variations");
      log("đã tick Exclude variations");

      // 3. Get Keywords (+ hộp thoại "đã tìm sản phẩm này trước đó")
      await nghi();
      const nutTim = await cho(() => { const b = q('[data-testid="getkeywords"]'); return b && !b.disabled && b; }, 15000, "nút Get Keywords");
      const tTim = Date.now();
      bam(nutTim);
      log("bấm Get Keywords");
      const s = await cho(() => {
        const moi = q('[data-testid="runnewsearch"]');
        if (moi) return { hop: moi };
        return tim(/\/rta\/cerebro\/v1\/amazon\/search\/single(\?|$)/, "POST", tTim) && { xong: true };
      }, 60000, "kết quả Get Keywords");
      if (s.hop) {
        // Mở lại lượt tìm cũ (không tốn lượt) khi: lấy kỳ cũ (là một lượt tìm riêng, không cần dữ liệu
        // kỳ hiện tại mới), lượt sau của cùng job, hoặc lượt cũ còn dưới 24 giờ. Ngoài ra thì tìm mới.
        const truoc = json(tim(/previous-searches/, "GET", tTim) || {})?.data;
        const tuoi = truoc?.createdAt ? Date.now() / 1000 - truoc.createdAt : Infinity;
        const dungLai = filters.period !== "current" || (filters.attempt || 1) > 1 || tuoi < 86400;
        await nghi();
        const cu = dungLai && theoChu(/^Load from/i, "button, [role=button]");
        bam(cu || s.hop);
        log(cu ? `đã tìm trước đó (${Math.round(tuoi / 3600)} giờ trước): mở lại lượt cũ, không tốn lượt` : "đã tìm trước đó: bấm Run New Search");
      }
      const tao = await cho(() => tim(/\/rta\/cerebro\/v1\/amazon\/search\/single(\/\d+)?(\?|$)/, null, tTim), 120000, "tạo lượt tìm");
      if (tao.status >= 400) {
        const m = loiH10(tao);
        return { ok: false, error: `Cerebro từ chối tìm: ${m}`, het_luot: HET_LUOT.test(m), log: LOG, debug: debug() };
      }
      const searchId = json(tao)?.data?.id;
      const du = await cho(() => tim(/\/amazon\/search\/single\/\d+\/data/, "GET", tTim), 180000, "bảng keyword kỳ hiện tại");
      if (du.status >= 400) return { ok: false, error: `Không tải được bảng keyword: ${loiH10(du)}`, log: LOG, debug: debug() };
      log(`lượt tìm ${searchId}: ${json(du)?.data?.count ?? "?"} keyword kỳ hiện tại`);

      // 4. Kỳ cũ (12/2025): chọn tháng ở ô Time Period rồi Apply Filters
      if (filters.period !== "current") {
        const [nam, thang] = String(filters.period).split("-").map(Number);
        const TEN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][thang - 1];
        await nghi();
        const oKy = await cho(() => q('input[placeholder="Current"]'), 20000, "ô Time Period");
        gan = oKy;
        const namCua = el => {
          for (let e = el.parentElement, i = 0; e && i < 8; e = e.parentElement, i++) {
            const m = (e.innerText || "").match(/\b(20\d\d)\b/);
            if (m) return Number(m[1]);
          }
          return null;
        };
        const oThang = () => [...document.querySelectorAll("span, div, button, td, li")]
          .filter(el => thay(el) && (el.innerText || "").trim() === TEN && el.children.length <= 1);
        // Mở khung chọn tháng: bấm ô; chưa mở thì bấm khung bao ngoài, rồi thử phím mũi tên xuống
        const cachMo = [() => bam(oKy), () => bam(oKy.parentElement), () => {
          oKy.focus();
          oKy.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
          oKy.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", code: "ArrowDown", keyCode: 40, bubbles: true }));
        }];
        for (const [i, mo] of cachMo.entries()) {
          mo();
          log(`mở ô Time Period (cách ${i + 1})`);
          if (await cho(() => oThang().length, 3000, "").catch(() => 0)) break;
        }
        let chon = null;
        for (let lui = 0; lui < 4 && !chon; lui++) {
          const ds = await cho(() => { const d = oThang(); return d.length && d; }, 5000, `ô tháng ${TEN}`);
          chon = ds.find(el => namCua(el) === nam) || (ds.length <= 2 && ds.every(el => namCua(el) == null) ? ds[0] : null);
          if (!chon) {
            const nutLui = [...document.querySelectorAll("button, [role=button], span, svg")].find(el => thay(el) &&
              (/prev|previous|back|left/i.test(el.getAttribute("aria-label") || String(el.getAttribute("class") || "")) ||
               /^[‹<«❮]$/.test((el.innerText || "").trim())));
            if (!nutLui) break;
            bam(nutLui);
            log("lùi năm trong ô Time Period");
            await nghi(400, 900);
          }
        }
        if (!chon) return { ok: false, error: `Không tìm thấy tháng ${TEN}/${nam} trong ô Time Period`, log: LOG, debug: debug() };
        await nghi(400, 900);
        bam(chon);
        log(`chọn ${TEN} ${nam}`);
        await nghi();
        const ap = await cho(() => q('[data-testid="applyfilters"]'), 10000, "nút Apply Filters");
        const tKy = Date.now();
        bam(ap);
        log("bấm Apply Filters");
        const h = await cho(() => tim(/\/rta\/cerebro\/v1\/amazon\/search\/history(\?|$)/, "POST", tKy), 30000, "tạo tìm kiếm kỳ cũ");
        let gui = {};
        try { gui = JSON.parse(h.req_body || "{}"); } catch { /* bỏ qua */ }
        const tu = `${nam}-${String(thang).padStart(2, "0")}-01`;
        if (gui.periodFrom !== tu) return { ok: false, error: `Chọn sai kỳ: trang gửi ${gui.periodFrom || "?"}, cần ${tu}`, log: LOG, debug: debug() };
        if (h.status >= 400) {
          const m = loiH10(h);
          return { ok: false, error: `Cerebro từ chối tìm kỳ cũ: ${m}`, het_luot: HET_LUOT.test(m), log: LOG, debug: debug() };
        }
        const hid = json(h)?.data?.id;
        log(`tìm kỳ ${gui.periodFrom} → ${gui.periodTo}, mã ${hid}`);
        // Chỉ tin "0 keyword" khi trang đã báo lượt tìm kỳ cũ xong (status 3 = "Search is Done");
        // chưa xong thì chờ lượt tải bảng kế tiếp.
        const demCua = x => json(x)?.data?.count ?? json(x)?.data?.tableData?.length ?? 0;
        const xong = () => json(h)?.data?.status === 3 || so().some(x => x.t >= tKy && new RegExp(`/history/${hid}/status`).test(x.url) && json(x)?.data?.status === 3);
        const hd = await cho(() => so().filter(x => x.t >= tKy && new RegExp(`/search/history/${hid}/data`).test(x.url))
          .find(x => demCua(x) > 0 || xong()), 300000, "bảng keyword kỳ cũ");
        const dem = demCua(hd);
        log(`kỳ ${filters.period}: ${dem} keyword`);
        if (!dem) return { ok: true, period_used: filters.period, rows: [], log: LOG };   // server tự chuyển sang kỳ hiện tại
        const rs = await exportJson(Date.now() - 500);
        return { ok: true, period_used: filters.period, rows: doiDong(rs, filters.period), log: LOG };
      }

      // 5. Kỳ hiện tại (sản phẩm mới): không Time Period, không lọc. Lượt tìm mở lại có thể còn bộ lọc H10 đã lưu
      // (kể cả kỳ vừa chọn ở lượt 12/2025), nên bấm Clear trước khi Export.
      const xoa = theoChu(/^Clear( all| filters)?$/i, "button, [role=button]");
      if (xoa) {
        await nghi();
        const tXoa = Date.now();
        bam(xoa);
        log("bấm Clear (bỏ bộ lọc H10 đã lưu)");
        await cho(() => tim(/\/search\/single\/\d+\/data/, "GET", tXoa), 15000, "bảng sau Clear").catch(() => log("Clear không tải lại bảng"));
      }
      const rs = await exportJson(Date.now() - 500);
      return { ok: true, period_used: "current", rows: doiDong(rs, "current"), log: LOG };
    } catch (e) {
      return { ok: false, error: String(e.message || e), login: !!e.login, log: LOG, debug: debug() };
    }
  },
};

// Kiểm tra trang đang mở có phải trang đăng nhập H10 không. Tiêm vào tab, phải tự đủ.
export function laTrangDangNhap() {
  return /\/(login|signin|sign-in)/i.test(location.pathname) || !!document.querySelector('input[type="password"]');
}

// Danh sách tài khoản H10 của phiên đăng nhập này: menu avatar → Switch Accounts. Tiêm vào tab, phải tự đủ.
// Chỉ đọc rồi bấm Cancel, không chọn: nền tự mở link tài khoản mới (trang chuyển đi thì kết quả tiêm bị mất).
// Giao diện ngày 14/11/2026: [data-testid=header-user-btn] → [data-testid=header-user-switch-accounts-btn]
// → a[data-testid=header-user-account-<id>] href …/dashboard?accountId=<id>, tài khoản đang dùng có radio tick.
export async function dsTaiKhoan() {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const thay = el => !!el && el.getClientRects().length > 0;
  const q = sel => [...document.querySelectorAll(sel)].find(thay);
  async function cho(fn, ms) {
    const het = Date.now() + ms;
    while (Date.now() < het) { const v = fn(); if (v) return v; await sleep(300); }
    return null;
  }
  const SW = '[data-testid="header-user-switch-accounts-btn"]';
  const nut = await cho(() => q('[data-testid="header-user-btn"]'), 20000);
  if (!nut) return { ok: false, error: "Không thấy nút avatar H10 để đổi tài khoản" };
  if (!q(SW)) nut.click();
  const sw = await cho(() => q(SW), 6000);
  if (!sw) return { ok: false, error: "Không thấy nút Switch Accounts trong menu H10" };
  sw.click();
  const as = await cho(() => { const a = [...document.querySelectorAll('a[data-testid^="header-user-account-"]')].filter(thay); return a.length && a; }, 8000);
  if (!as) return { ok: false, error: "Không mở được danh sách tài khoản H10" };
  const ds = as.map(a => {
    const dong = (a.innerText || "").split("\n").map(x => x.trim()).filter(Boolean);
    return { id: a.dataset.testid.replace("header-user-account-", ""), ten: dong[1] || dong[0] || "", href: a.href,
             dangDung: !!a.querySelector('input[type="radio"]')?.checked };
  });
  q(SW)?.click();   // nút Switch Accounts thành Cancel khi danh sách đang mở
  await sleep(300);
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
  return { ok: true, ds };
}
