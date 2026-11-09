/* Một dòng thông báo dưới thanh trên cùng khi extension có vấn đề: H10 đăng xuất (job dừng, đăng nhập lại
   là chạy tiếp) hoặc lỗi mới nhất extension báo về. Dùng chung cho trang chính và trang /kw-list. */
(() => {
  const el = document.createElement("div");
  el.className = "bao";
  el.setAttribute("role", "status");
  el.hidden = true;
  document.querySelector(".topbar")?.after(el);
  async function xem() {
    try {
      const a = (await (await fetch("/api/status")).json()).agent || {};
      let text = "", cls = "";
      if (a.online && a.h10 === "logged_out") {
        text = "Helium 10 đã đăng xuất trên Chrome chạy extension: job đang dừng, chưa tốn lượt. Đăng nhập lại H10 là extension chạy tiếp.";
        cls = "bad";
      } else if (a.online && a.loi) {
        text = "Extension báo: " + a.loi;
        cls = "warn";
      }
      el.textContent = text;
      el.className = "bao " + cls;
      el.hidden = !text;
    } catch { /* tool không trả lời: để nguyên */ }
  }
  xem();
  setInterval(xem, 20000);
})();
