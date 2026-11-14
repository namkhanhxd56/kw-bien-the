// Nền của extension: hỏi tool KW Biến Thể có job Cerebro không, chạy job trong một tab
// members.helium10.com chạy ngầm (dùng phiên đăng nhập H10 của Chrome này), gửi kết quả về.
// Mỗi lần chỉ chạy 1 job, nghỉ giữa các job để không dồn request lên H10.
import { ADAPTER, laTrangDangNhap, dsTaiKhoan } from "./adapter.js";

const VERSION = chrome.runtime.getManifest().version;
const MAC_DINH = { server: "http://localhost:8796", token: "", running: true, capture: false, nghi: 10, ten: "" };
const HET_GIO_JOB = 8 * 60 * 1000;   // server tự trả job về hàng đợi sau 10 phút
const HET_GIO_TAB = 60 * 1000;

let ban = false;
let boDemCapture = [];
let henCapture = null;

// ---------------------------------------------------------------- cấu hình & trạng thái
const cfg = () => chrome.storage.local.get(MAC_DINH);
// Mỗi máy một id cố định để tool phân biệt khi nhiều máy cùng chạy hàng đợi
async function mayId() {
  let { agentId } = await chrome.storage.local.get("agentId");
  if (!agentId) {
    agentId = "may-" + crypto.randomUUID().slice(0, 8);
    await chrome.storage.local.set({ agentId });
  }
  return agentId;
}
async function st() {
  return (await chrome.storage.session.get({ st: { phase: "idle", h10: "unknown", job: null, last: null, error: null, captured: 0, tabId: null } })).st;
}
let hangGhi = Promise.resolve();   // ghi trạng thái lần lượt để các lần ghi không đè nhau
function datSt(p) {
  hangGhi = hangGhi.then(async () => {
    const s = { ...(await st()), ...p, at: Date.now() };
    await chrome.storage.session.set({ st: s });
    return s;
  });
  return hangGhi;
}

async function api(path, { method = "GET", body } = {}) {
  const c = await cfg(), s = await st(), id = await mayId();
  let r;
  try {
    r = await fetch(c.server.replace(/\/$/, "") + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Agent-Token": c.token,
        "X-Agent-Id": id,
        "X-Agent-Ten": encodeURIComponent(c.ten || ""),
        "X-Agent-Version": VERSION,
        "X-Agent-H10": s.h10,
        "X-Agent-Ready": ADAPTER.ready ? "1" : "0",
        "X-Agent-Running": c.running ? "1" : "0",
        "X-Agent-Loi": encodeURIComponent(String(s.error || "").slice(0, 300)),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    await datSt({ tool: "loi" });
    throw new Error("Không kết nối được tool ở " + c.server);
  }
  const d = await r.json().catch(() => ({}));
  await datSt({ tool: r.status === 401 ? "token" : "ok" });
  if (!r.ok || d.ok === false) throw new Error(d.error || `Tool trả lỗi ${r.status}`);
  return d;
}

// ---------------------------------------------------------------- tab Cerebro
function choTabTai(tabId) {
  return new Promise((ok, loi) => {
    const het = setTimeout(() => { chrome.tabs.onUpdated.removeListener(nghe); loi(new Error("Trang H10 tải quá lâu")); }, HET_GIO_TAB);
    function nghe(id, info) {
      if (id === tabId && info.status === "complete") { clearTimeout(het); chrome.tabs.onUpdated.removeListener(nghe); ok(); }
    }
    chrome.tabs.onUpdated.addListener(nghe);
    chrome.tabs.get(tabId).then(t => { if (t.status === "complete") nghe(tabId, { status: "complete" }); }).catch(loi);
  });
}

async function moTab() {
  const s = await st();
  if (s.tabId != null) {
    try {
      const t = await chrome.tabs.get(s.tabId);
      if (/^https:\/\/members\.helium10\.com\//.test(t.url || t.pendingUrl || "")) { await choTabTai(t.id); return t.id; }
    } catch { /* tab đã đóng */ }
  }
  const t = await chrome.tabs.create({ url: ADAPTER.cerebroUrl, active: false });
  await datSt({ tabId: t.id });
  await choTabTai(t.id);
  return t.id;
}

async function dongTab() {
  const s = await st();
  if (s.tabId == null) return;
  await chrome.tabs.remove(s.tabId).catch(() => {});
  await datSt({ tabId: null });
}

async function chayTrongTab(tabId, func, args = []) {
  const [kq] = await chrome.scripting.executeScript({ target: { tabId }, world: "MAIN", func, args });
  return kq?.result;
}

// ---------------------------------------------------------------- vòng nhận job
async function tick() {
  if (ban) return;
  ban = true;
  try {
    const c = await cfg();
    const p = await api("/api/agent/ping");
    if (!c.running || !ADAPTER.ready || !p.cho || p.het_luot) {
      await dongTab();
      await datSt({ phase: !c.running ? "paused" : !ADAPTER.ready ? "no_adapter" : p.het_luot ? "limit" : "idle", error: null });
      return;
    }

    // Có job chờ: kiểm tra phiên H10 trước khi nhận, để không mất lượt vì chưa đăng nhập.
    // Đã biết là chưa đăng nhập thì 5 phút mới mở tab thử lại (mở trang H10 bất kỳ sau khi
    // đăng nhập sẽ báo về ngay qua capture-relay.js).
    const s = await st();
    if (s.h10 === "logged_out" && Date.now() - (s.h10At || 0) < 5 * 60 * 1000) {
      await datSt({ phase: "idle", error: "H10 chưa đăng nhập trên Chrome này" });
      return;
    }
    const tabId = await moTab();
    if (await chayTrongTab(tabId, laTrangDangNhap)) {
      await dongTab();
      await datSt({ phase: "idle", h10: "logged_out", h10At: Date.now(), error: "H10 chưa đăng nhập trên Chrome này" });
      await api("/api/agent/ping");
      return;
    }
    await datSt({ h10: "ok", h10At: Date.now() });

    const { job } = await api("/api/agent/next");
    if (!job) { await datSt({ phase: "idle" }); return; }
    const kq = await chayJob(tabId, job);
    if (!kq.dung) setTimeout(tick, c.nghi * 1000);   // làm job kế tiếp; H10 đăng xuất / hết lượt thì dừng
  } catch (e) {
    await datSt({ phase: "error", error: String(e.message || e) });
  } finally {
    ban = false;
  }
}

// ---------------------------------------------------------------- đổi tài khoản H10
// Một phiên đăng nhập H10 có thể có 2–3 tài khoản (menu avatar → Switch Accounts). Tài khoản chỉ có bản demo
// Cerebro hoặc hết lượt thì ghi nhớ một thời gian và chuyển sang tài khoản khác, không cần mật khẩu.
const TK_NHO = { demo: 12 * 3600 * 1000, het_luot: 20 * 3600 * 1000 };

async function tkBiKhoa() {
  const { tkKhoa = {} } = await chrome.storage.local.get("tkKhoa");
  const now = Date.now();
  return Object.fromEntries(Object.entries(tkKhoa).filter(([, v]) => now - v.at < (TK_NHO[v.ly] || 0)));
}

async function doiTaiKhoan(tabId, ly) {
  const r = await chayTrongTab(tabId, dsTaiKhoan).catch(e => ({ ok: false, error: String(e.message || e) }));
  if (!r?.ok) return { ok: false, error: r?.error || "Không đọc được danh sách tài khoản H10" };
  const khoa = await tkBiKhoa();
  const cu = r.ds.find(a => a.dangDung);
  if (cu) khoa[cu.id] = { ly, ten: cu.ten, at: Date.now() };
  await chrome.storage.local.set({ tkKhoa: khoa });
  const moi = r.ds.find(a => !a.dangDung && !khoa[a.id]);
  if (!moi) return { ok: false, error: `${r.ds.length} tài khoản H10 trên Chrome này đều đang bị khoá Cerebro hoặc hết lượt` };
  await chrome.tabs.update(tabId, { url: moi.href });   // link của chính menu H10: …/dashboard?accountId=<id>
  await new Promise(ok => setTimeout(ok, 1500));
  await choTabTai(tabId);
  await datSt({ tk: { id: moi.id, ten: moi.ten, at: Date.now() } });
  return { ok: true, cu, moi };
}

// Mở trang tìm mới của Cerebro trước mỗi job (sau job trước, tab còn ở trang /view/<id>)
async function veTrangTim(tabId) {
  await chrome.tabs.update(tabId, { url: ADAPTER.cerebroUrl });
  await new Promise(r => setTimeout(r, 1500));
  await choTabTai(tabId);
}

// Mỗi job chạy tối đa 2 lần: lần 1 lỗi thì đóng tab, mở tab mới chạy lại; vẫn lỗi thì báo lỗi job đó
// và để tick làm job kế tiếp (một ASIN lỗi không kéo cả hàng đợi). Lần chạy lại không tốn thêm lượt tìm:
// Cerebro hiện hộp thoại "đã tìm trước đó" và bộ lấy mở lại lượt vừa tạo.
// H10 đăng xuất: trả job về hàng đợi (không tính lượt), dừng nhận job cho tới khi đăng nhập lại.
// Hết lượt Cerebro: báo lỗi job, tắt "Nhận job".
const SO_LAN_CHAY = 2;

async function chayMotLan(tabId, job) {
  await veTrangTim(tabId);
  if (await chayTrongTab(tabId, laTrangDangNhap)) return { ok: false, login: true, error: "H10 đã đăng xuất trên Chrome này", log: [] };
  const kq = await Promise.race([
    chayTrongTab(tabId, ADAPTER.run, [job.asin, { ...job.filters, attempt: job.attempt }]),
    new Promise(ok => setTimeout(() => ok({ ok: false, error: "Cerebro chạy quá 8 phút", log: [] }), HET_GIO_JOB)),
  ]);
  return kq || { ok: false, error: "Bộ lấy Cerebro không trả kết quả", log: [] };
}

async function chayJob(tabId, job) {
  await datSt({ phase: "running", job: { id: job.id, asin: job.asin, period: job.filters.period, start: Date.now() }, error: null });
  const giuThuc = setInterval(() => chrome.runtime.getPlatformInfo(), 20000);   // giữ service worker sống
  let kq = null, lan = 0, doi = 0;
  try {
    for (lan = 1; lan <= SO_LAN_CHAY; lan++) {
      try {
        kq = await chayMotLan(tabId, job);
      } catch (e) {
        kq = { ok: false, error: String(e.message || e), log: [] };
      }
      guiNhatKy(job, kq, lan);
      // Tài khoản chỉ có bản demo / hết lượt: chuyển tài khoản H10 rồi chạy lại (không tính vào số lần chạy)
      if (kq.khoa || kq.het_luot) {
        const d = doi < 3 ? await doiTaiKhoan(tabId, kq.khoa ? "demo" : "het_luot") : { ok: false, error: "đã đổi tài khoản 3 lần" };
        if (d.ok) {
          doi++; lan--;
          await datSt({ error: `${job.asin}: ${kq.khoa ? "tài khoản bị khoá Cerebro" : "hết lượt"} ở ${d.cu?.ten || "tài khoản cũ"} → chuyển sang ${d.moi.ten}` });
          continue;
        }
        kq = { ...kq, het_luot: true, error: `${kq.error} · ${d.error}` };
        break;
      }
      if (kq.ok || kq.login || lan === SO_LAN_CHAY) break;
      // Lỗi khác: đóng tab, mở tab mới rồi chạy lại một lần
      await datSt({ job: { id: job.id, asin: job.asin, period: job.filters.period, start: Date.now(), chay_lai: true },
                    error: `${job.asin}: ${kq.error} → đóng tab, chạy lại 1 lần` });
      await dongTab();
      tabId = await moTab();
    }

    if (kq.login) {
      await api(`/api/agent/jobs/${job.id}/release`, { method: "POST", body: { error: kq.error } }).catch(() => {});
      await datSt({ phase: "idle", job: null, h10: "logged_out", h10At: Date.now(),
                    error: "H10 đã đăng xuất: dừng nhận job, đăng nhập lại Helium 10 để chạy tiếp" });
      return { dung: true };
    }
    if (!kq.ok && kq.het_luot) {
      // Hết tài khoản dùng được: trả job về hàng (máy khác lấy, không tính lượt), tắt "Nhận job" ở máy này
      await chrome.storage.local.set({ running: false });
      await api(`/api/agent/jobs/${job.id}/release`, { method: "POST", body: { error: kq.error } }).catch(() => {});
      await datSt({ phase: "limit", job: null, error: `${job.asin}: ${kq.error} → trả job về hàng, tắt nhận job` });
      return { dung: true };
    }
    if (!kq.ok) {
      const msg = kq.het_luot ? `Hết lượt Cerebro: ${kq.error}` : `${kq.error} (đã chạy ${lan} lần)`;
      await api(`/api/agent/jobs/${job.id}/fail`, { method: "POST", body: { error: msg } }).catch(() => {});
      await datSt({ phase: kq.het_luot ? "limit" : "idle", job: null, error: `${job.asin}: ${msg}`,
                    last: { asin: job.asin, loi: msg, at: Date.now() } });
      return { dung: !!kq.het_luot };
    }
    const d = await api(`/api/agent/jobs/${job.id}/result`, { method: "POST", body: { period_used: kq.period_used, rows: kq.rows } });
    await datSt({ phase: "idle", job: null, error: null,
                  last: { asin: job.asin, period: kq.period_used, so: kq.rows.length, tiep: d.tiep || null, at: Date.now() } });
    return { dung: false };
  } finally {
    clearInterval(giuThuc);
    api("/api/agent/ping").catch(() => {});   // báo ngay trạng thái mới (đăng xuất / lỗi) để tool hiện dòng thông báo
  }
}

// Nhật ký từng bước (và giao diện lúc lỗi) gửi về tool để soát / sửa bộ lấy
function guiNhatKy(job, kq, lan) {
  api("/api/agent/capture", { method: "POST", body: { items: [{
    kind: "job-log", job: job.id, asin: job.asin, period: job.filters.period, attempt: job.attempt, lan_chay: lan,
    ok: !!kq?.ok, error: kq?.error || null, period_used: kq?.period_used || null, so: kq?.rows?.length ?? null,
    log: kq?.log || [], debug: kq?.debug || null, adapter: ADAPTER.version, t: Date.now(),
  }] } }).catch(() => {});
}

// ---------------------------------------------------------------- ghi lại request (dò API)
function guiCaptureSau() {
  if (henCapture) return;
  henCapture = setTimeout(async () => {
    henCapture = null;
    const items = boDemCapture.splice(0, 200);
    if (!items.length) return;
    try {
      await api("/api/agent/capture", { method: "POST", body: { items } });
      await datSt({ captured: (await st()).captured + items.length });
    } catch (e) {
      await datSt({ error: "Không gửi được request đã ghi: " + (e.message || e) });
    }
    if (boDemCapture.length) guiCaptureSau();
  }, 2000);
}

// ---------------------------------------------------------------- sự kiện
chrome.runtime.onMessage.addListener((m, sender, tra) => {
  if (m?.type === "capture") {
    if (boDemCapture.length < 1000) boDemCapture.push(m.item);
    guiCaptureSau();
    return false;
  }
  if (m?.type === "h10page") {
    datSt({ h10: m.login ? "logged_out" : "ok", h10At: Date.now() });
    return false;
  }
  if (m?.type === "state") {
    Promise.all([cfg(), st()]).then(([c, s]) => tra({ cfg: c, st: s, adapter: { ready: ADAPTER.ready, version: ADAPTER.version }, version: VERSION }));
    return true;
  }
  if (m?.type === "save") {
    // Bật lại "Nhận job" bằng tay: quên các tài khoản đã đánh dấu khoá / hết lượt để thử lại từ đầu
    const xoaKhoa = m.cfg.running === true ? chrome.storage.local.remove("tkKhoa") : Promise.resolve();
    xoaKhoa.then(() => chrome.storage.local.set(m.cfg)).then(() => { tick(); tra({ ok: true }); });
    return true;
  }
  if (m?.type === "tick") {
    tick().then(() => st()).then(s => tra({ st: s }));
    return true;
  }
  if (m?.type === "openCerebro") {
    chrome.tabs.create({ url: ADAPTER.cerebroUrl, active: true }).then(() => tra({ ok: true }));
    return true;
  }
  return false;
});

chrome.alarms.onAlarm.addListener(a => { if (a.name === "poll") tick(); });
chrome.alarms.get("poll").then(a => { if (!a) chrome.alarms.create("poll", { periodInMinutes: 0.5 }); });
chrome.runtime.onStartup.addListener(tick);
chrome.runtime.onInstalled.addListener(tick);
