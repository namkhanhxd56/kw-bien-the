// Chạy: node extension/kiem-tra.mjs
// Hàm tiêm vào tab (chrome.scripting.executeScript) chỉ được chuyển bằng mã nguồn, nên mã nguồn đó phải
// là một hàm hợp lệ khi đứng riêng. Viết `async run() {}` (method rút gọn) là hỏng mà không báo lỗi gì.
import { ADAPTER, laTrangDangNhap, dsTaiKhoan } from "./adapter.js";

let hong = 0;
for (const [ten, f] of [["ADAPTER.run", ADAPTER.run], ["laTrangDangNhap", laTrangDangNhap], ["dsTaiKhoan", dsTaiKhoan]]) {
  try {
    const g = new Function(`return (${f.toString()})`)();
    if (typeof g !== "function") throw new Error("không ra hàm");
    console.log(`  ok   ${ten} tiêm được vào tab`);
  } catch (e) {
    hong++;
    console.log(`  FAIL ${ten}: ${e.message}`);
  }
}
process.exit(hong ? 1 : 0);
