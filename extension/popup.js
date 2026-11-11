const $ = s => document.querySelector(s);
const KY = { "2025-12": "12/2025", current: "kỳ hiện tại" };
const PHASE = {
  idle: ["Đang chờ job", "on"], running: ["Đang lấy", "on"], paused: ["Tạm dừng", "warn"],
  no_adapter: ["Chưa nhận job (thiếu bộ lấy)", "warn"], limit: ["Hết lượt H10 hôm nay", "warn"], error: ["Lỗi", "off"],
};
let daDienForm = false;

const gio = t => new Date(t).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
function dat(id, text, dot) {
  $("#v-" + id).textContent = text;
  if (dot !== undefined) $("#d-" + id).className = "dot " + dot;
}

async function ve() {
  const d = await chrome.runtime.sendMessage({ type: "state" });
  const { cfg: c, st: s, adapter: a } = d;
  $("#ver").textContent = "v" + d.version;

  dat("tool", { ok: "Đã kết nối", loi: "Không kết nối được", token: "Sai agent token" }[s.tool] || "Chưa thử",
      { ok: "on", loi: "off", token: "off" }[s.tool] || "");
  dat("h10", { ok: "Đã đăng nhập", logged_out: "Chưa đăng nhập", unknown: "Chưa rõ (kiểm tra khi có job)" }[s.h10] || s.h10,
      { ok: "on", logged_out: "off" }[s.h10] || "");
  dat("adapter", a.ready ? `Sẵn sàng (${a.version})` : "Chưa có, cần soi Cerebro 1 lượt", a.ready ? "on" : "warn");

  const [nhan, dot] = PHASE[s.phase] || [s.phase, ""];
  dat("job", s.job ? `${nhan}: ${s.job.asin} · ${KY[s.job.period] || s.job.period}` : nhan, dot);
  const L = s.last;
  $("#v-last").textContent = !L ? "—" : L.loi ? `${L.asin} lỗi lúc ${gio(L.at)}`
    : L.tiep ? `${L.asin}: 12/2025 trống, chuyển kỳ hiện tại (${gio(L.at)})`
    : `${L.asin}: ${L.so.toLocaleString("vi-VN")} keyword, ${KY[L.period] || L.period} (${gio(L.at)})`;
  $("#loi").textContent = s.error || "";
  $("#v-cap").textContent = (s.captured || 0).toLocaleString("vi-VN");

  $("#c-running").checked = c.running;
  $("#c-capture").checked = c.capture;
  if (!daDienForm) {
    $("#i-server").value = c.server; $("#i-token").value = c.token; $("#i-nghi").value = c.nghi; $("#i-ten").value = c.ten || "";
    daDienForm = true;
  }
}

async function luu(p) {
  await chrome.runtime.sendMessage({ type: "save", cfg: p });
  await ve();
}

$("#c-running").addEventListener("change", e => luu({ running: e.target.checked }));
$("#c-capture").addEventListener("change", e => luu({ capture: e.target.checked }));
$("#b-open").addEventListener("click", () => chrome.runtime.sendMessage({ type: "openCerebro" }));
$("#b-tick").addEventListener("click", async e => {
  e.target.disabled = true;
  await chrome.runtime.sendMessage({ type: "tick" });
  await ve();
  e.target.disabled = false;
});

$("#f").addEventListener("submit", async e => {
  e.preventDefault();
  let server;
  try { server = new URL($("#i-server").value.trim()).origin; }
  catch { $("#saved").textContent = "Địa chỉ không hợp lệ"; return; }
  // Tool không ở máy này: xin quyền truy cập domain đó (Chrome hỏi người dùng)
  if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(server)) {
    const ok = await chrome.permissions.request({ origins: [server + "/*"] }).catch(() => false);
    if (!ok) { $("#saved").textContent = "Chưa được cấp quyền truy cập " + server; return; }
  }
  const nghi = Math.min(300, Math.max(5, parseInt($("#i-nghi").value, 10) || 10));
  await luu({ server, token: $("#i-token").value.trim(), nghi, ten: $("#i-ten").value.trim() });
  $("#i-server").value = server; $("#i-nghi").value = nghi;
  $("#saved").textContent = "Đã lưu";
  setTimeout(() => { $("#saved").textContent = ""; }, 2000);
});

ve();
setInterval(ve, 2000);
