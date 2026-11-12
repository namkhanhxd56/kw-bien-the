# Hướng dẫn agent đọc bộ keyword final (KW Biến Thể)

Dành cho Claude hoặc agent khác cần đọc bộ keyword final của một mã sản phẩm. Ví dụ dùng khi viết content listing, chọn keyword quảng cáo hoặc soát niche.

Máy chủ: `https://web-production-f71ebe.up.railway.app`
Bản mới nhất của file này: `<máy chủ>/huong-dan-agent`

## Đừng đọc trang `/kw-list/...`

Link trong cột **Link bộ Keyword** trên Lark có dạng `<máy chủ>/kw-list/<tên bộ>`. Trang này do JavaScript dựng sau khi tải xong. Công cụ đọc web (WebFetch, fetch, curl) chỉ nhận được khung HTML rỗng, không có keyword nào. Đó là lý do agent "không đọc được web".

Cũng **đừng** mở trang bằng extension trình duyệt hay đọc qua ảnh chụp màn hình. Cách đó tốn token, chậm, dễ đọc sót, và chỉ thấy phần đang hiện trên màn hình.

Hãy gọi thẳng các đường dữ liệu bên dưới. Chúng trả chữ hoặc JSON, đọc một lần là đủ.

## Đọc bộ keyword: dùng `final.md`

```
GET <máy chủ>/api/lists/<tên bộ hoặc Mã>/final.md
```

- Có link `/kw-list/BSV051-hiking-ornament` thì đổi `/kw-list/` thành `/api/lists/` và thêm `/final.md`:
  `<máy chủ>/api/lists/BSV051-hiking-ornament/final.md`
- Chỉ có Mã sản phẩm thì dùng thẳng Mã: `<máy chủ>/api/lists/BSV051/final.md`

Tham số tuỳ chọn, giúp bớt token:

| Tham số | Tác dụng |
|---|---|
| `?kw=0` | Chỉ lấy bảng biến thể (tên, nhóm, mức sát, SV), không kèm danh sách keyword. Nên đọc cái này trước. |
| `?loai=product,gift` | Chỉ lấy các loại được liệt kê: `product`, `function`, `gift`, `personalized`, `occasion` |
| `?phu=0` | Bỏ khối "Chưa vào biến thể" (keyword chưa khớp biến thể nào, khối Khác, dính negative) |

Ghép được nhiều tham số, ví dụ `final.md?loai=product&phu=0`.

### Bản markdown có những gì

1. **Thông tin bộ**: mã, link, ASIN đối thủ và kỳ dữ liệu, số ASIN đã quét. Nếu dòng "Đã quét" ghi **CHƯA ĐỦ** thì bộ còn đang lấy dữ liệu và kết quả sẽ còn đổi, nên báo cho người dùng.
2. Mỗi **loại** là một mục `##`, theo thứ tự Product → Function → Gift → Personalized → Occasion. Mục đó gồm:
   - bảng biến thể: Mục · Nhóm · Biến thể · Mức sát · ASIN dùng · Rank tốt nhất · Tổng SV · Số kw;
   - từng biến thể một mục `###`, kèm bảng keyword (Keyword · SV · Rank · ASIN có), xếp theo SV giảm dần.

## Ý nghĩa các cột

| Cột | Nghĩa |
|---|---|
| **Loại** | Personalized: có personalized hoặc custom. Product: có ornament. Function: có decor hoặc decoration. Gift: có gift. Occasion: có dịp lễ. Xét theo đúng thứ tự này và mỗi keyword chỉ thuộc một loại. |
| **Mục** | `Nhóm 1` / `Nhóm 2` / `Nhóm 3`: biến thể có ở ≥ 3 / 2 / 1 ASIN đối thủ. `Cần xem xét`: rank tốt nhất > 50. `Loại`: người dùng đã bấm Loại vì không hợp sản phẩm. `Chưa vào biến thể`: keyword chưa khớp biến thể nào. |
| **Nhóm (theo số ASIN)** | Như Mục nhưng vẫn giữ cả với biến thể đã vào Cần xem xét |
| **Mức sát** | Tự tính từ số ASIN dùng biến thể và rank tốt nhất: **5 Sát · 4 Khá sát · 3 Trung bình · 2 Xa · 1 Không hợp** |
| **Đối tượng** | Biến thể của Gift là người nhận (women, hiker, horse lover…), không phải chủ đề |
| **Nhãn tay** | Nhãn người dùng tự gắn trên trang. `Không hợp` nghĩa là đã loại, đừng dùng keyword đó. |
| **ASIN dùng** | Số ASIN đối thủ có biến thể / tổng số ASIN của bộ |
| **Rank tốt nhất** | Organic rank tốt nhất của biến thể trong các ASIN đối thủ |
| **SV** | Search Volume (Cerebro / Helium 10) |

Cách tính mức sát:

| Số ASIN dùng | rank ≤ 20 | 21–50 | 51–75 | 76–100 |
|---|---|---|---|---|
| ≥ 3 ASIN | 5 | 4 | 2 | 1 |
| 2 ASIN | 4 | 3 | 2 | 1 |
| 1 ASIN | 3 | 3 | 1 | 1 |

Gợi ý khi dùng: ưu tiên Nhóm 1 rồi đến Nhóm 2, chọn biến thể có mức sát 4–5. "Cần xem xét" chỉ dùng khi đã kiểm tra là đúng sản phẩm. Không dùng mục "Loại".

## Các đường khác

| Cần gì | Đường |
|---|---|
| File Excel đầy đủ cho người dùng tải về | `GET /api/lists/<tên bộ hoặc Mã>/final.xlsx` |
| JSON đầy đủ của phần chia biến thể (lớn) | `GET /api/lists/<tên bộ>/bien-the` |
| Thông tin bộ, trạng thái từng ASIN và mọi keyword thô sau gộp (JSON) | `GET /api/lists/<tên bộ>` |
| Chỉ thông tin bộ, không kèm keyword | `GET /api/lists/<tên bộ>?rows=0` |
| Keyword thô sau gộp, chưa chia biến thể (CSV) | `GET /api/lists/<tên bộ>/export.csv` |

File Excel `final.xlsx` gồm các sheet:
- **Tổng hợp**: mọi biến thể, kèm rank ở từng ASIN, mức sát, bậc lọc và root;
- **Product / Function / Gift / Personalized / Occasion**: mỗi dòng một keyword, có cột Mục, Nhóm, Biến thể, Mức sát, nên lọc được;
- **Tất cả keyword**: tính cả keyword ngoài bộ lọc (SV < 50 hoặc rank ngoài 1–100);
- **Ghi chú**: giải thích các cột.

Agent nên đọc bản `.md`. File `.xlsx` để người dùng tải.

`/api/products` trả về khoảng 2 MB cho khoảng 1.500 mã. **Đừng gọi** nó chỉ để tìm một bộ, hãy dùng thẳng Mã như ở trên.

## Quyền truy cập

- Hiện tool không bắt đăng nhập, nên agent gọi thẳng được.
- Nếu sau này bật đăng nhập (bro-auth), các đường trên sẽ trả về trang đăng nhập hoặc lỗi 403. Khi đó cần cookie phiên của người dùng; đừng tự nhập mật khẩu.
- **Claude Code** hỏi quyền theo từng domain khi dùng WebFetch. Để không bị hỏi lại, thêm vào `.claude/settings.json` (hoặc `~/.claude/settings.json`):
  ```json
  { "permissions": { "allow": ["WebFetch(domain:web-production-f71ebe.up.railway.app)"] } }
  ```
  Hoặc dùng `curl -s <url>` trong Bash.
- **Ứng dụng Claude (claude.ai / desktop)**: tính năng đọc web có thể chỉ nhận link người dùng dán vào chat. Hãy dán thẳng link `.../final.md` vào chat thay vì link `/kw-list/...`.
- **Chỉ đọc.** Các đường POST (tạo bộ, xếp Cerebro, xoá keyword, ghi Lark) làm thay đổi dữ liệu chung và tốn lượt H10. Không gọi khi người dùng chưa yêu cầu rõ.
