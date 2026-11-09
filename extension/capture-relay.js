// Chạy trong trang members.helium10.com (world ISOLATED). Nhận request do capture-main.js ghi,
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
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", baoDangNhap);
else baoDangNhap();
