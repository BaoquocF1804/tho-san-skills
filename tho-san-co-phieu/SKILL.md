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
| Vào ngay | entry trong ±0,5% giá mark; xa hơn là lệnh chờ (`limit` nếu chờ hồi, `stop` nếu đánh phá vỡ) |
| KQKD | Không giữ lệnh qua ngày KQKD: `plan` FAIL nếu KQKD rơi vào `--horizon-days` (mặc định 20). Muốn vào trước KQKD thì rút `--horizon-days` để đóng trước ngày đó và ghi vào **Sai nếu**; không thì bỏ lệnh |
| Tầm nhìn | ≤ 20 ngày, tối đa 3 lệnh |
| Hạng | `plan` in `Hạng tối đa`. Là B khi stop dính `WARN`, khi lệnh chờ có 24 giờ hiệu lực trùm một sự kiện vĩ mô Mỹ (CPI, PPI, việc làm, FOMC; lịch nằm ở `macro_events.json`, gốc repo skills), hoặc khi entry chờ cách mark hơn 1 ATR. Báo cáo được hạ hạng, **không được nâng** |

## Quy trình
`hunt_stock_data.py` dưới đây là `python3 ~/.gemini/config/skills/tho-san-co-phieu/scripts/hunt_stock_data.py`.

1. **Quét:** `hunt_stock_data.py scan [--market all|us|kr|hk|cn|adr|pre]`. Lệnh mất khoảng 1 phút và quét mọi hợp đồng có thanh khoản từ 1 triệu USD/24h (khoảng 120 mã). Đừng tự thêm `--top 40`: cắt ở 40 mã sẽ chỉ còn nhóm công nghệ.
   - Săn mã cờ `OK` (đòn bẩy mặc định) và `OKxN` (dùng `--leverage N`).
   - Bỏ `ATR` (quá biến động kể cả ở x2, hoặc chưa đủ 15 phiên để tính ATR), `PUMP` (nhảy ≥ 20%/24h hoặc funding cực đoan) và `INDEX`.
   - Cột `sector` và dòng cuối `Tradeable by sector` cho biết mã giao dịch được thuộc những ngành nào.
   - Cột `earn`: `Xd!` là KQKD trong ≤ 7 ngày, `Xd` là còn X ngày, `-Xd` là vừa công bố X ngày trước. `7d`/`20d` tính theo phiên.
2. **Tin tức. REQUIRED SUB-SKILL:** agent-reach.
   - Chạy `hunt_stock_data.py news SYM1 SYM2 ...`: Google News RSS cho Phố Wall, châu Á, Fed/lợi suất, chip/thuế quan. Mã niêm yết ở Mỹ (`US`/`ADR`) lấy RSS Yahoo Finance theo mã, có link bài gốc (link Google News chỉ là link chuyển hướng); mã châu Á và `PRE` tìm qua Google News theo tên công ty.
   - Mã nộp hồ sơ SEC có thêm mục `SEC 8-K/6-K 30 ngày`: dòng có `!` (KQKD, đổi lãnh đạo, hợp đồng lớn, M&A, nợ mới, suy giảm tài sản, hủy niêm yết, phá sản…) là chất xúc tác: mở link SEC đọc trước khi dựng setup.
   - Bổ sung: `agent-reach doctor --text` trước, rồi `agent-reach web search "..." --limit 5` **tuần tự, cách nhau khoảng 15 giây**; đọc bài chính bằng `agent-reach web read <url>`. agent-reach lỗi thì dùng web search có sẵn của runtime (`WebSearch` trên Claude Code, `search_web` trên Gemini).
   - Phải đủ bốn nhóm, mỗi tin có ngày (bỏ tin không ngày):
     - vĩ mô Mỹ và châu Á 48 giờ qua: S&P 500, Nasdaq, KOSPI, Hang Seng, lợi suất 10 năm Mỹ, Fed/FOMC, thuế quan, kiểm soát xuất khẩu chip
     - ngày KQKD của từng mã trong shortlist. Ngày từ script có thể là ước tính (nguồn SEC là hồ sơ gần nhất + 91 ngày), nên xác nhận bằng tin; ngày xác nhận khác thì chạy lại `plan`
     - chất xúc tác từng mã: KQKD vừa công bố (beat/miss, guidance), đơn hàng HBM/AI, sản phẩm mới, M&A, pháp lý
     - giờ sàn cơ sở (giờ VN): Mỹ/ADR 20:30–03:00 khi Mỹ theo giờ mùa hè (Chủ nhật thứ hai tháng 3 đến Chủ nhật đầu tiên tháng 11), còn lại 21:30–04:00; Hàn 07:00–13:30; Hồng Kông 08:30–11:00 và 12:00–15:00; A-share 08:30–10:30 và 12:00–14:00. Ngoài giờ sàn cơ sở thanh khoản mỏng, dễ gap khi mở phiên
3. **Soi kỹ 3–6 mã, trải ra nhiều ngành.**
   - Tối đa 3 mã cùng một ngành (cột `sector`).
   - Nếu dòng `Tradeable by sector` có mã ngoài bán dẫn/AI (Electronic Technology, Technology Services), phải soi ít nhất 1–2 mã ngoài nhóm đó, chọn mã có xu hướng hoặc chất xúc tác rõ nhất. Tin tức xoay quanh chip không phải lý do để chỉ soi chip.
   - Lệnh: `hunt_stock_data.py detail SYM1 SYM2 ...` (mức giá theo ATR, vị thế nhỏ lẻ và top trader, định giá và tăng trưởng quy USD, bảng quý SEC nếu công ty nộp 10-Q, nến hôm nay, nến 4h, kèm dự báo xác suất **Kronos-small MC** 30 kịch bản qua 20 phiên T2–T6: dải phân vị `P10 / P50 / P90`, biên độ đỉnh/đáy P50 theo ATR và xác suất chạm TP/SL chuẩn `±1,5 ATR / ∓1,0 ATR`).
4. **Dựng setup, chiều nào cũng được:** ưu tiên LONG cổ phiếu tăng trưởng doanh thu/EPS mạnh, hưởng lợi chu kỳ ngành của chính nó (bán dẫn/AI, phần mềm, y tế, tiêu dùng, tài chính, công nghiệp, năng lượng…) đang hồi về hỗ trợ/EMA; ưu tiên SHORT cổ phiếu suy giảm cơ bản, định giá quá cao, hoặc nhỏ lẻ fomo quá nóng khi gãy cấu trúc. Stop đặt ở mức luận điểm sai **và** vượt qua đỉnh/đáy swing gần đó; target ở mức cấu trúc (hỗ trợ, kháng cự, EMA).
   - Dò stop bằng `hunt_stock_data.py stops LONG|SHORT SYM [--span 0.07] [--step 0.005]`, đừng viết script dò riêng. Lệnh này in, cho từng entry tính từ mark, mức stop chặt nhất mà `plan` cho qua. Mục tiêu 1,5R/2R đi kèm chỉ để tham chiếu. `WARN near` là đỉnh/đáy 20 phiên gần ngay sát stop.
5. **Kiểm từng lệnh ngay trước khi báo:** `hunt_stock_data.py plan LONG|SHORT SYM --stop X --target Y [--entry E] [--capital C] [--horizon-days N]`.
   - `FAIL` thì sửa mức hoặc bỏ lệnh.
   - Lệnh vào ngay khớp quanh mark, nên `plan` tính rủi ro từ giá xấu hơn giữa entry và mark.
   - `plan` tự chạy **Kronos-small MC** (30 đường giá Monte Carlo trên nến T2–T6) để chấm xác suất khớp Entry, `% chạm TP trước SL`, `% chạm SL trước TP` và kỳ vọng `E[R]`. Nếu in `⚠️ KRONOS PHẢN BIỆN` (xác suất chạm SL > chạm TP hoặc `E[R] < 0`), bắt buộc ghi rõ vào mục **Phản biện** và cân nhắc hạ hạng/bỏ lệnh.
   - `PASS` thì `plan` in `Hạng tối đa` và 5 dòng `TG:` (tiêu đề; Vào/Stop/TP/R:R; Size/Ký quỹ/Rủi ro/Thanh lý; Cơ bản & KQKD; Kronos MC P10/P50/P90 & % chạm TP trước SL). Báo cáo dán nguyên văn các dòng này (bỏ tiền tố `TG: `), kể cả `(tối đa hạng B)` ở dòng đầu. Không gõ lại con số nào. Độ lệch mark–index và dòng KQKD cũng chép từ output.
   - Lần `plan` cuối của mỗi lệnh đưa vào báo cáo phải thêm `--log`:
     - `LOG: #id`: lệnh mới.
     - `LOG: trùng #id`: lệnh cũ còn hiệu lực, báo cáo ghi "giữ #id".
6. **Lệnh cũ:** chạy `hunt_stock_data.py orders`. Nó đọc sổ lệnh 20 ngày ở `~/.local/share/tho-san-co-phieu/orders.json` và tính trạng thái từ nến Binance. Không lấy lệnh cũ từ file báo cáo.
   - `CHỜ`: quyết định giữ, hủy (`orders --cancel ID`), hoặc thay (hủy trước, rồi `plan --log` lệnh mới).
   - `KHỚP … đang chạy` / `chạm TP` / `chạm stop`: lệnh đã khớp trên giấy. Hỏi người dùng có vào thật không, nêu R hiện tại và mức đóng sớm. `orders --cancel` sẽ từ chối các lệnh này.
   - `HẾT HẠN` / `ĐÃ HỦY`: bỏ qua.

## Báo cáo trên khung chat (tiếng Việt, đúng thứ tự)
1. Một dòng kết luận: có hay không có lệnh hạng A (vào ngay / lệnh chờ), bao nhiêu lệnh, thuộc những thị trường nào (`US`, `ADR`, `KR`, `HK`, `CN`, `PRE`). Hạng của mỗi lệnh không vượt `Hạng tối đa` mà `plan` in ra.
2. Bối cảnh vĩ mô (Phố Wall và châu Á): tối đa 5 gạch đầu dòng, mỗi ý có ngày.
3. Mỗi lệnh vào ngay:
   - Tiêu đề `### 🟢 LONG SYM [MKT] (R:R x) #id` hoặc `🔴 SHORT`.
   - Các dòng `TG:` của `plan` (gồm cả dòng Kronos MC), nguyên văn, bỏ tiền tố; dòng KQKD từ `plan`.
   - Rồi **Cơ bản & KQKD**, **Kỹ thuật & Vị thế**, **Phản biện**, **Sai nếu**. **Phản biện** chép lại lý do của `Hạng tối đa: B` hoặc `⚠️ KRONOS PHẢN BIỆN` nếu có.
4. Lệnh chờ: trình bày như lệnh vào ngay (dòng `TG:` đầu đã ghi `Limit` hay `Stop`), hiệu lực 24 giờ. Lệnh cũ lấy từ `orders` (bước 6), mỗi lệnh một dòng gồm #id, trạng thái, và giữ / hủy / thay hoặc cách quản lý nếu đã khớp.
5. Đã loại: mỗi mã một dòng kèm lý do (cơ bản, kỹ thuật, dính KQKD, hoặc cờ `ATR`/`PUMP`/`INDEX`).
6. Quản lý rủi ro: tương quan với Nasdaq/S&P 500/KOSPI/Hang Seng; rủi ro gap khi mở phiên sàn cơ sở; điều kiện đóng sớm.
7. Nguồn: link các bài báo và dữ liệu BCTC đã dùng.
8. Một dòng: phân tích tham khảo, không phải lời khuyên đầu tư.

## Gửi Telegram (mỗi lần săn — bản rút gọn 1 tin nhắn)
- Bản đầy đủ lưu vào `~/.local/share/tho-san-co-phieu/report-<YYYYmmdd-HHMM>.md` và hiển thị trong khung chat. Không lưu ở `/tmp`, vì WSL khởi động lại là mất.
- Bản gửi Telegram lưu riêng vào `~/.local/share/tho-san-co-phieu/tg-<YYYYmmdd-HHMM>.md` (**tối đa ~1200–1800 ký tự, gọn trong 1 tin nhắn duy nhất, không dùng bảng Markdown, không kèm danh sách link URL và danh sách mã đã loại**):
  - **Dòng đầu:** Kết luận ngắn (số lệnh vào ngay / lệnh chờ).
  - **Bối cảnh Vĩ mô:** tối đa 3 gạch đầu dòng, mỗi dòng 1 câu ngắn kèm ngày.
  - **Mỗi lệnh (vào ngay hoặc chờ):**
    - 4 dòng `TG:` của `plan`, nguyên văn, bỏ tiền tố `TG: `
    - `• Lý do: <1 câu ngắn>`
    - `• Sai nếu: <mức đóng sớm / hủy lệnh>`
  - **Lệnh cũ** (từ `orders`): mỗi lệnh 1 dòng: #id, giữ / hủy / thay, hoặc đã khớp và đang ở đâu.
  - **Quản trị rủi ro:** 1–2 dòng (tối đa mấy lệnh cùng lúc, rủi ro gap mở phiên / KQKD).
- Kiểm `wc -m ~/.local/share/tho-san-co-phieu/tg-<...>.md` ≤ 1800 rồi gửi bằng lệnh:
  `hermes send --to telegram --subject "📈 Thợ săn Cổ phiếu <dd/mm HH:MM>" --file ~/.local/share/tho-san-co-phieu/tg-<...>.md`
- Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục. Người dùng nói "không gửi" thì bỏ bước này.

## Lỗi thường gặp
| Lỗi | Cách đúng |
|---|---|
| Giữ lệnh qua ngày KQKD, chỉ gắn nhãn cảnh báo | `plan` FAIL thì rút `--horizon-days` để đóng trước KQKD, hoặc bỏ lệnh |
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
| Ba lệnh cùng chiều cùng nhóm ngành (bán dẫn/AI) không cảnh báo | Nêu tương quan, khuyên tối đa 2 lệnh cùng nhóm |
| Chỉ soi và chỉ báo cáo chip/AI (các lượt săn 06–13/11 chỉ ra AVGO, TSM, META, GOOGL, TSLA), vì `scan` từng cắt ở 40 mã mà 29/40 là công nghệ | Quét toàn bộ, không tự thêm `--top`; chọn mã soi kỹ theo bước 3 (tối đa 3 mã/ngành, ít nhất 1–2 mã ngoài bán dẫn/AI khi có) |
| Bỏ mã `OKxN` vì nghĩ là "quá biến động", hoặc chạy `plan` ở x5 cho mã `OKx3` | `OKxN` vẫn giao dịch được: chạy `stops` / `plan` với `--leverage N` và dán dòng Size có `(xN)` |
| Bịa số hoặc mức giá | Chỉ dùng số từ script và bài có nguồn |
| Gõ lại số vào báo cáo hoặc Telegram, lệch với `plan` | Dán các dòng `TG:` của lần `plan` cuối |
| Trích link news.google.com cho mã Mỹ | Dùng link bài gốc trong mục Yahoo của `news` |
