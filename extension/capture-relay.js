// Chạy trong mọi trang/khung *.helium10.com (world ISOLATED). Nhận request do capture-main.js ghi,
// chỉ chuyển cho background khi đang bật "Ghi lại request" trong popup.
let bat = null;
const cho = [];

chrome.storage.local.get({ capture: false }).then(c => {
  bat = !!c.capture;
  if (bat) cho.forEach(gui);
  cho.length = 0;
});
chrome.storage.onChanged.addListener((ch, area) => {
  if (area === "local" && ch.capture) bat = !!ch.capture.newValue;
});

function gui(item) {
  chrome.runtime.sendMessage({ type: "capture", item }).catch(() => { /* background đang ngủ, bỏ qua */ });
}

window.addEventListener("message", e => {
  if (e.source !== window || e.data?.__kwbt !== "capture") return;
  if (bat === null) { if (cho.length < 200) cho.push(e.data.item); return; }
  if (bat) gui(e.data.item);
});

// Báo trạng thái đăng nhập H10 cho background mỗi khi mở một trang H10
function baoDangNhap() {
  const login = /\/(login|signin|sign-in)/i.test(location.pathname) || !!document.querySelector('input[type="password"]');
  chrome.runtime.sendMessage({ type: "h10page", login }).catch(() => {});
}
if (window === top) {   // chỉ trang chính báo; khung con của H10 không phải trang đăng nhập
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", baoDangNhap);
  else baoDangNhap();
}

// Chế độ ghi lại còn ghi cả thao tác tay (nút bấm, ô nhập) để biết các bước trên giao diện Cerebro
function moTa(el) {
  if (!el || el.nodeType !== 1) return null;
  const attrs = {};
  for (const a of el.attributes) {
    if (/^(id|name|type|role|aria-[\w-]+|placeholder|title|for|href|data-[\w-]+)$/.test(a.name)) attrs[a.name] = a.value.slice(0, 120);
  }
  return { tag: el.tagName.toLowerCase(), text: (el.innerText || el.value || "").trim().replace(/\s+/g, " ").slice(0, 80),
           cls: String(el.className?.baseVal ?? el.className ?? "").split(/\s+/).filter(Boolean).slice(0, 6).join(" "), attrs };
}
function duong(el) {
  const out = [];
  for (let e = el, i = 0; e && e.nodeType === 1 && i < 6; e = e.parentElement, i++) out.push(moTa(e));
  return out;
}
function ghiThaoTac(kind, e) {
  if (!bat) return;
  const t = e.target;
  const nut = t.closest?.('button, a, [role="button"], [role="tab"], [role="menuitem"], [role="option"], label, input, select') || t;
  const item = { kind, el: moTa(nut), path: duong(t), page: location.href.replace(location.origin, ""), host: location.host, frame: window !== top, t: Date.now() };
  if (kind === "change" && t.matches?.("input, select, textarea") && t.type !== "password") {
    item.value = t.type === "checkbox" || t.type === "radio" ? String(t.checked) : String(t.value).slice(0, 200);
  }
  gui(item);
}
document.addEventListener("click", e => ghiThaoTac("click", e), true);
document.addEventListener("change", e => ghiThaoTac("change", e), true);
