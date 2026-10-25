---
name: tho-san
description: >-
  Use when the user asks to hunt for crypto futures trades or calls — "đi săn", "săn lệnh", "săn kèo", "thợ săn", "có kèo nào không", "tìm lệnh long/short" — or wants a manual Binance USDⓈ-M LONG/SHORT scan of crypto perpetuals with entry, stop, target and position size done by the agent itself rather than by automated hunter code. Not for stock perpetuals (that is tho-san-co-phieu).
---

# Thợ săn Futures (săn tay)

## Tổng quan
Tự săn lệnh crypto trên Binance USDⓈ-M: dữ liệu mới từ script [`hunt_data.py`](./scripts/hunt_data.py), tin tức có ngày từ agent-reach, tự phân tích, báo cáo tiếng Việt. Mọi con số lấy từ script ngay lúc báo cáo; mọi tin có ngày và nguồn; không có lệnh hạng A thì nói thẳng. Chỉ phân tích, không đặt lệnh; báo cáo xong thì gửi lên Telegram qua Hermes.

## Khung rủi ro (mặc định; dùng số người dùng nói nếu khác)
| Tham số | Giá trị |
|---|---|
| Đòn bẩy | x5 (khác thì truyền `--leverage`) |
| Vốn | 1000 USDT (`--capital`) |
| Rủi ro mỗi lệnh | 1% vốn |
| Ký quỹ tối đa mỗi lệnh | 20% vốn |
| Stop | ≥ 1 ATR14 ngày, ≤ `(1/đòn bẩy − mmr)/2` (8,75% ở x5) và cách mọi đỉnh/đáy ngày ≥ 0,25 ATR (`plan` tự kiểm) |
| R:R gộp | ≥ 1,5 (script kèm thêm `net R:R` sau phí taker 2 chiều 0,10%) |
| Vào ngay | entry trong ±0,5% giá mark; xa hơn là lệnh chờ (`limit` nếu chờ hồi, `stop` nếu đánh phá vỡ) |
| Tầm nhìn | ≤ 20 ngày, tối đa 3 lệnh |

## Quy trình
1. **Dữ liệu:** `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py scan` (khoảng 15 giây, 40 hợp đồng lớn nhất). Chỉ săn mã có flag `OK`; `ATR` là quá biến động cho đòn bẩy hoặc mã mới niêm yết chưa đủ 15 nến ngày, `PUMP` là vừa pump/funding cực đoan.
2. **Tin tức. REQUIRED SUB-SKILL:** agent-reach.
   - Chạy `agent-reach doctor --text` trước.
   - Tìm bằng `agent-reach web search "..." --limit 5` (Exa) **tuần tự, cách nhau khoảng 15 giây**; đọc bài chính bằng `agent-reach web read <url>`; quét RSS rộng bằng `uv run -q --no-project --with feedparser python3` (feedparser lấy được ngày và link từng bài). Twitter/Reddit chỉ dùng khi doctor không báo `not_added`. agent-reach lỗi thì dùng web search có sẵn của runtime (`WebSearch` trên Claude Code, `search_web` trên Gemini).
   - Phải có đủ bốn nhóm, mỗi tin có ngày (bỏ tin không ngày):
     - vĩ mô và địa chính trị 48 giờ qua (dầu, chiến sự, Fed và ngày họp FOMC kế tiếp)
     - dòng tiền ETF BTC/ETH ngày gần nhất, bản đồ thanh lý BTC/ETH (cụm long/short; với altcoin không có bài heatmap trong ngày thì dùng vùng swing high/low kết hợp OI để ước lượng vùng quét stop)
     - lịch sự kiện 2 tuần tới: mở khóa token, nâng cấp, FOMC
     - tin riêng từng mã trong shortlist (OI kỷ lục, hack, unlock, ETF)
3. **Soi kỹ 3–6 mã:** `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py detail SYM1 SYM2 ...` (mức hỗ trợ/kháng cự đã gom cụm 0,25 ATR và tính cả S/R flip, vị thế nhỏ lẻ và top trader, nến hôm nay, nến 4h).
4. **Dựng setup, chiều nào cũng được:** hồi về hỗ trợ trong xu hướng; phá vỡ hoặc thủng mức có OI và taker xác nhận; đảo chiều khi đòn bẩy quá nóng (OI tăng mạnh, funding cao, nhỏ lẻ dồn một phía, top trader phía kia); catalyst có ngày. Stop đặt ở mức luận điểm sai **và** vượt qua cụm thanh lý / đỉnh đáy quét stop gần đó; target ở mức cấu trúc (hỗ trợ, kháng cự, EMA).
5. **Kiểm từng lệnh ngay trước khi báo:** `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py plan LONG|SHORT SYM --stop X --target Y [--entry E] [--capital C]`. `FAIL` thì sửa mức hoặc bỏ lệnh; entry xa mark là lệnh chờ (`limit` hoặc `stop` theo output của script). Khối lượng, ký quỹ, rủi ro, giá thanh lý chép từ output, không tự tính.

## Báo cáo (tiếng Việt, đúng thứ tự)
1. Một dòng kết luận: có hay không có lệnh hạng A, bao nhiêu lệnh.
2. Bối cảnh: tối đa 5 gạch đầu dòng, mỗi ý có ngày.
3. Mỗi lệnh vào ngay: tiêu đề `### 🔴 SHORT SYM (R:R x)` hoặc `🟢 LONG`; bảng Vào | Stop | Target | Khối lượng | Ký quỹ | Rủi ro | Thanh lý; rồi **Lý do**, **Phản biện**, **Sai nếu**.
4. Lệnh chờ: mức vào (ghi rõ lệnh `limit` hay `stop`), stop, target, R:R, hiệu lực 24 giờ; rồi **Lý do**, **Phản biện**, **Sai nếu** như lệnh vào ngay. Nếu `/tmp/tho-san/` có báo cáo dưới 24 giờ, ghi rõ từng lệnh chờ của báo cáo đó còn giữ, hủy hay thay bằng lệnh nào.
5. Đã loại: mỗi mã một dòng kèm lý do.
6. Quản lý rủi ro: lệnh cùng chiều là tương quan; sự kiện sắp tới; điều kiện đóng sớm (mức BTC).
7. Nguồn: link các bài đã dùng.
8. Một dòng: phân tích tham khảo, không phải lời khuyên đầu tư.

## Gửi Telegram (mỗi lần săn — bản rút gọn 1 tin nhắn)
- Bản đầy đủ lưu vào `/tmp/tho-san/report-<YYYYmmdd-HHMM>.md` và hiển thị trong khung chat.
- Bản gửi Telegram lưu riêng vào `/tmp/tho-san/tg-<YYYYmmdd-HHMM>.md` (**tối đa ~1200–1800 ký tự, gọn trong 1 tin nhắn duy nhất, không dùng bảng Markdown, không kèm danh sách link URL và danh sách mã đã loại**):
  - **Dòng đầu:** Kết luận ngắn (số lệnh vào ngay / lệnh chờ).
  - **Bối cảnh:** tối đa 3 gạch đầu dòng, mỗi dòng 1 câu ngắn kèm ngày.
  - **Mỗi lệnh (vào ngay hoặc chờ):**
    - `🔴 SHORT SYM` hoặc `🟢 LONG SYM` — `Vào ngay` / `Limit` / `Stop`
    - `• Vào: ... | Stop: ... (...%, ... ATR) | TP: ... (...%) | R:R: ...`
    - `• Size: ... (... USDT) | Ký quỹ: ... | Rủi ro: ... | Thanh lý: ~...`
    - `• Lý do: <1 câu ngắn>`
    - `• Sai nếu: <mức đóng sớm / hủy lệnh>`
  - **Lệnh chờ cũ** (khi có báo cáo dưới 24 giờ): 1 dòng giữ / hủy / thay.
  - **Quản trị rủi ro:** 1–2 dòng (tối đa mấy lệnh cùng lúc, mốc BTC đóng sớm, giờ sự kiện lớn).
- Kiểm `wc -m /tmp/tho-san/tg-<...>.md` ≤ 1800 rồi gửi bằng lệnh:
  `hermes send --to telegram --subject "🎯 Thợ săn <dd/mm HH:MM>" --file /tmp/tho-san/tg-<...>.md`
- Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục. Người dùng nói "không gửi" thì bỏ bước này.

## Ghi bảng điểm crypto-desk (nếu máy có `~/crypto-desk-rewrite`)
- Báo cáo xong thì ghi từng lệnh (vào ngay và `limit`) đúng mức trong báo cáo, để chấm cùng thước đo với hunter của crypto-desk:
  `~/crypto-desk-rewrite/scripts/desk log-call LONG|SHORT SYM --entry E --stop S --target T --note "<lý do 1 câu>"`
- Lệnh chờ kiểu `stop` chưa ghi được (script từ chối, báo lại người dùng). Người dùng nói "không ghi" thì bỏ bước này.
- Kết quả xem bằng `~/crypto-desk-rewrite/scripts/desk scorecard`, dòng `tho-san`.

## Lỗi thường gặp
| Lỗi | Cách đúng |
|---|---|
| Chỉ đọc tiêu đề RSS hoặc web search không ngày, bỏ sót chiến sự và unlock | Đủ bốn nhóm tin ở bước 2, có ngày |
| Gọi Exa song song, bị `RATE_LIMITED` | Tuần tự, cách khoảng 15 giây; bị chặn thì đợi `retry_after_seconds` rồi thử lại, tối đa 3 lần |
| Stop vừa đủ 1 ATR, giá chạy làm còn 0,99 ATR | Chạy lại `plan` với giá mới ngay trước khi báo |
| Stop nằm sát đỉnh/đáy ngày hoặc ngay dưới cụm thanh lý (`plan` FAIL `stop >= 0.25 ATR from daily highs/lows`) | Dời stop qua hẳn mọi mức trong `too close` và cụm thanh lý; R:R không còn đủ thì bỏ lệnh, không ép stop sát lại |
| Nói "gãy", "thủng", "bị từ chối" khi mark chỉ tạm vượt mức, hoặc đọc nến 4h `LIVE` như nến đã đóng | Chỉ tính trên nến ngày/4h đã đóng; nến `LIVE` là nến đang chạy |
| Coi funding 0,0100% là long quá nóng; gọi `avg last 21` là trung bình 30 ngày | 0,01%/8h là mức mặc định của Binance (trung tính); `avg last 21` là 21 kỳ, tức 7 ngày với kỳ 8h |
| Mục bản đồ thanh lý chỉ ghi số tiền đã bị thanh lý | Ghi mức giá các cụm long/short đang chờ, rồi đặt stop vượt các cụm đó |
| Chọn mã vừa pump vì ATR nến đóng còn nhỏ | Bỏ mã flag `PUMP` |
| Đặt lệnh chờ đánh thủng đáy nhưng ghi là `limit bán` | Đánh thủng đáy (SHORT dưới giá mark) hoặc vượt đỉnh (LONG trên giá mark) phải là lệnh `stop` |
| Ba lệnh cùng chiều không cảnh báo | Nêu tương quan, khuyên tối đa 2 lệnh |
| Bịa số hoặc mức giá | Chỉ dùng số từ script và bài có nguồn |

