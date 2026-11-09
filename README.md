# KW Biến Thể (bản tạm)

Lấy keyword ASIN đối thủ từ Cerebro (Helium 10) cho từng mã trong bảng Lark
**PPC - Phân tích Keyword**, gộp thành một bộ keyword có link riêng
`<domain>/kw-list/{Mã nội bộ}-{niche product}` rồi ghi link về Lark.

Python stdlib, không cần cài thư viện. Đọc/ghi Lark qua `lark-cli` (danh tính user của máy chạy).

```bash
HOST=127.0.0.1 PORT=8796 python3 -u server.py
```

## Luồng

1. **Phân tích ảnh sản phẩm.** Ảnh main được tải từ 🌼 2026 Product Flow, mỗi ảnh tải một lần rồi cache vào `data/img`. Chỉ căn cứ vào ảnh; Tên mẫu, Niche và Chất liệu trên Lark chỉ để tham khảo. Hiện người tự ghi kết quả vào form, nút "Phân tích bằng AI" chưa bật.
2. **Lấy keyword.** ASIN đối thủ lấy từ cột `ASIN đối thủ (>=3)` (ASIN trùng bị bỏ). Có thể thêm ASIN tạm trong tool. Cần tối thiểu 3 ASIN. Bấm "Tạo bộ & lấy keyword" thì mỗi ASIN thành một job trong hàng đợi.
   - Bộ lọc: kỳ **12/2025**, Exclude variations, SV ≥ 50, Organic rank ≥ 1, mỗi ASIN chạy 1 lần.
   - Nếu kỳ 12/2025 trả về 0 dòng (sản phẩm mới), server tự xếp lại job với **kỳ hiện tại, bỏ Time Period
     và không lọc SV / organic rank**. Kỳ đã dùng được ghi cho từng ASIN.
   - Khi extension chưa lấy được: bấm "Tải file tay" để nạp file Cerebro đã export (xlsx/csv).
3. **Trang `/kw-list/<tên bộ>`.** Hiển thị keyword đã gộp: mỗi keyword giữ dòng có organic rank tốt nhất, hoà thì lấy SV cao hơn. Có lọc, sắp xếp, tải CSV. Nút "Ghi link vào Lark" ghi vào cột `Link bộ Keyword`, có hộp xác nhận trước khi ghi.
4. **Xác định biến thể.** Bước sau, chưa có trong bản này.

## Extension Cerebro (`extension/`)

Extension Chrome (MV3) chạy trên máy đã đăng nhập Helium 10. Nó hỏi tool có job không, chạy
Cerebro trong một tab `members.helium10.com` mở nền bằng phiên đăng nhập sẵn có, rồi gửi keyword về.

**Cài:** mở `chrome://extensions`, bật Developer mode, bấm "Load unpacked", chọn thư mục `KW-Bien-The/extension`.
Bấm biểu tượng extension để mở popup: xem trạng thái, bật/tắt nhận job, đổi địa chỉ tool.

**Cách làm (cách C của Dearmine):** extension thao tác giao diện Cerebro như người và đọc JSON mà chính trang
nhận về. Không dùng API/MCP của H10, không đọc token; file Export bị chặn không tải về máy. Luồng soi tay
09/11/2026 (`data/capture/`), dữ liệu đi qua `h10api.pacvue.com/rta/cerebro/v1/…`:

1. Nhập ASIN vào ô "Enter a keyword…" (trang gọi `validate-asin`), tick `[data-testid=excludevariations]`.
2. Bấm `[data-testid=getkeywords]`; đã tìm trước đó thì bấm `[data-testid=runnewsearch]`
   (lượt kỳ hiện tại ngay sau lượt 12/2025 rỗng thì bấm "Load from…", không tốn lượt).
3. Kỳ 12/2025: ô Time Period (`placeholder="Current"`) chọn Dec 2025 → `[data-testid=applyfilters]`.
   Bộ lấy kiểm `periodFrom` trong request `search/history` trang gửi đi; sai kỳ thì báo lỗi, không ghi.
4. `[data-testid=exportdata]` → CSV/XLSX: trang tải `…/export/` (JSON toàn bộ dòng) rồi mới dựng file.
   Bộ lấy lấy JSON đó, lọc SV ≥ 50 (`impressionExact30`) và organic rank ≥ 1 (`organicPosition`).

Mỗi job gửi nhật ký từng bước về `/api/agent/capture` (`kind: "job-log"`, kèm giao diện lúc lỗi) để soát.
Cerebro báo hết lượt thì extension tự tắt "Nhận job". Chế độ "Soi Cerebro" trong popup ghi lại thao tác tay
và request khi H10 đổi giao diện cần soi lại.

Cách chạy một job:

- Mỗi 30 giây extension gọi `ping`.
- Chỉ khi có job chờ, chưa hết lượt và bộ lấy đã sẵn sàng thì nó mới mở tab H10. Nếu là trang đăng nhập, nó không nhận job: báo "H10 chưa đăng nhập" và 5 phút sau mới thử lại. Mở một trang H10 bất kỳ sau khi đăng nhập thì extension biết ngay.
- Nếu đã đăng nhập, nó nhận job và tiêm `ADAPTER.run(asin, filters)` vào tab. Giới hạn 8 phút mỗi job, nghỉ 10 giây giữa các job (đổi được trong popup).
- Hết hàng đợi thì đóng tab.

| Gọi | Ý nghĩa |
|---|---|
| `GET /api/agent/ping` | Báo còn sống, hỏi `{cho, het_luot}`. Không nhận job, không tính lượt |
| `GET /api/agent/next` | Lấy job kế tiếp → `{job: {id, asin, attempt, filters: {period: "2025-12" \| "current", exclude_variations, search_volume_min, organic_rank_min}}}` hoặc `{job: null}`. Mỗi job tính 1 lượt H10 (`DAILY_LIMIT`, mặc định 60/ngày) |
| `POST /api/agent/jobs/<id>/result` | Body `{period_used, rows: [{keyword, search_volume, search_volume_trend, organic_rank}]}`. `rows` rỗng ở kỳ 2025-12 thì server tự xếp lại job với kỳ hiện tại |
| `POST /api/agent/jobs/<id>/fail` | Body `{error}` |
| `POST /api/agent/capture` | Body `{items: [...]}`: request do chế độ "Ghi lại" bắt được |

- Header: `X-Agent-Token` (nếu không đặt `AGENT_TOKEN` thì server chỉ nhận từ localhost), `X-Agent-Version`, `X-Agent-H10` (`ok`/`logged_out`/`unknown`), `X-Agent-Ready`, `X-Agent-Running`. Thanh trên cùng của tool hiển thị các trạng thái này.
- Job ở trạng thái "đang lấy" quá 10 phút sẽ tự quay lại hàng đợi.
- Sơ đồ "cách C" dùng WebSocket. Bản này dùng HTTP hỏi định kỳ (stdlib), nội dung job và kết quả vẫn như cũ.
- Tool đặt ở domain khác localhost: nhập địa chỉ trong popup, Chrome sẽ hỏi quyền truy cập domain đó. Server phải đặt `AGENT_TOKEN`, và trong popup nhập cùng token.

## Biến môi trường

`HOST`, `PORT`, `PUBLIC_URL` (domain dựng link; trên Railway mặc định lấy `RAILWAY_PUBLIC_DOMAIN`),
`DATA_DIR`, `AGENT_TOKEN`, `DAILY_LIMIT`, `SV_MIN`, `RANK_MIN`, `LARK_BASE`, `LARK_TABLE`, `LARK_VIEW`,
`LARK_FLOW_TABLE`, `LARK_APP_ID` + `LARK_APP_SECRET` (có thì đọc Lark bằng Open API thay cho lark-cli),
`BRO_AUTH_URL` + `BRO_AUTH_API_KEY` (đăng nhập).

Ở máy: không cần biến nào, `HOST=127.0.0.1` và auth tắt. Bind ra ngoài mà thiếu bro-auth thì server tự thoát,
trừ khi đặt `ALLOW_NO_AUTH=1` (chạy không đăng nhập, ai có link cũng dùng được).

## Deploy Railway

Giống Kho-Keyword: Nixpacks + `railway.json`, health check `/healthz`.

1. New Project → Deploy from GitHub repo → chọn repo này.
2. Thêm **Volume** gắn vào `/data`, đặt biến `DATA_DIR=/data`. Không có volume thì mỗi lần deploy là mất hết bộ keyword và job.
3. Biến môi trường:
   - `BRO_AUTH_URL`, `BRO_AUTH_API_KEY`: lấy ở trang admin bro-auth, dùng chung tài khoản với Content-Listing.
     Giai đoạn tạm chưa gắn đăng nhập: bỏ hai biến này, đặt `ALLOW_NO_AUTH=1`.
   - `LARK_APP_ID`, `LARK_APP_SECRET`: cùng app Lark với Content-Listing (app đó đã được thêm vào Base `B53Nb…`).
   - `AGENT_TOKEN`: một chuỗi ngẫu nhiên dài. Nhập cùng chuỗi đó vào popup của extension.
4. Settings → Networking → Generate Domain. Domain này là phần đầu của link `…/kw-list/<tên bộ>` ghi vào Lark.

Quyền (bro-auth): `kw.view` xem bộ keyword (VIEWER trở lên); `kw.edit` tạo bộ, xếp job Cerebro, tải file,
ghi phân tích; `kw.lark` ghi link vào Lark. Kiểm bằng `python3 test_auth.py`.

## Cấu trúc

- `server.py`: HTTP + API
- `lark.py`: đọc bảng, tải ảnh, ghi link
- `cerebro.py`: đọc file Cerebro, gộp keyword
- `store.py`: lưu JSON trong `data/`
- `auth.py`: bảng quyền bro-auth (client ở `vendor/`)
- `web/`: giao diện (`index.html`, `kwlist.html`, `style.css`)
- `extension/`: extension Chrome (`background.js` vòng job, `adapter.js` bộ lấy Cerebro, `capture-*.js` ghi request, `popup.*`)
