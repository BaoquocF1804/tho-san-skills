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
| Đòn bẩy | x5 (khác thì truyền `--leverage`) |
| Vốn | 1000 USDT (`--capital`) |
| Rủi ro mỗi lệnh | 1% vốn |
| Ký quỹ tối đa mỗi lệnh | 20% vốn |
| Độ lệch mark–index | ≤ 0,5% (vượt thì cờ `INDEX`, đứng ngoài) |
| Stop | ≥ 1 ATR14 ngày, ≤ `(1/đòn bẩy − mmr)/2` (8,75% ở x5) và cách mọi đỉnh/đáy ngày ≥ 0,25 ATR (`plan` tự kiểm). ATR và mọi chỉ báo ngày/4h chỉ tính nến T2–T6, vì cuối tuần sàn cơ sở đóng và giá gần như đứng |
| R:R gộp | ≥ 1,5 (`plan` in thêm `net R:R` sau phí taker 2 chiều 0,10%) |
| Vào ngay | entry trong ±0,5% giá mark; xa hơn là lệnh chờ (`limit` nếu chờ hồi, `stop` nếu đánh phá vỡ) |
| KQKD | Không giữ lệnh qua ngày KQKD: `plan` FAIL nếu KQKD rơi vào `--horizon-days` (mặc định 20). Muốn vào trước KQKD thì rút `--horizon-days` để đóng trước ngày đó và ghi vào **Sai nếu**; không thì bỏ lệnh |
| Tầm nhìn | ≤ 20 ngày, tối đa 3 lệnh |

## Quy trình
`hunt_stock_data.py` dưới đây là `python3 ~/.gemini/config/skills/tho-san-co-phieu/scripts/hunt_stock_data.py`.

1. **Quét:** `hunt_stock_data.py scan [--market all|us|kr|hk|cn|adr|pre]` (khoảng 20 giây, 40 hợp đồng lớn nhất).
   - Chỉ săn mã cờ `OK`. Bỏ `ATR` (quá biến động cho x5, hoặc chưa đủ 15 phiên để tính ATR), `PUMP` (nhảy ≥ 20%/24h hoặc funding cực đoan), `INDEX`.
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
3. **Soi kỹ 3–6 mã:** `hunt_stock_data.py detail SYM1 SYM2 ...` (mức giá theo ATR, vị thế nhỏ lẻ và top trader, định giá và tăng trưởng quy USD, bảng quý SEC nếu công ty nộp 10-Q, nến hôm nay, nến 4h).
4. **Dựng setup, chiều nào cũng được:** ưu tiên LONG cổ phiếu tăng trưởng doanh thu/EPS mạnh, hưởng lợi chu kỳ ngành (HBM/AI/Cloud/Robotics) đang hồi về hỗ trợ/EMA; ưu tiên SHORT cổ phiếu suy giảm cơ bản, định giá quá cao, hoặc nhỏ lẻ fomo quá nóng khi gãy cấu trúc. Stop đặt ở mức luận điểm sai **và** vượt qua đỉnh/đáy swing gần đó; target ở mức cấu trúc (hỗ trợ, kháng cự, EMA).
5. **Kiểm từng lệnh ngay trước khi báo:** `hunt_stock_data.py plan LONG|SHORT SYM --stop X --target Y [--entry E] [--capital C] [--horizon-days N]`. `FAIL` thì sửa mức hoặc bỏ lệnh. Lệnh vào ngay khớp quanh mark, nên `plan` tính rủi ro từ giá xấu hơn giữa entry và mark. `PASS` thì `plan` in sẵn 4 dòng `TG:` (tiêu đề; Vào/Stop/TP/R:R; Size/Ký quỹ/Rủi ro/Thanh lý; Cơ bản & KQKD): báo cáo dán nguyên văn các dòng này (bỏ tiền tố `TG: `). Không gõ lại con số nào. Độ lệch mark–index và dòng KQKD cũng chép từ output.

## Báo cáo trên khung chat (tiếng Việt, đúng thứ tự)
1. Một dòng kết luận: có hay không có lệnh hạng A (vào ngay / lệnh chờ), bao nhiêu lệnh, thuộc những thị trường nào (`US`, `ADR`, `KR`, `HK`, `CN`, `PRE`).
2. Bối cảnh vĩ mô (Phố Wall và châu Á): tối đa 5 gạch đầu dòng, mỗi ý có ngày.
3. Mỗi lệnh vào ngay: tiêu đề `### 🟢 LONG SYM [MKT] (R:R x)` hoặc `🔴 SHORT`; 4 dòng `TG:` của `plan`, nguyên văn, bỏ tiền tố; dòng KQKD từ `plan`; rồi **Cơ bản & KQKD**, **Kỹ thuật & Vị thế**, **Phản biện**, **Sai nếu**.
4. Lệnh chờ: như lệnh vào ngay (dòng `TG:` đầu đã ghi `Limit` hay `Stop`), hiệu lực 24 giờ. Nếu `/tmp/tho-san-co-phieu/` có báo cáo dưới 24 giờ, ghi rõ từng lệnh chờ của báo cáo đó còn giữ, hủy hay thay bằng lệnh nào.
5. Đã loại: mỗi mã một dòng kèm lý do (cơ bản, kỹ thuật, dính KQKD, hoặc cờ `ATR`/`PUMP`/`INDEX`).
6. Quản lý rủi ro: tương quan với Nasdaq/S&P 500/KOSPI/Hang Seng; rủi ro gap khi mở phiên sàn cơ sở; điều kiện đóng sớm.
7. Nguồn: link các bài báo và dữ liệu BCTC đã dùng.
8. Một dòng: phân tích tham khảo, không phải lời khuyên đầu tư.

## Gửi Telegram (mỗi lần săn — bản rút gọn 1 tin nhắn)
- Bản đầy đủ lưu vào `/tmp/tho-san-co-phieu/report-<YYYYmmdd-HHMM>.md` và hiển thị trong khung chat.
- Bản gửi Telegram lưu riêng vào `/tmp/tho-san-co-phieu/tg-<YYYYmmdd-HHMM>.md` (**tối đa ~1200–1800 ký tự, gọn trong 1 tin nhắn duy nhất, không dùng bảng Markdown, không kèm danh sách link URL và danh sách mã đã loại**):
  - **Dòng đầu:** Kết luận ngắn (số lệnh vào ngay / lệnh chờ).
  - **Bối cảnh Vĩ mô:** tối đa 3 gạch đầu dòng, mỗi dòng 1 câu ngắn kèm ngày.
  - **Mỗi lệnh (vào ngay hoặc chờ):**
    - 4 dòng `TG:` của `plan`, nguyên văn, bỏ tiền tố `TG: `
    - `• Lý do: <1 câu ngắn>`
    - `• Sai nếu: <mức đóng sớm / hủy lệnh>`
  - **Lệnh chờ cũ** (khi có báo cáo dưới 24 giờ): 1 dòng giữ / hủy / thay.
  - **Quản trị rủi ro:** 1–2 dòng (tối đa mấy lệnh cùng lúc, rủi ro gap mở phiên / KQKD).
- Kiểm `wc -m /tmp/tho-san-co-phieu/tg-<...>.md` ≤ 1800 rồi gửi bằng lệnh:
  `hermes send --to telegram --subject "📈 Thợ săn Cổ phiếu <dd/mm HH:MM>" --file /tmp/tho-san-co-phieu/tg-<...>.md`
- Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục. Người dùng nói "không gửi" thì bỏ bước này.

## Lỗi thường gặp
| Lỗi | Cách đúng |
|---|---|
| Giữ lệnh qua ngày KQKD, chỉ gắn nhãn cảnh báo | `plan` FAIL thì rút `--horizon-days` để đóng trước KQKD, hoặc bỏ lệnh |
| Tin không ngày, thiếu nhóm vĩ mô hoặc lịch KQKD | Đủ bốn nhóm tin ở bước 2, có ngày |
| Gọi Exa song song, bị `RATE_LIMITED` | Tuần tự, cách khoảng 15 giây; bị chặn thì đợi `retry_after_seconds` rồi thử lại, tối đa 3 lần |
| Stop vừa đủ 1 ATR, giá chạy làm còn 0,99 ATR | Chạy lại `plan` với giá mới ngay trước khi báo |
| Stop sát đỉnh/đáy ngày (`plan` FAIL `stop >= 0.25 ATR from daily highs/lows`) | Dời stop qua hẳn mọi mức trong `too close`; R:R không còn đủ thì bỏ lệnh, không ép stop sát lại |
| Nói "gãy", "thủng", "bị từ chối" khi mark chỉ tạm vượt mức, hoặc đọc nến 4h `LIVE` như nến đã đóng | Chỉ tính trên nến ngày/4h đã đóng; nến `LIVE` là nến đang chạy |
| Gọi `avg last 21` là trung bình 30 ngày, hoặc coi funding dương nhỏ là long quá nóng | `avg last 21` là 21 kỳ funding (7 ngày với kỳ 8h, 3,5 ngày với kỳ 4h); phần lớn hợp đồng cổ phiếu đứng ở 0% khi trung tính |
| Đoán thị trường và giờ sàn theo tên mã | Dùng cột `mkt`: `SKHY` là ADR giờ Mỹ, `ZHONGJI`/`GIGADEV` là H-share Hồng Kông |
| Chọn mã vừa nhảy mạnh vì ATR nến đóng còn nhỏ | Bỏ mã cờ `PUMP` |
| Phân tích BCTC cho mã `PRE` | Mã `PRE` chưa niêm yết, không có BCTC; chỉ dựa vào tin và vị thế |
| Ba lệnh cùng chiều cùng nhóm ngành (bán dẫn/AI) không cảnh báo | Nêu tương quan, khuyên tối đa 2 lệnh cùng nhóm |
| Bịa số hoặc mức giá | Chỉ dùng số từ script và bài có nguồn |
| Gõ lại số vào báo cáo hoặc Telegram, lệch với `plan` | Dán các dòng `TG:` của lần `plan` cuối |
| Trích link news.google.com cho mã Mỹ | Dùng link bài gốc trong mục Yahoo của `news` |
