// Bộ lấy Cerebro: hàm `run` được tiêm vào tab members.helium10.com (world MAIN) và gọi API
// của Cerebro bằng phiên đăng nhập sẵn có của trang. Hàm phải tự đủ (không dùng biến bên ngoài)
// vì Chrome chỉ chuyển mã nguồn của hàm sang trang.
//
// CHƯA XONG: cần biết request thật của Cerebro (chạy tìm ASIN, chờ báo cáo, lấy trang kết quả
// với bộ lọc). Bật "Ghi lại request" trong popup, chạy Cerebro tay 1 lần với đúng bộ lọc,
// tool sẽ lưu request vào data/capture/<ngày>.jsonl để viết phần này.
//
// Hợp đồng trả về:
//   { ok: true, period_used: "2025-12" | "current",
//     rows: [{ keyword, search_volume, search_volume_trend, organic_rank }] }
//   { ok: false, error: "..." , login: true }   // login: true nếu phiên H10 đã hết
// rows rỗng ở kỳ 2025-12 là bình thường: server tự xếp lại job với kỳ hiện tại.

export const ADAPTER = {
  ready: false,
  version: "chua-co",
  cerebroUrl: "https://members.helium10.com/cerebro",

  async run(asin, filters) {
    void asin; void filters;
    return { ok: false, error: "Chưa có bộ lấy Cerebro (cần dò API trước)" };
  },
};

// Kiểm tra trang đang mở có phải trang đăng nhập H10 không. Tiêm vào tab, phải tự đủ.
export function laTrangDangNhap() {
  return /\/(login|signin|sign-in)/i.test(location.pathname) || !!document.querySelector('input[type="password"]');
}
