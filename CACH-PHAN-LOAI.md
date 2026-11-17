# Tool phân loại biến thể và gom nhóm keyword như thế nào

File này giải thích bằng lời thường cách KW Biến Thể biến keyword Cerebro của các ASIN đối thủ thành
bảng biến thể (Product · Function · Gift · Personalized · Occasion, Nhóm 1/2/3, mức sát). Luật lấy đúng
theo code đang chạy (`engine.py`). Đổi luật trong code thì phải sửa file này cho khớp.

Ví dụ trong file lấy từ bộ thật **BSV051 - hiking ornament** (4 ASIN đối thủ, 808 keyword sau gộp).

Tóm tắt 6 bước:

1. Gộp keyword của các ASIN, lọc theo SV và rank.
2. Xếp mỗi keyword vào **một loại**: Personalized → Product → Function → Gift → Occasion.
3. Gạt keyword dính **negative** ra khối riêng.
4. **Rút biến thể** từ chính keyword của từng ASIN: bỏ từ gốc và chữ chung, phần còn lại là biến thể.
5. **Gom** mỗi keyword vào đúng một biến thể, theo thứ tự ưu tiên.
6. Chia **Nhóm 1/2/3** theo số ASIN có biến thể, đánh **mức sát**, rank tốt nhất > 50 thì vào **Cần xem xét**.

---

## Bước 1. Gộp và lọc keyword

- Mỗi ASIN đối thủ có một file Cerebro riêng: kỳ **12/2025**, Exclude variations.
- **Gộp:** cùng một keyword xuất hiện ở nhiều ASIN thì giữ một dòng, lấy dòng có **organic rank tốt nhất**.
  Hoà rank thì lấy dòng có SV cao hơn. Cột "Số ASIN có" cho biết keyword đó có ở mấy ASIN.
- **Lọc:** chỉ giữ keyword có **SV ≥ 50** và **organic rank 1–100**. Keyword ngoài bộ lọc không vào biến thể,
  chỉ nằm ở sheet "Tất cả keyword" của file Excel với mục "Ngoài bộ lọc".
- **Ngoại lệ sản phẩm mới:** ASIN không có keyword nào ở kỳ 12/2025 thì tool lấy kỳ hiện tại. Keyword của ASIN
  đó **không bị lọc** SV và rank.
- Keyword người dùng đã bấm **Xoá khỏi bộ** bị bỏ ngay từ đầu, không vào bước nào phía sau.

Trước khi so từ, tool tách keyword thành từng chữ thường (`U.S.` thành `us`). Tool cũng đưa số nhiều về số ít khi
dạng số ít có trong dữ liệu, ví dụ `hikers` thành `hiker`. Hai loại từ không bao giờ bị bỏ chữ "s":
- chữ chung (`christmas`, `xmas`…);
- từ dịp lễ.

## Bước 2. Xếp keyword vào loại

Mỗi keyword chỉ thuộc **một** loại. Tool xét lần lượt, gặp điều kiện nào đúng trước thì dừng:

| Thứ tự | Điều kiện | Loại | Ví dụ (BSV051) |
|---|---|---|---|
| 1 | Có từ cá nhân hoá: personalized, personalize, personalised, personalise, personalization, custom, customized, customize, customizable… | **Personalized** | `personalized hiking ornament` |
| 2 | Có `ornament` (kể cả ornaments) | **Product** | `hiking ornament`, `national park christmas ornaments` |
| 3 | Có decor, decors, decoration, decorations, decorative, decorating, decorate | **Function** | `hiking decor`, `mountain christmas decor` |
| 4 | Có `gift` (gifts…) | **Gift** | `hiking gifts for women` |
| 5 | Có từ dịp lễ (bảng dưới) | **Occasion** | `mountain christmas` |
| 6 | Không có từ nào ở trên | Khối **Khác** của Function | `hiking`, `stocking stuffers for hikers`, `hiking presents` |

Từ dịp lễ gồm christmas, xmas, navidad, santa, holiday, halloween, easter, thanksgiving, valentine, mother's day,
mothers day, father's day, fathers day, new year, st patrick.

Hệ quả của thứ tự xét:
- `personalized hiking gift` vào Personalized, không vào Gift.
- `hiking ornament gift` vào Product, vì có ornament.
- `christmas hiking decorations` vào Function, không vào Occasion.
- `presents` và `stocking stuffers` **không** được tính là gift, nên keyword chỉ có các từ này rơi vào Khác.

## Bước 3. Negative

Keyword dính negative **không bị xoá**. Keyword đó vẫn ở trong loại của mình nhưng nằm trong khối riêng
**"Loại bỏ (negative)"**, không vào biến thể nào, và không được dùng để rút biến thể.

Negative mặc định ở `cau-hinh/neg-mac-dinh.json`:

| Nhóm | Ví dụ |
|---|---|
| Negative B mặc định | hallmark, set, basket, ceramic, unique, 3d, bulk |
| Vật thể khác | topper, stocking, lights, lamp, garland, centerpiece, tumbler, pillow, rug… (138 từ) |
| Vật thể khác, **chỉ khi không có ornament** | card, shirt, hat, bag, stuffed animal, charm, flag, puzzle, calendar, book… |
| Tiếng Tây Ban Nha | navidad, navideno, adorno, arbol, decoracion, regalo… |
| Thương hiệu / IP | hallmark, bronner's, kurt adler, lenox, swarovski, disney, marvel, harry potter… |
| **Năm cũ** (tự động) | keyword có năm khác năm mục tiêu, vd `hiking ornament 2025` khi năm mục tiêu là 2026 |

- Ví dụ: `outdoor christmas stockings` dính "stocking", nên vào khối negative của Occasion. Riêng
  `stocking stuffer` không bị tính là stocking.
- Từ cá nhân hoá (personalized, custom) **không còn là negative** nữa, kể cả khi file cấu hình cũ vẫn ghi.
- Mã nào cần negative riêng, nhãn ban đầu hay năm mục tiêu khác thì thêm file `cau-hinh/<Mã nội bộ>.json`
  (ví dụ có sẵn: `BSV627.json`). Không có file riêng thì năm mục tiêu là năm hiện tại.

## Bước 4. Rút biến thể

Biến thể **không có danh sách soạn sẵn**. Tool rút biến thể từ chính keyword của đối thủ, theo từng loại và
**từng ASIN riêng**:

1. Lấy keyword của loại đó, của một ASIN, rank 1–100, không dính negative. Đọc từ rank tốt nhất trở đi.
2. Bỏ **từ gốc** của loại:
   - Product: ornament.
   - Function: các từ decor.
   - Gift: gift.
   - Personalized: ornament, gift và các từ cá nhân hoá.
3. Bỏ **chữ chung**: christmas, xmas, tree, holiday, decoration(s), gift(s), present(s), idea(s), for, the, a, an,
   of, and, with, to, on, in, my, your, is, as, at, from, by, women, woman, men, man, her, him, adult(s).
   Bỏ luôn số năm (2025, 2026…).
4. **Phần chữ còn lại, giữ nguyên thứ tự, là tên biến thể.** Mỗi tên chỉ ghi một lần.

| Keyword của đối thủ | Bỏ đi | Biến thể |
|---|---|---|
| `hiking christmas ornament` | christmas, ornament | **hiking** |
| `national park ornaments 2026` | ornament, 2026 | **national park** |
| `rocky mountain national park ornament` | ornament | **rocky mountain national park** |
| `hiking decor` (Function) | decor | **hiking** |

### Gift chia theo đối tượng trước

Với Gift, nếu phần còn lại có **từ chỉ người nhận** thì biến thể là **đối tượng**, không phải chủ đề:

- Từ người nhận gồm: women, men, her, him, mom, dad, grandma, wife, husband, boyfriend, girlfriend, couple,
  daughter, son, sister, brother, kids, boy, girl, baby, friend, coworker, boss, teacher, nurse, family…
  (`engine.DOI_TUONG`).
- Đuôi lover, owner, fan, rider, enthusiast, mom, dad, girl, boy thì **giữ cả chữ đứng trước**:
  `horse lover`, `dog mom`, `hiking enthusiast`.

| Keyword | Biến thể Gift |
|---|---|
| `hiking gifts for women` | **women** (đối tượng) |
| `gifts for hiking lovers` | **hiking lover** (đối tượng) |
| `nature lover gifts for men` | **nature lover men** (đối tượng) |
| `hiker gifts` | **hiker** (chủ đề) |

Trên trang và trong file Excel, biến thể đối tượng có chữ "(đối tượng)" hoặc cột Đối tượng.

### Function "Khác" và Occasion không rút biến thể

- **Occasion**: mỗi từ dịp lễ là một khối, ví dụ khối `christmas` gồm `mountain christmas`…
- **Khác** của Function: để nguyên một khối, không chia. Đây là chỗ cần người soát, vì hay có keyword tốt như
  `hiking` (SV 32.200), `hiker` hoặc `stocking stuffers for hikers`.

## Bước 5. Gom keyword vào biến thể

Một keyword có thể khớp nhiều biến thể. Ví dụ `rocky mountain national park ornament` khớp cả
`rocky mountain national park`, `national park` và `mountain`. Keyword chỉ được vào **một** biến thể. Tool thử
biến thể theo thứ tự dưới đây và gán vào **biến thể đầu tiên khớp**:

1. Biến thể **đối tượng** (chỉ có ở Gift).
2. Biến thể **nhiều từ**, nhiều từ hơn trước: 4 từ, rồi 3 từ, rồi 2 từ.
3. Biến thể **1 từ cụ thể** (`hiking`, `mountain`, `colorado`).
4. Biến thể **1 từ rộng**: funny, fun, cute, new, first, unique, cool, best, beautiful, pretty, small, large, big,
   mini, vintage, cheap.

Cùng bậc thì xét Nhóm 1 trước Nhóm 3, rồi đến rank tốt hơn. Vì vậy `dallas cowboys ornament` vào `dallas cowboy`,
không vào `cowboy`.

**Thế nào là "khớp":** mọi chữ của biến thể đều có trong keyword, đứng ở đâu cũng được.
- Chữ dài hơn 3 ký tự khớp cả dạng có đuôi (s, er, ing, ist…). Ví dụ biến thể `golf` khớp `golfer`, `golfing`.
- Chữ ngắn (`us`, `uk`, `rv`) chỉ khớp đúng nó hoặc thêm "s". Vì vậy `us` không khớp `used`.

Keyword đúng loại mà không khớp biến thể nào thì vào khối **"Chưa vào biến thể"**.

## Bước 6. Nhóm, Cần xem xét, mức sát

Với mỗi biến thể, tool đếm biến thể đó **có ở bao nhiêu ASIN**: ASIN có ít nhất một keyword rút ra được biến thể
này, trong rank 1–100. Tool cũng lấy **rank tốt nhất**: rank nhỏ nhất của keyword đó trong các ASIN.

| Số ASIN có biến thể | Nhóm |
|---|---|
| ≥ 3 ASIN | **Nhóm 1** |
| 2 ASIN | **Nhóm 2** |
| 1 ASIN | **Nhóm 3** |

- Rank tốt nhất **> 50** (ngoài trang 1) thì biến thể chuyển sang mục **Cần xem xét**, nhưng vẫn ghi nó thuộc
  Nhóm mấy. Ví dụ `yosemite`: có ở 3/4 ASIN nhưng rank tốt nhất là 53, nên vào Cần xem xét (Nhóm 1).
- Occasion tính tương tự: số ASIN có keyword của khối, và rank tốt nhất của khối.

**Mức sát** (cột sóng 5 vạch trên trang) tự tính từ số ASIN và rank tốt nhất:

| Số ASIN có | rank ≤ 20 | 21–50 | 51–75 | 76–100 |
|---|---|---|---|---|
| ≥ 3 ASIN | 5 Sát | 4 Khá sát | 2 Xa | 1 Không hợp |
| 2 ASIN | 4 Khá sát | 3 Trung bình | 2 Xa | 1 Không hợp |
| 1 ASIN | 3 Trung bình | 3 Trung bình | 1 Không hợp | 1 Không hợp |

Ví dụ ở BSV051:
- `hiking`: 4/4 ASIN, rank 1, nên 5 Sát.
- `camping`: 3/4 ASIN, rank 21, nên 4 Khá sát.
- `tent`: 2/4 ASIN, rank 28, nên 3 Trung bình.
- `alaska`: 2/4 ASIN, rank 80, nên 1 Không hợp.

**Mức sát chỉ đo mức đối thủ dùng biến thể, không đo nghĩa.** Tool không biết biến thể có hợp với ảnh sản phẩm
hay không, nên người dùng phải tự bấm **Loại** (nhãn "Không hợp").

## Thứ tự hiển thị

- Loại: Product → Function → Gift → Personalized → Occasion. Thứ tự này là thứ tự **hiển thị**, khác thứ tự
  **xếp loại** ở bước 2.
- Trong mỗi loại: Nhóm 1 → Nhóm 2 → Nhóm 3 → Cần xem xét → Loại (bị loại tay) → Chưa vào biến thể / Khác /
  negative.
- Trong mỗi nhóm: biến thể có ở nhiều ASIN hơn đứng trước. Cùng số ASIN thì rank tốt nhất nhỏ hơn đứng trước,
  rồi đến tổng SV lớn hơn.
- Keyword trong mỗi khối xếp theo Search Volume giảm dần.

Tab **Từng ASIN** chạy đúng các bước trên cho riêng một ASIN. Tab **So sánh ASIN** đặt rank tốt nhất của mỗi
biến thể ở từng ASIN cạnh nhau.

## Người dùng chỉnh được gì

| Thao tác | Tác dụng |
|---|---|
| **Loại** biến thể (nhãn Không hợp) | Biến thể chuyển xuống mục "Loại", không vào "Sao chép tất cả". Keyword vẫn còn trong bộ. |
| **Xoá khỏi bộ** (tích keyword) | Keyword bị bỏ khỏi mọi bước, nên biến thể có thể đổi số ASIN và nhóm. Khôi phục được. |
| File `cau-hinh/<Mã>.json` | Negative riêng, nhãn ban đầu, năm mục tiêu cho mã đó |

## Hạn chế đã biết (cần người soát)

Tool không hiểu nghĩa, nên các trường hợp sau phải người xem và Loại hoặc xoá:

- **Gõ sai thành biến thể riêng:** `himing`, `hikinh`, `hiking gofts`.
- **Thương hiệu, tên riêng không liên quan:** `volkswagen`, `mountain dew`, `walle`, `harvey lewis`.
- **Biến thể chỉ là chữ thừa hoặc số:** `41`, `10 hiking`, `hiker who have everything`, `someone who hike`.
- **Từ đồng nghĩa với gift không được nhận:** `presents`, `stocking stuffers`, `gadgets` nằm trong Khác chứ không
  vào Gift.
- **Nhóm 3 dễ là nhiễu:** chỉ 1 ASIN có biến thể, dễ là chủ đề riêng của đối thủ đó (`oregon trail`, `utah`).
- **Mức sát cao vẫn có thể sai sản phẩm:** ví dụ `adventure time` (tên phim hoạt hình) có 2 ASIN, rank 17, nên
  mức 4.

Gợi ý chọn: dùng Nhóm 1 rồi đến Nhóm 2, mức sát 4–5. Chỉ dùng Cần xem xét và Nhóm 3 sau khi đã xem đúng với ảnh
sản phẩm. Soát khối **Khác** của Function vì hay có keyword SV lớn.
