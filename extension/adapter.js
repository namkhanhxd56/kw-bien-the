// Bộ lấy Cerebro: hàm `run` được tiêm vào tab Cerebro (world MAIN) và chạy bằng phiên đăng nhập
// sẵn có của trang. Hàm phải tự đủ (không dùng biến bên ngoài) vì Chrome chỉ chuyển mã nguồn
// của hàm sang trang.
//
// Cách C (Dearmine): thao tác giao diện Cerebro như người (nhập ASIN, Get Keywords, Clear, Export) và
// đọc JSON chính trang nhận về; không dùng API/MCP của H10, không đọc token.
// CHƯA XONG: cần soi 1 lượt thao tác tay (popup → "Soi Cerebro"), tool lưu ở data/capture/<ngày>.jsonl.
//
// Hợp đồng trả về:
//   { ok: true, period_used: "2025-12" | "current",
//     rows: [{ keyword, search_volume, search_volume_trend, organic_rank }] }
//   { ok: false, error: "..." , login: true }   // login: true nếu phiên H10 đã hết
// rows rỗng ở kỳ 2025-12 là bình thường: server tự xếp lại job với kỳ hiện tại.

export const ADAPTER = {
  ready: false,
  version: "chua-co",
  cerebroUrl: "https://members.helium10.com/cerebro-new",

  async run(asin, filters) {
    void asin; void filters;
    return { ok: false, error: "Chưa có bộ lấy Cerebro (cần soi Cerebro 1 lượt trước)" };
  },
};

// Kiểm tra trang đang mở có phải trang đăng nhập H10 không. Tiêm vào tab, phải tự đủ.
export function laTrangDangNhap() {
  return /\/(login|signin|sign-in)/i.test(location.pathname) || !!document.querySelector('input[type="password"]');
}
