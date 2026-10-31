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
5. **Kiểm từng lệnh ngay trước khi báo:** `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py plan LONG|SHORT SYM --stop X --target Y [--entry E] [--capital C]`. `FAIL` thì sửa mức hoặc bỏ lệnh; entry xa mark là lệnh chờ (`limit` hoặc `stop` theo output của script). Lệnh vào ngay khớp quanh mark, nên `plan` tính rủi ro từ giá xấu hơn giữa entry và mark. `PASS` thì `plan` in sẵn 3 dòng `TG:` (tiêu đề; Vào/Stop/TP/R:R; Size/Ký quỹ/Rủi ro/Thanh lý) và dòng `DESK:`: báo cáo dán nguyên văn các dòng `TG:` (bỏ tiền tố `TG: `), desk chạy đúng dòng `DESK:`. Không gõ lại con số nào.
6. **Ghi desk trước khi viết báo cáo** (máy có `~/crypto-desk-rewrite`; người dùng nói "không ghi" thì bỏ bước này). `desk` dưới đây là `~/crypto-desk-rewrite/scripts/desk`.
   - Lệnh cũ lấy từ desk, không từ `/tmp` (WSL khởi động lại là mất): `desk --json calls --status LOGGED`, giữ các dòng `segment` `tho-san` có `outcome` null (desk để `LOGGED` cả lệnh đã chấm). Chia theo `filled_at`:
     - có giờ: **đang chạy** (limit đã khớp, hoặc lệnh vào ngay), kể cả khi `expires_at` đã qua. Không hủy; quyết định giữ hay đóng sớm ở mức nào, và tính là vị thế đang mở ở mục Quản lý rủi ro.
     - `null`, `expires_at` chưa qua: **lệnh chờ chưa khớp**. Quyết định giữ, hủy hay thay.
     - `null`, `expires_at` đã qua: hết hạn không khớp, bỏ qua.
   - Hủy hoặc thay lệnh chờ: chạy `desk cancel-call ID` trước, để bảng điểm chỉ chấm lệnh cũ tới lúc hủy. Desk báo `đã khớp giá vào` thì lệnh vừa khớp: xử lý như lệnh đang chạy.
   - Mỗi lệnh `PASS` có dòng `DESK:`: chạy đúng dòng đó, thêm `--note "<lý do 1 câu>"`. Đọc JSON trả về:
     - `"duplicate": false`: lệnh mới, báo cáo ghi `#id`.
     - `"duplicate": true`: lệnh cũ còn giữ, báo cáo ghi "giữ #id", không tính là lệnh mới.
     - `Error: Đã đủ ... lệnh tho-san trong 24 giờ` hoặc vượt rủi ro 24 giờ: bỏ lệnh khỏi báo cáo, đưa vào **Đã loại** với lý do giới hạn ngày.
   - Lệnh chờ kiểu `stop` không có dòng `DESK:` vì desk chưa chấm được; báo cáo ghi "chưa ghi desk".
   - Kết quả xem bằng `desk scorecard`, dòng `tho-san`.

## Báo cáo (tiếng Việt, đúng thứ tự)
1. Một dòng kết luận: có hay không có lệnh hạng A, bao nhiêu lệnh.
2. Bối cảnh: tối đa 5 gạch đầu dòng, mỗi ý có ngày.
3. Mỗi lệnh vào ngay: tiêu đề là `### ` + dòng `TG:` đầu của `plan` (bỏ tiền tố) + ` #id`, ví dụ `### 🔴 SHORT BTCUSDT — Vào ngay #id`; ngay dưới là 2 dòng `TG:` còn lại, nguyên văn, bỏ tiền tố (R:R nằm trong dòng Vào); rồi **Lý do**, **Phản biện**, **Sai nếu**.
4. Lệnh chờ: như lệnh vào ngay (dòng `TG:` đầu đã ghi `Limit` hay `Stop`), hiệu lực 24 giờ. Lệnh cũ từ desk (bước 6), mỗi lệnh một dòng: lệnh chờ chưa khớp thì giữ #id, hủy #id, hoặc thay #id bằng #id mới; lệnh đang chạy thì #id, mã, chiều, entry, khớp lúc (`filled_at`), giữ hay đóng sớm ở mức nào.
5. Đã loại: mỗi mã một dòng kèm lý do.
6. Quản lý rủi ro: lệnh cùng chiều là tương quan; sự kiện sắp tới; điều kiện đóng sớm (mức BTC).
7. Nguồn: link các bài đã dùng.
8. Một dòng: phân tích tham khảo, không phải lời khuyên đầu tư.

## Gửi Telegram (mỗi lần săn — bản rút gọn 1 tin nhắn)
- Bản đầy đủ lưu vào `/tmp/tho-san/report-<YYYYmmdd-HHMM>.md` và hiển thị trong khung chat.
- Bản gửi Telegram lưu riêng vào `/tmp/tho-san/tg-<YYYYmmdd-HHMM>.md` (**tối đa ~2500 ký tự, gọn trong 1 tin nhắn duy nhất (Telegram cắt ở 4096), không dùng bảng Markdown, không kèm danh sách link URL và danh sách mã đã loại**):
  - **Dòng đầu:** Kết luận ngắn (số lệnh vào ngay / lệnh chờ).
  - **Bối cảnh:** tối đa 3 gạch đầu dòng, mỗi dòng 1 câu ngắn kèm ngày.
  - **Mỗi lệnh (vào ngay hoặc chờ):**
    - 3 dòng `TG:` của `plan`, nguyên văn, bỏ tiền tố `TG: `; thêm ` #id` desk vào cuối dòng đầu
    - `• Lý do: <1 câu ngắn>`
    - `• Sai nếu: <mức đóng sớm / hủy lệnh>`
  - **Lệnh cũ** (từ desk, bước 6): mỗi lệnh 1 dòng; lệnh chờ: giữ / hủy / thay kèm #id; lệnh đang chạy: #id đã khớp, giữ hay đóng sớm ở mức nào.
  - **Quản trị rủi ro:** 1–2 dòng (tối đa mấy lệnh cùng lúc, mốc BTC đóng sớm, giờ sự kiện lớn).
- Kiểm `wc -m /tmp/tho-san/tg-<...>.md` ≤ 2500 rồi gửi bằng lệnh:
  `hermes send --to telegram --subject "🎯 Thợ săn <dd/mm HH:MM>" --file /tmp/tho-san/tg-<...>.md`
- Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục. Người dùng nói "không gửi" thì bỏ bước này.

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
| Gõ lại số vào báo cáo, Telegram hoặc desk (desk ghi stop 2455 khi `plan` đã duyệt 2462) | Dán dòng `TG:`, chạy dòng `DESK:` của lần `plan` cuối |
| Ghi lại lệnh chờ đang giữ thành lệnh mới (#24, #25, #26 là cùng một lệnh ETH) | Desk trả `"duplicate": true` kèm id cũ; báo cáo ghi "giữ #id" |
| Thay hoặc bỏ lệnh chờ nhưng lệnh cũ vẫn `LOGGED` và vẫn được chấm điểm | `desk cancel-call ID` trước khi ghi lệnh thay |
| Lọc lệnh cũ theo `expires_at`, coi lệnh limit đã khớp là lệnh chờ rồi hủy hoặc quên nó (#28 HYPE khớp 31/10 mà vẫn `LOGGED`, `outcome` null) | Đọc `filled_at`: có giờ là vị thế đang chạy, không hủy, báo giữ hay đóng sớm |
| Desk báo đủ lệnh trong 24 giờ, đổi số cho khác để ghi bằng được | Bỏ lệnh yếu nhất, hoặc hủy lệnh bị thay rồi ghi lại |

