# Quy trình làm việc với KW Biến Thể

Hướng dẫn cho người dùng tool hằng ngày: từ một mã sản phẩm trên Lark đến bộ keyword đã chia biến thể, sẵn sàng
đưa sang viết content hoặc chạy PPC.

- Tool: https://web-production-f71ebe.up.railway.app
- Cách tool chia biến thể, gom nhóm, tính mức sát: xem [CACH-PHAN-LOAI.md](CACH-PHAN-LOAI.md)
- Agent khác (Claude…) đọc và xử lý bộ keyword: xem [HUONG-DAN-AGENT.md](HUONG-DAN-AGENT.md)

## Các trang của tool

| Trang | Dùng để |
|---|---|
| **Trang chính** `/` | Danh sách mã từ bảng Lark **PPC - Phân tích Keyword**. Chọn mã: xem ảnh, ASIN đối thủ, tạo bộ, lấy keyword, ghi link về Lark |
| **Bộ keyword** `/kw-list/<tên bộ>` | Biến thể đã chia, soát và loại, xoá keyword, sao chép, tải Excel final. Link này được ghi vào cột Link bộ Keyword trên Lark |
| **Hàng đợi** `/hang-doi` | Bộ nào đang chờ lấy keyword, máy nào đang chạy, bỏ bớt hàng đợi, dừng tool, cài máy mới |

---

## Phần A. Chuẩn bị máy lấy keyword (làm một lần)

Keyword được lấy bằng **extension Chrome** chạy trên máy đã đăng nhập Helium 10. Extension tự mở Cerebro trong
một tab nền, nhập ASIN, chọn kỳ 12/2025, lấy keyword rồi gửi về tool. Càng nhiều máy chạy thì hàng đợi xong càng
nhanh.

1. Vào trang **Hàng đợi**, bấm **Thêm máy**, tải `extension.zip` rồi giải nén ra một thư mục cố định. Không xoá
   thư mục này sau khi cài.
2. Mở `chrome://extensions`, bật **Developer mode**, bấm **Load unpacked**, rồi chọn thư mục vừa giải nén.
3. Bấm biểu tượng extension, vào mục **Kết nối tool**:
   - điền địa chỉ tool;
   - dán **Agent token** (hỏi người quản lý tool, giống các máy đang chạy);
   - đặt **Tên máy**;
   - bấm **Lưu kết nối** và cho phép truy cập khi Chrome hỏi.
4. Đăng nhập **Helium 10** trên Chrome đó.
5. Bật **Nhận job** trong popup. Trong khoảng 30 giây máy sẽ hiện ở bảng "Máy đang chạy" của trang Hàng đợi.

Popup extension cho biết:
- trạng thái kết nối tool;
- Helium 10 đã đăng nhập chưa, và đã chuyển sang tài khoản nào;
- việc đang làm và kết quả lần cuối.

**Khi có bản extension mới:** tải lại `extension.zip`, chép đè vào thư mục cũ, rồi bấm nút tải lại ↻ của
extension ở `chrome://extensions`. Popup hiện số phiên bản (hiện tại là v0.1.9).

**Nhiều tài khoản H10:** một phiên đăng nhập H10 có thể có 2–3 tài khoản (avatar → Switch Accounts). Từ bản 0.1.9,
extension tự chuyển tài khoản khi gặp một trong hai trường hợp:
- tài khoản đang dùng chỉ có bản demo Cerebro (ô ASIN xám, bấm vào đòi Upgrade);
- tài khoản đang dùng hết lượt.

Khi mọi tài khoản đều không dùng được, extension trả job về hàng đợi cho máy khác và tự **tắt Nhận job**.

---

## Phần B. Làm một mã: từ Lark đến bộ keyword

### Bước 1. Chọn mã

Ở cột trái trang chính:
- **Tìm:** gõ mã, tên mẫu, niche hoặc ASIN.
- **Lọc trạng thái:**
  - Chưa tạo bộ;
  - **Đủ ≥ 3 ASIN, chưa lấy keyword**;
  - Chờ / đang lấy keyword;
  - Bộ còn thiếu ASIN;
  - Đủ keyword;
  - Dưới 3 ASIN;
  - Đã xem ảnh / Chưa xem ảnh.
- **Sắp xếp:** theo thứ tự Lark, mã A→Z, hoặc nhiều ASIN trước.

Lark vừa được sửa (thêm mã, thêm ASIN) thì bấm **Tải lại từ Lark**.

### Bước 2. Xem ảnh sản phẩm (mục 1)

- Xem ảnh main để biết sản phẩm thật là gì. **Chỉ tin ảnh.** Tên mẫu, Niche, Chất liệu trên Lark chỉ để tham khảo.
- Ghi kết luận vào form, đặc biệt dòng **Kết luận sơ bộ: niche thật của sản phẩm**, rồi bấm **Lưu phân tích**.
  Kết luận này dùng để phán biến thể nào sát sản phẩm ở bước 5.
- Nút "Phân tích bằng AI" chưa bật.

### Bước 3. Tạo bộ và lấy keyword (mục 2)

1. **Kiểm ASIN đối thủ.**
   - Tool lấy sẵn từ cột `ASIN đối thủ (>=3)` trên Lark. ASIN bị trùng sẽ tự bỏ.
   - **Cần tối thiểu 3 ASIN.** Thiếu thì bổ sung trên Lark rồi Tải lại, hoặc bấm **Thêm ASIN** để thêm tạm trong tool.
   - Bỏ ASIN không đúng sản phẩm, vì ASIN sai kéo theo biến thể sai.
2. **Niche và product.**
   - Ô **Niche** đặt tên bộ, lấy theo kết luận ảnh ở bước 2 nếu khác Lark.
   - Ô **Product** để `ornament` cho hàng ornament.
   - Tên bộ có dạng `<Mã> - <niche> <product>`, ví dụ `BSV051 - hiking ornament`.
3. Bấm **Tạo bộ & lấy keyword**. Mỗi ASIN thành một job trong hàng đợi.
   - ASIN đã lấy ở bộ khác thì được **dùng lại** ngay, không tốn lượt H10. Bảng ASIN ghi "H10 · dùng lại".
   - ASIN đang chờ ở bộ khác thì chạy chung một lần. Xong là điền cho mọi bộ cần ASIN đó.
4. Theo dõi bảng trạng thái từng ASIN:

| Trạng thái | Ý nghĩa | Làm gì |
|---|---|---|
| Chưa lấy | Chưa xếp hàng | Bấm **Lấy** |
| Chờ extension / Đang lấy | Đang trong hàng đợi / máy đang chạy | Đợi. Muốn rút ra thì **Huỷ chờ** |
| Xong | Đã có keyword. Cột Kỳ dữ liệu ghi 12/2025 hay Kỳ hiện tại | — |
| Không có dữ liệu | Cerebro không trả keyword nào | Xem lại ASIN có đúng không |
| Lỗi | Lấy 2 lần đều hỏng (xem cột Cảnh báo) | Bấm **Lấy lại**, hoặc **Tải file tay** |

- **Kỳ hiện tại** nghĩa là ASIN không có keyword ở 12/2025 (sản phẩm mới), nên tool lấy kỳ hiện tại và không lọc
  SV/rank. Nếu các ASIN lấy ở hai kỳ khác nhau, trang bộ keyword có dòng cảnh báo: SV hai kỳ không cùng mùa.
- **Tải file tay:** khi extension không lấy được, tự export Cerebro (xlsx/csv) của đúng ASIN đó rồi nạp vào.
- **Lấy lại** tốn thêm lượt H10. Chỉ bấm khi thật cần.

Một mã đã có bộ thì nút chính đổi thành **Lưu & lấy keyword còn thiếu**: chỉ lấy các ASIN chưa có, không chạy lại
ASIN đã xong.

### Bước 4. Ghi link về Lark

Khi đã có ít nhất một ASIN xong, bấm **Ghi link vào Lark** và xác nhận. Link bộ keyword được ghi vào cột
`Link bộ Keyword` của mã trên Lark. Chỉ ghi khi đã chắc bộ đúng mã và đúng ASIN.

### Bước 5. Soát biến thể trên trang bộ keyword

Bấm **Bộ keyword** (hoặc mở link trên Lark). Trang có 4 tab:

| Tab | Dùng để |
|---|---|
| **Chọn cho sản phẩm** | Tab chính để soát. Hàng tab con Product · Function · Gift · Personalized · Occasion · Tổng hợp |
| **So sánh ASIN** | Rank tốt nhất của mỗi biến thể ở từng ASIN, đặt cạnh nhau |
| **Từng ASIN** | Biến thể của riêng một ASIN đối thủ |
| **Tất cả keyword** | Mọi keyword sau gộp: lọc, sắp xếp, xem và khôi phục keyword đã xoá |

**Thứ tự soát nên làm:**

1. Mở tab **Tổng hợp** để thấy số biến thể của từng loại × nhóm.
2. Soát **Product** trước, vì đây là keyword có "ornament", sát sản phẩm nhất. Sau đó soát Gift, Function,
   Personalized, Occasion.
3. Trong mỗi loại, đi từ **Nhóm 1 → Nhóm 2 → Nhóm 3 → Cần xem xét**. Đối chiếu từng biến thể với ảnh sản phẩm:
   - **Đúng sản phẩm:** giữ nguyên.
   - **Không hợp** (thương hiệu, chủ đề khác, tên phim, gõ sai, chữ thừa): bấm **Loại**. Biến thể chuyển xuống mục
     Loại, không vào "Sao chép tất cả" và file Excel ghi nhãn Không hợp. Bấm **Đưa lại** để bỏ nhãn.
   - **Biến thể đúng nhưng có vài keyword sai:** mở khối, tích các keyword sai, bấm **Xoá khỏi bộ** ở thanh dưới.
     Keyword biến mất ngay, khối vẫn mở. Bấm **Hoàn tác** trên thông báo để lấy lại.
4. Soát khối **Khác** của Function. Ở đây hay có keyword SV lớn không chứa ornament/gift, ví dụ `hiking`,
   `stocking stuffers for hikers`.
5. Mở khối **Loại bỏ (negative)** xem nhanh. Nếu negative bắt nhầm keyword tốt thì báo người quản lý để sửa
   negative cho mã đó.

**Đọc cột sóng mức sát** (5 vạch, xanh lá = sát, đỏ = không hợp): tool tính từ số ASIN đối thủ dùng biến thể và
rank tốt nhất, **không xét nghĩa**. Mức sát cao vẫn có thể sai sản phẩm, nên luôn đối chiếu với ảnh.

**Gợi ý chọn:**
- Ưu tiên Nhóm 1, rồi Nhóm 2, mức sát 4–5.
- Nhóm 3 và Cần xem xét chỉ dùng khi đã xem là đúng sản phẩm.
- Không dùng mục Loại.

Các lỗi hay gặp cần Loại hoặc xoá: xem phần "Hạn chế đã biết" trong [CACH-PHAN-LOAI.md](CACH-PHAN-LOAI.md).

Nhãn Loại và keyword đã xoá được lưu trên server, ai mở bộ cũng thấy như nhau.

### Bước 6. Lấy keyword ra dùng

| Cách | Lấy gì |
|---|---|
| **Sao chép** ở từng khối biến thể | Keyword của khối đó |
| **Sao chép tất cả** | Keyword Nhóm 1–3 của tab đang xem. Không lấy Cần xem xét, không lấy biến thể bị Loại |
| Tích keyword rồi bấm **Sao chép** ở thanh dưới | Đúng các keyword đã tích |
| **Tải Excel final** | Sheet Tổng hợp, mỗi loại một sheet (Product · Function · Gift · Personalized · Occasion), Tất cả keyword, Ghi chú. Mỗi dòng có Mục, Nhóm, Biến thể, Mức sát, Nhãn tay |
| **Tải CSV thô** | Keyword sau gộp, chưa chia biến thể |

- Mọi nút sao chép chép mỗi dòng dạng **`keyword<tab>search volume`**. Dán vào Excel hoặc Google Sheet sẽ tự tách
  thành 2 cột. Tên biến thể không được chép theo.
- Excel final và bản chữ cho agent đều lấy theo trạng thái hiện tại: đã trừ keyword bị xoá, có ghi nhãn Loại.
  Vì vậy hãy soát xong bước 5 rồi mới tải.

---

## Phần C. Làm hàng loạt nhiều mã

1. Ở trang chính, lọc **Đủ ≥ 3 ASIN, chưa lấy keyword**. Bộ lọc này gồm hai loại mã:
   - mã chưa tạo bộ;
   - mã đã tạo bộ nhưng mọi ASIN đều lỗi hoặc chưa lấy.
2. Tạo bộ cho từng mã như bước 3. Muốn tạo cả loạt một lần thì nhờ người quản lý tool chạy, vì việc này tốn lượt
   H10 dùng chung.
3. Theo dõi ở trang **Hàng đợi**:
   - **Bộ đang chờ:** xếp theo thứ tự chạy, có lọc theo nhóm mã. Tích nhiều bộ rồi bấm **Bỏ khỏi hàng đợi** để rút
     ra; ASIN đang lấy dở sẽ chạy nốt.
   - **Máy đang chạy:** máy nào online, H10 đăng nhập chưa, đang nhận job hay không, đang lấy ASIN nào.
   - **Dừng tool:** mọi máy ngừng nhận job, hàng đợi giữ nguyên. Bấm lại để chạy tiếp.
4. Tool ước khoảng 0,7 phút một lượt (xem số lượt còn lại ở trang Hàng đợi). Một ASIN dùng chung cho nhiều mã chỉ tốn một lượt.

**Mã bị trùng trên Lark:** một mã nằm ở hai dòng Lark thì chỉ có một bộ keyword dùng chung. Hai dòng có ASIN khác
nhau thì cần người chốt giữ dòng nào và xoá dòng thừa trên Lark.

---

## Phần D. Xử lý sự cố

| Gặp | Nguyên nhân thường gặp | Làm gì |
|---|---|---|
| Hàng đợi không chạy, mọi máy "không nhận job" | Tool đang **Dừng**, hoặc các máy đã tự tắt Nhận job vì hết tài khoản H10 dùng được | Trang Hàng đợi: bỏ Dừng tool. Trên từng máy: bật lại **Nhận job** |
| Máy báo "H10 chưa đăng nhập" | Phiên Helium 10 hết hạn | Đăng nhập lại H10 trên Chrome máy đó. Job đang dở tự trả về hàng, không mất lượt |
| ASIN "Lỗi: Hết giờ chờ ô nhập ASIN / ô Time Period" | Trang H10 chậm, hiện popup, hoặc tài khoản chỉ có bản demo | Bấm **Lấy lại**. Lỗi lặp trên cùng một máy thì cài extension bản mới nhất |
| "Hết lượt Cerebro" | Tài khoản H10 hết lượt trong ngày | Extension tự chuyển tài khoản khác (bản 0.1.9). Hết cả thì job trả về hàng cho máy khác |
| Biến thể toàn chủ đề lạ | ASIN đối thủ không đúng sản phẩm | Sửa ASIN trên Lark → Tải lại → Lưu & lấy keyword còn thiếu |
| Không thấy mã mới | Danh sách Lark cũ | Bấm **Tải lại từ Lark** |
| H10 đổi giao diện, extension lỗi hàng loạt | Bộ lấy không còn khớp trang | Bật **Soi Cerebro** trong popup, làm tay một lượt Cerebro, rồi báo người quản lý tool sửa extension |

## Những điều không làm

- Không bấm **Lấy lại** hàng loạt khi chưa rõ lỗi, vì mỗi lần tốn lượt H10 dùng chung.
- Không **Ghi link vào Lark** khi bộ chưa đúng mã hoặc chưa đúng ASIN.
- Không xoá keyword chỉ vì SV thấp. Xoá là để bỏ keyword **sai sản phẩm**. Biến thể sai thì bấm Loại.
- Không chia sẻ Agent token ra ngoài nhóm.
