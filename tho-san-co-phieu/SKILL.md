---
name: tho-san-co-phieu
description: >-
  Use when the user asks to hunt for stock or equity trades on Binance futures — "săn cổ phiếu", "thợ săn cổ phiếu", "săn kèo cổ phiếu", "săn chứng khoán", "tìm lệnh cổ phiếu", "hunt stocks" — or wants a manual LONG/SHORT scan of Binance USDⓈ-M stock perpetuals (US, Korea, Hong Kong, China, ADR, pre-IPO) rather than crypto.
---

# Thợ săn Cổ phiếu (Binance TradFi Futures)

## Tổng quan
Tự săn hợp đồng vĩnh cửu cổ phiếu (`TRADIFI_PERPETUAL`) trên Binance USDⓈ-M, tự phân tích, báo cáo tiếng Việt. **Chỉ phân tích, không đặt lệnh.** Mọi con số (giá, ATR, vị thế phái sinh, định giá và tăng trưởng từ TradingView + SEC EDGAR, lịch KQKD) lấy từ [`hunt_stock_data.py`](./scripts/hunt_stock_data.py) ngay lúc báo cáo; mọi tin có ngày và nguồn; không có lệnh hạng A thì nói thẳng. Báo cáo xong gửi bản rút gọn lên Telegram.

- Danh sách mã do script tự lấy từ `exchangeInfo` của Binance, không liệt kê tay.
- Cột `mkt` theo `underlyingType` của Binance: `US`, `ADR` (niêm yết ở Mỹ, giao dịch giờ Mỹ, vd. `TSM`, `SKHY`), `KR`, `HK` (gồm H-share của doanh nghiệp đại lục, vd. `ZHONGJI`, `GIGADEV`), `CN` (A-share), `PRE` (chưa niêm yết, không có BCTC).
- ETF/ETP đòn bẩy bị loại khỏi `scan`; `--include-etfs` chỉ để xem, `plan` luôn FAIL ETF.
- Người dùng đặt lệnh trên **OKX**. Dữ liệu phân tích vẫn lấy từ Binance, nhưng `scan`, `detail`, `plan` và `stops` chỉ nhận mã OKX cũng niêm yết: cùng tên, loại cổ phiếu, giá lệch ≤ 1%; riêng `scan` còn cần volume OKX 24h ≥ 0,5 triệu USD (`--okx-min-qv`). Bị loại: mã chỉ có trên Binance (Tencent, Meituan, BYD, BABA, ANET, UBER…) và pre-IPO OPENAI, ANTHROPIC (hai sàn định nghĩa hợp đồng khác nhau, giá lệch khoảng 90%).

## Khung rủi ro (mặc định; dùng số người dùng nói nếu khác)
| Tham số | Giá trị |
|---|---|
| Đòn bẩy | x5 mặc định. Mã có cờ `OKxN` (ATR quá rộng cho x5) thì chạy `stops` / `plan` với `--leverage N`; dòng `TG:` Size sẽ ghi `(xN)` để người đặt lệnh dùng đúng đòn bẩy. Rủi ro vẫn 1% vốn, vì size tính theo khoảng cách stop. Đòn bẩy thấp chỉ tốn thêm ký quỹ, nhưng mã biến động mạnh dễ gap qua stop hơn: ghi vào **Phản biện**. Người dùng nói số khác thì truyền `--leverage` |
| Vốn | 1000 USDT (`--capital`) |
| Rủi ro mỗi lệnh | 1% vốn |
| Ký quỹ tối đa mỗi lệnh | 20% vốn |
| Độ lệch mark–index | ≤ 0,5% (vượt thì cờ `INDEX`, đứng ngoài) |
| Stop | ≥ 1 ATR14 ngày, ≤ `(1/đòn bẩy − mmr)/2` (8,75% ở x5) và cách mọi đỉnh/đáy ngày ≥ 0,25 ATR (`plan` tự kiểm: sát swing 120 phiên hoặc đỉnh/đáy 2 phiên gần nhất thì `FAIL`; sát đỉnh/đáy bất kỳ trong 20 phiên thì `WARN` và hạ trần hạng). ATR và mọi chỉ báo ngày/4h chỉ tính nến T2–T6, vì cuối tuần sàn cơ sở đóng và giá gần như đứng |
| R:R gộp | ≥ 1,5 (`plan` in thêm `net R:R` sau phí taker 2 chiều 0,10%) |
| Chốt lời | Lãi tới +1R thì chốt một nửa, dời stop phần còn lại về giá vào. Dòng `TG:` thứ hai có `Chốt 1/2: <giá>` để người dùng đặt sẵn lệnh chốt một nửa trên OKX; `orders` chấm điểm theo luật này (giá quay về giá vào sau khi chốt = +0,5R). Lý do: 30/10–20/11, 3/9 lệnh khớp từng lãi tới +1R, hai trong số đó quay về stop, và chưa lệnh nào chạm TP |
| Vào ngay | entry trong ±0,5% giá mark; xa hơn là lệnh chờ (`limit` nếu chờ hồi, `stop` nếu đánh phá vỡ) |
| KQKD | Không giữ lệnh qua ngày KQKD: `plan` FAIL nếu KQKD rơi vào `--horizon-days` (mặc định 20). Muốn vào trước KQKD thì rút `--horizon-days` để đóng trước ngày đó và ghi vào **Sai nếu**; không thì bỏ lệnh. Ngày đã xác nhận bằng tin thì truyền `--earnings-date YYYY-MM-DD`; nó thay ngày của script |
| Xu hướng thị trường | `plan` FAIL lệnh LONG khi QQQ (mã `KR`: EWY) đóng cửa ngày gần nhất dưới EMA20, FAIL lệnh SHORT khi trên EMA20. Dòng `Xu hướng` của `scan` cho biết chiều nào được dựng. Lý do: 30/10–20/11 QQQ đóng dưới EMA20 mọi phiên, và cả 7 lệnh LONG khớp đều chạm stop |
| Tầm nhìn | ≤ 20 ngày (`--horizon-days`, lưu vào sổ). Hết hạn giữ mà lệnh chưa đóng thì `orders` đóng nó ở giá đóng cửa cuối cùng trong hạn (`hết N ngày`); người dùng đóng lệnh thật lúc đó. Tối đa 3 lệnh mở cùng lúc (lệnh chờ khớp cộng lệnh đã khớp đang chạy), tối đa 2 lệnh cùng chiều, không có 2 lệnh cùng mã cùng chiều. `plan --log` từ chối lệnh vượt các mức này |
| Hạng | `plan` in `Hạng tối đa`. Là B khi stop dính `WARN`, khi lệnh chờ có 24 giờ hiệu lực trùm một sự kiện vĩ mô Mỹ (CPI, PPI, việc làm, FOMC; lịch nằm ở `macro_events.json`, gốc repo skills), hoặc khi entry chờ cách mark hơn 1 ATR. Báo cáo được hạ hạng, **không được nâng** |

## Quy trình
`hunt_stock_data.py` dưới đây là `python3 ~/.gemini/config/skills/tho-san-co-phieu/scripts/hunt_stock_data.py`.

1. **Quét:** `hunt_stock_data.py scan [--market all|us|kr|hk|cn|adr|pre]`. Lệnh mất khoảng 1 phút và quét mọi hợp đồng có thanh khoản từ 1 triệu USD/24h (khoảng 120 mã). Đừng tự thêm `--top 40`: cắt ở 40 mã sẽ chỉ còn nhóm công nghệ.
   - Dòng `Xu hướng` (ngay sau dòng tóm tắt): QQQ cho mọi mã trừ `KR`, EWY cho mã `KR`. `chỉ SHORT` nghĩa là `plan` FAIL mọi lệnh LONG của nhóm đó, `chỉ LONG` thì ngược lại; chỉ dựng setup theo chiều được phép.
   - Săn mã cờ `OK` (đòn bẩy mặc định) và `OKxN` (dùng `--leverage N`).
   - Bỏ `ATR` (quá biến động kể cả ở x2, hoặc chưa đủ 15 phiên để tính ATR), `PUMP` (nhảy ≥ 20%/24h hoặc funding cực đoan) và `INDEX`.
   - Cột `sector` và dòng cuối `Tradeable by sector` cho biết mã giao dịch được thuộc những ngành nào.
   - Cột `earn`: `Xd!` là KQKD trong ≤ 7 ngày, `Xd` là còn X ngày, `-Xd` là vừa công bố X ngày trước. `7d`/`20d` tính theo phiên.
2. **Tin tức. REQUIRED SUB-SKILL:** agent-reach.
   - Chạy `hunt_stock_data.py news SYM1 SYM2 ...`: Google News RSS cho Phố Wall, châu Á, Fed/lợi suất, chip/thuế quan. Mã niêm yết ở Mỹ (`US`/`ADR`) lấy RSS Yahoo Finance theo mã, có link bài gốc (link Google News chỉ là link chuyển hướng); mã châu Á và `PRE` tìm qua Google News theo tên công ty.
   - Mã nộp hồ sơ SEC có thêm mục `SEC 8-K/6-K 30 ngày`: dòng có `!` (KQKD, đổi lãnh đạo, hợp đồng lớn, M&A, nợ mới, suy giảm tài sản, hủy niêm yết, phá sản…) là chất xúc tác: mở link SEC đọc trước khi dựng setup. Dòng `6-K ?` (công ty nước ngoài, 6-K không có mã mục) cũng mở xem. Mục ghi `SEC không trả lời` thì mở EDGAR bằng WebFetch.
   - Đọc [references/bay-co-phieu.md](references/bay-co-phieu.md) trước khi viết phần cơ bản và đặt lệnh chờ: bẫy BCTC (Exhibit 99.1, cột GP/Op), hồ sơ SEC, giờ giao dịch và lệnh cuối tuần.
   - Bổ sung: `agent-reach doctor --text` trước, rồi `agent-reach web search "..." --limit 5` **tuần tự, cách nhau khoảng 15 giây**; đọc bài chính bằng `agent-reach web read <url>`. agent-reach lỗi thì dùng web search có sẵn của runtime (`WebSearch` trên Claude Code, `search_web` trên Gemini).
   - Phải đủ bốn nhóm, mỗi tin có ngày (bỏ tin không ngày):
     - vĩ mô Mỹ và châu Á 48 giờ qua: S&P 500, Nasdaq, KOSPI, Hang Seng, lợi suất 10 năm Mỹ, Fed/FOMC, thuế quan, kiểm soát xuất khẩu chip
     - ngày KQKD của từng mã trong shortlist. Ngày từ script có thể là ước tính (nguồn SEC là 8-K KQKD gần nhất + 91 ngày), nên xác nhận bằng tin. Ngày xác nhận khác, hoặc `plan` báo `chưa rõ ngày KQKD`, thì chạy lại `plan` với `--earnings-date YYYY-MM-DD`
     - chất xúc tác từng mã: KQKD vừa công bố (beat/miss, guidance), đơn hàng HBM/AI, sản phẩm mới, M&A, pháp lý
     - giờ sàn cơ sở (giờ VN): Mỹ/ADR 20:30–03:00 khi Mỹ theo giờ mùa hè (Chủ nhật thứ hai tháng 3 đến Chủ nhật đầu tiên tháng 11), còn lại 21:30–04:00; Hàn 07:00–13:30; Hồng Kông 08:30–11:00 và 12:00–15:00; A-share 08:30–10:30 và 12:00–14:00. Ngoài giờ sàn cơ sở thanh khoản mỏng, dễ gap khi mở phiên
3. **Soi kỹ 3–6 mã, trải ra nhiều ngành.**
   - Tối đa 3 mã cùng một ngành (cột `sector`).
   - Nếu dòng `Tradeable by sector` có mã ngoài bán dẫn/AI (Electronic Technology, Technology Services), phải soi ít nhất 1–2 mã ngoài nhóm đó, chọn mã có xu hướng hoặc chất xúc tác rõ nhất. Tin tức xoay quanh chip không phải lý do để chỉ soi chip.
   - Lệnh: `hunt_stock_data.py detail SYM1 SYM2 ...` (mức giá theo ATR, vị thế nhỏ lẻ và top trader, định giá và tăng trưởng quy USD, bảng quý SEC nếu công ty nộp 10-Q, nến hôm nay, nến 4h).
   - Dòng `OKX <hợp đồng>`: giá OKX so với Binance, volume 24h trên OKX, 1 hợp đồng bằng bao nhiêu cổ phiếu, đòn bẩy tối đa.
   - Dòng `OKX crowd 100d`: OI, L/S nhỏ lẻ, top trader và taker của riêng OKX trong 100 ngày (`pct100` là phân vị 100 ngày), cùng funding OKX, tức khoản người dùng thực trả. Ngày OKX bắt đầu lúc 16:00 UTC, nên dòng mới nhất là ngày đang chạy.
4. **Dựng setup theo chiều dòng `Xu hướng` cho phép:** khi được LONG, ưu tiên cổ phiếu tăng trưởng doanh thu/EPS mạnh, hưởng lợi chu kỳ ngành của chính nó (bán dẫn/AI, phần mềm, y tế, tiêu dùng, tài chính, công nghiệp, năng lượng…) đang hồi về hỗ trợ/EMA; khi được SHORT, ưu tiên cổ phiếu suy giảm cơ bản, định giá quá cao, hoặc nhỏ lẻ fomo quá nóng khi gãy cấu trúc. Stop đặt ở mức luận điểm sai **và** vượt qua đỉnh/đáy swing gần đó; target ở mức cấu trúc (hỗ trợ, kháng cự, EMA).
   - Dò stop bằng `hunt_stock_data.py stops LONG|SHORT SYM [--span 0.07] [--step 0.005]`, đừng viết script dò riêng. Lệnh này in, cho từng entry tính từ mark, mức stop chặt nhất mà `plan` cho qua. Mục tiêu 1,5R/2R đi kèm chỉ để tham chiếu. `WARN near` là đỉnh/đáy 20 phiên gần ngay sát stop.
5. **Kiểm từng lệnh ngay trước khi báo:** `hunt_stock_data.py plan LONG|SHORT SYM --stop X --target Y [--entry E] [--capital C] [--horizon-days N] [--earnings-date YYYY-MM-DD]`.
   - `FAIL` thì sửa mức hoặc bỏ lệnh.
   - `plan` và `stops` từ chối mã không đặt được trên OKX (`không đặt được trên OKX`): bỏ mã đó.
   - Dòng Size tính theo **số hợp đồng OKX**, ví dụ `0.81 hợp đồng NVDA-USDT-SWAP (0.81 NVDA ≈ 128.39 USDT)`; người dùng đặt đúng số hợp đồng này trên OKX. Gặp `FAIL size >= OKX minimum` hoặc `FAIL … OKX max leverage` thì đổi đòn bẩy hoặc bỏ lệnh.
   - Lệnh vào ngay khớp quanh mark, nên `plan` tính rủi ro từ giá xấu hơn giữa entry và mark.
   - `plan` làm tròn giá vào, stop và TP theo bước giá của OKX (có mã như LLY, SKHYNIX, ASML, MELI bước 0,1, trong khi Binance là 0,01). Giá vào được làm tròn về phía khớp xấu hơn, stop ra xa giá vào, TP lại gần giá vào. Vì vậy dòng `TG:` có thể khác vài bước giá so với số đã truyền vào; dán nguyên dòng đó.
   - `PASS` thì `plan` in `Hạng tối đa` và 4 dòng `TG:` (tiêu đề; Vào/Stop/TP/R:R/Chốt 1/2; Size/Ký quỹ/Rủi ro/Thanh lý; Cơ bản & KQKD). Báo cáo dán nguyên văn các dòng này (bỏ tiền tố `TG: `), kể cả `(tối đa hạng B)` ở dòng đầu. Không gõ lại con số nào. Độ lệch mark–index và dòng KQKD cũng chép từ output.
   - Lần `plan` cuối của mỗi lệnh đưa vào báo cáo phải thêm `--log`:
     - `LOG: #id`: lệnh mới.
     - `LOG: trùng #id`: lệnh cũ còn hiệu lực, báo cáo ghi "giữ #id".
     - `LOG: từ chối, sổ đã có 3 lệnh mở`: hủy lệnh chờ yếu nhất (`orders --cancel ID`) rồi chạy lại, hoặc đưa lệnh này vào **Đã loại** với lý do đủ 3 lệnh.
     - `LOG: từ chối, đã có #id <chiều> <MÃ> đang mở`: mỗi ý tưởng chỉ một lệnh, báo cáo ghi "giữ #id". Muốn đổi mức của lệnh còn chờ khớp thì `orders --cancel ID` rồi chạy lại.
     - `LOG: từ chối, sổ đã có 2 lệnh <chiều> mở`: hủy lệnh chờ yếu nhất cùng chiều rồi chạy lại, hoặc đưa lệnh này vào **Đã loại** với lý do đủ 2 lệnh cùng chiều.
6. **Lệnh cũ:** chạy `hunt_stock_data.py orders`. Nó đọc các lệnh tạo trong 30 ngày (`--days`) ở `~/.local/share/tho-san-co-phieu/orders.json` và tính trạng thái từ nến Binance. Không lấy lệnh cũ từ file báo cáo.
   - `CHỜ`: quyết định giữ, hủy (`orders --cancel ID`), hoặc thay (hủy trước, rồi `plan --log` lệnh mới).
   - `KHỚP … đang chạy … · chốt 1/2 ở <giá>`: lệnh đã khớp trên giấy, chưa tới +1R. Hỏi người dùng có vào thật không, nêu R hiện tại, giá chốt một nửa và mức đóng sớm. `orders --cancel` sẽ từ chối các lệnh đã khớp.
   - `chốt 1/2 ở +1R …, stop dời về <giá vào> · đang chạy`: nhắc người dùng chốt một nửa và dời stop về giá vào nếu chưa làm.
   - `chạm TP` / `chạm stop` / `về hòa vốn` / `hết N ngày`: lệnh đã đóng trên giấy, R ghi trong ngoặc.
   - `HẾT HẠN` / `ĐÃ HỦY`: bỏ qua.
   - Người dùng hỏi hiệu quả của thợ săn thì chạy `orders --stats`. Lệnh này chấm toàn bộ sổ: tỷ lệ khớp của lệnh chờ, số lệnh thắng/thua, tổng R, R đang chạy, và R tách theo chiều, hạng, thị trường.

## Báo cáo trên khung chat (tiếng Việt)
Báo cáo là đúng khung dưới đây: các mục này, theo thứ tự này. Chữ trong `<...>` là chỗ điền; mục không có gì thì ghi "Không có.". Bối cảnh tối đa 5 dòng, mỗi dòng có ngày. Hạng của mỗi lệnh không vượt `Hạng tối đa` mà `plan` in ra.

```markdown
**Kết luận:** <có / không có> lệnh hạng A; <n> lệnh vào ngay, <m> lệnh chờ (<thị trường: US, ADR, KR, HK, CN, PRE>), <k> lệnh cũ đang chạy trên giấy.

## Bối cảnh vĩ mô (Phố Wall và châu Á)
- <dd/mm>: <một ý> (<nguồn>)

## Lệnh vào ngay
### <dòng TG: đầu của plan, bỏ "TG: "> #<id sổ lệnh>
<dòng TG: thứ hai, nguyên văn, bỏ "TG: ">
<dòng TG: thứ ba, nguyên văn, bỏ "TG: ">
<dòng TG: thứ tư (Cơ bản & KQKD), nguyên văn, bỏ "TG: ">
- **Cơ bản & KQKD:** <...>
- **Kỹ thuật & Vị thế:** <...>
- **Phản biện:** <lý do của `Hạng tối đa: B` nếu có> <...>
- **Sai nếu:** <mức đóng sớm hoặc hủy>

## Lệnh chờ (hiệu lực 24 giờ)
<mỗi lệnh trình bày như trên; lệnh cũ còn giữ ghi "giữ #id" thay cho #id mới>

## Lệnh cũ (từ `orders`)
- #<id> <MÃ> <chiều>, <trạng thái của orders>: <giữ / hủy / thay bằng #id mới, hoặc cách quản lý nếu đã khớp>

## Đã loại
- <MÃ>: <lý do một câu: cơ bản, kỹ thuật, dính KQKD, hoặc cờ ATR / PUMP / INDEX>

## Quản lý rủi ro
- <tương quan với Nasdaq, S&P 500, KOSPI, Hang Seng; gap khi sàn cơ sở mở phiên; điều kiện đóng sớm>

## Nguồn
- <link bài báo và dữ liệu BCTC đã dùng>

_Phân tích tham khảo, không phải lời khuyên đầu tư._
```

## Gửi Telegram (mỗi lần săn — bản rút gọn 1 tin nhắn)
- Bản đầy đủ lưu vào `~/.local/share/tho-san-co-phieu/report-<YYYYmmdd-HHMM>.md` và hiển thị trong khung chat. Không lưu ở `/tmp`, vì WSL khởi động lại là mất.
- Bản gửi Telegram lưu riêng vào `~/.local/share/tho-san-co-phieu/tg-<YYYYmmdd-HHMM>.md` (**tối đa ~2500 ký tự, gọn trong 1 tin nhắn duy nhất (Telegram cắt ở 4096), không dùng bảng Markdown, không kèm danh sách link URL và danh sách mã đã loại**):
  - **Dòng đầu:** Kết luận ngắn (số lệnh vào ngay / lệnh chờ).
  - **Bối cảnh Vĩ mô:** tối đa 3 gạch đầu dòng, mỗi dòng 1 câu ngắn kèm ngày.
  - **Mỗi lệnh (vào ngay hoặc chờ):**
    - 4 dòng `TG:` của `plan`, nguyên văn, bỏ tiền tố `TG: `
    - `• Lý do: <1 câu ngắn>`
    - `• Sai nếu: <mức đóng sớm / hủy lệnh>`
  - **Lệnh cũ** (từ `orders`): mỗi lệnh 1 dòng: #id, giữ / hủy / thay, hoặc đã khớp và đang ở đâu.
  - **Quản trị rủi ro:** 1–2 dòng (tối đa mấy lệnh cùng lúc, rủi ro gap mở phiên / KQKD).
- Kiểm `wc -m ~/.local/share/tho-san-co-phieu/tg-<...>.md` ≤ 2500 rồi gửi bằng lệnh:
  `hermes send --to telegram --subject "📈 Thợ săn Cổ phiếu <dd/mm HH:MM>" --file ~/.local/share/tho-san-co-phieu/tg-<...>.md`
- Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục. Người dùng nói "không gửi" thì bỏ bước này.

## Lỗi thường gặp
| Lỗi | Cách đúng |
|---|---|
| Giữ lệnh qua ngày KQKD, chỉ gắn nhãn cảnh báo | `plan` FAIL thì rút `--horizon-days` để đóng trước KQKD, hoặc bỏ lệnh |
| Tin vào ngày KQKD của script khi nó là ước tính, hoặc bỏ qua dòng `chưa rõ ngày KQKD` | Xác nhận ngày bằng tin, rồi chạy lại `plan --earnings-date YYYY-MM-DD` |
| Mở báo cáo bằng bối cảnh, lặp lại tiêu đề lệnh trên dòng `TG:` đầu, thêm bảng tổng hợp | Dòng đầu là **Kết luận:**; tiêu đề lệnh là dòng `TG:` đầu kèm #id; điền đúng khung ở mục Báo cáo |
| Tin không ngày, thiếu nhóm vĩ mô hoặc lịch KQKD | Đủ bốn nhóm tin ở bước 2, có ngày |
| Gọi Exa song song, bị `RATE_LIMITED` | Tuần tự, cách khoảng 15 giây; bị chặn thì đợi `retry_after_seconds` rồi thử lại, tối đa 3 lần |
| Stop vừa đủ 1 ATR, giá chạy làm còn 0,99 ATR | Chạy lại `plan` với giá mới ngay trước khi báo |
| Stop sát đỉnh/đáy ngày (`plan` FAIL `stop >= 0.25 ATR from daily highs/lows`) | Dời stop qua hẳn mọi mức trong `too close`; R:R không còn đủ thì bỏ lệnh, không ép stop sát lại |
| Gọi "stop sạch" khi `plan` in `WARN … (near: …)` (AVGO 13/11: stop 314,5 nằm trên đáy 10/11 311,7 chỉ 0,15 ATR) | `WARN` không chặn lệnh nhưng hạ trần xuống B. Dời stop qua mức đó nếu R:R còn đủ, không thì để hạng B |
| Gọi lệnh là hạng A trong khi dòng `TG:` đầu ghi `(tối đa hạng B)` (AVGO 344,3 ngày 13/11: limit cách mark 1,26 ATR, trùm PPI) | Hạng ≤ `Hạng tối đa`; chép lý do vào **Phản biện** |
| Báo "không có lệnh cũ" vì báo cáo cũ ở `/tmp` mất khi WSL khởi động lại (13/11 bỏ sót AVGO 348,5 và TSM 400 đã khớp) | Mỗi lệnh báo cáo đều có `plan --log`; lệnh cũ lấy từ `orders` |
| Viết lại script dò stop/entry trong scratchpad mỗi lần săn | `hunt_stock_data.py stops` |
| Nói "gãy", "thủng", "bị từ chối" khi mark chỉ tạm vượt mức, hoặc đọc nến 4h `LIVE` như nến đã đóng | Chỉ tính trên nến ngày/4h đã đóng; nến `LIVE` là nến đang chạy |
| Gọi `avg last 21` là trung bình 30 ngày, hoặc coi funding dương nhỏ là long quá nóng | `avg last 21` là 21 kỳ funding (7 ngày với kỳ 8h, 3,5 ngày với kỳ 4h); phần lớn hợp đồng cổ phiếu đứng ở 0% khi trung tính |
| Đoán thị trường và giờ sàn theo tên mã | Dùng cột `mkt`: `SKHY` là ADR giờ Mỹ, `ZHONGJI`/`GIGADEV` là H-share Hồng Kông |
| Chọn mã vừa nhảy mạnh vì ATR nến đóng còn nhỏ | Bỏ mã cờ `PUMP` |
| Phân tích BCTC cho mã `PRE` | Mã `PRE` chưa niêm yết, không có BCTC; chỉ dựa vào tin và vị thế |
| Ba lệnh cùng chiều cùng nhóm ngành (bán dẫn/AI) không cảnh báo | `plan --log` chỉ cho 2 lệnh cùng chiều; 2 lệnh đó cùng nhóm ngành thì nêu tương quan trong **Quản lý rủi ro** |
| Mua bắt đáy liên tục khi thị trường giảm (30/10–20/11: 7/7 lệnh LONG khớp chạm stop; lệnh mua dưới giá khớp 7/10 lần, lệnh bán trên giá chỉ 2/7, vì giá giảm chỉ chạm lệnh mua) | Dựng theo dòng `Xu hướng`; `plan` FAIL lệnh ngược xu hướng QQQ/EWY. Không đổi mã proxy, không bỏ qua dòng FAIL |
| Ghi lại cùng một ý tưởng nhiều lần (AVGO LONG được gọi 4 lần từ 30/10 tới 13/11; #2 vào khi lệnh 12/11 đã khớp) | `plan --log` từ chối lệnh thứ hai cùng mã cùng chiều: quản lý lệnh đang có, không mở thêm |
| Giữ nguyên cả lệnh chờ TP xa dù đã lãi +1R (AVGO 326 lên +1,01R, AVGO 348,5 lên +1,20R, rồi cả hai về stop) | Chốt một nửa ở giá `Chốt 1/2` của dòng `TG:`, dời stop phần còn lại về giá vào |
| Chỉ soi và chỉ báo cáo chip/AI (các lượt săn 06–13/11 chỉ ra AVGO, TSM, META, GOOGL, TSLA), vì `scan` từng cắt ở 40 mã mà 29/40 là công nghệ | Quét toàn bộ, không tự thêm `--top`; chọn mã soi kỹ theo bước 3 (tối đa 3 mã/ngành, ít nhất 1–2 mã ngoài bán dẫn/AI khi có) |
| Bỏ mã `OKxN` vì nghĩ là "quá biến động", hoặc chạy `plan` ở x5 cho mã `OKx3` | `OKxN` vẫn giao dịch được: chạy `stops` / `plan` với `--leverage N` và dán dòng Size có `(xN)` |
| Đề xuất mã chỉ có trên Binance (Tencent, ANET…), hoặc tự quy đổi size từ cổ phiếu sang hợp đồng | Chỉ chọn mã có trong bảng `scan`; `plan` chặn mã không có trên OKX; dán nguyên dòng Size (đã là số hợp đồng OKX) |
| Bịa số hoặc mức giá | Chỉ dùng số từ script và bài có nguồn |
| Gõ lại số vào báo cáo hoặc Telegram, lệch với `plan` | Dán các dòng `TG:` của lần `plan` cuối |
| Trích link news.google.com cho mã Mỹ | Dùng link bài gốc trong mục Yahoo của `news` |
