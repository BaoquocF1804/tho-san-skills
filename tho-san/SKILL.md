---
name: tho-san
description: >-
  Use when the user asks to hunt for crypto futures trades or calls — "đi săn", "săn lệnh", "săn kèo", "thợ săn", "có kèo nào không", "tìm lệnh long/short" — or wants a manual Binance USDⓈ-M LONG/SHORT scan of crypto perpetuals with entry, stop, target and position size done by the agent itself rather than by automated hunter code. Not for stock perpetuals (that is tho-san-co-phieu).
---

# Thợ săn Futures (săn tay)

## Tổng quan
Tự săn lệnh crypto trên Binance USDⓈ-M: dữ liệu mới từ script [`hunt_data.py`](./scripts/hunt_data.py), tin tức có ngày từ agent-reach, tự phân tích, báo cáo tiếng Việt. Mọi con số lấy từ script ngay lúc báo cáo; mọi tin có ngày và nguồn; không có lệnh hạng A thì nói thẳng. Chỉ phân tích, không đặt lệnh; báo cáo xong thì gửi lên Telegram qua Hermes.

Người dùng đặt lệnh trên **OKX**. Dữ liệu phân tích vẫn lấy từ Binance (thị trường dày nhất), còn mọi lệnh của script chỉ nhận mã đặt được trên OKX và tính size theo hợp đồng OKX (`okx_gate.py` ở gốc repo skills).

## Khung rủi ro (mặc định; dùng số người dùng nói nếu khác)
| Tham số | Giá trị |
|---|---|
| Đòn bẩy | x5 mặc định. Mã cờ `OKxN` (ATR quá rộng cho x5) chạy `stops` / `plan` với `--leverage N`; dòng `TG:` Size sẽ ghi `(xN)`. Rủi ro vẫn 1% vốn vì size tính theo khoảng cách stop; đòn bẩy thấp chỉ tốn thêm ký quỹ. Người dùng nói số khác thì truyền `--leverage` |
| Vốn | 1000 USDT (`--capital`) |
| Rủi ro mỗi lệnh | 1% vốn |
| Ký quỹ tối đa mỗi lệnh | 20% vốn |
| Stop | ≥ 1 ATR14 ngày, ≤ `(1/đòn bẩy − mmr)/2` (8,75% ở x5) và cách mọi đỉnh/đáy ngày ≥ 0,25 ATR (`plan` tự kiểm: sát swing 120 ngày hoặc đỉnh/đáy 2 ngày gần nhất thì `FAIL`; sát đỉnh/đáy bất kỳ trong 20 ngày thì `WARN` và hạ trần hạng) |
| R:R gộp | ≥ 1,5 (script kèm thêm `net R:R` sau phí taker 2 chiều 0,10%) |
| Vào ngay | entry trong ±0,5% giá mark; xa hơn là lệnh chờ (`limit` nếu chờ hồi, `stop` nếu đánh phá vỡ) |
| Xu hướng thị trường | `plan` FAIL lệnh LONG khi BTC đóng cửa ngày gần nhất dưới EMA20, FAIL lệnh SHORT khi trên EMA20; dòng `Xu hướng` của `scan` cho biết chiều nào được dựng. Lý do: 25/10–21/11 cả 2 lệnh LONG đã chấm đều thua, TRX còn đang −0,82R, trong khi SHORT thắng 9/12 |
| Lệnh chờ | Hiệu lực **72 giờ** trên desk (`hunter.tho_san_ttl_hours`). Lý do: 25/10–21/11 chỉ 11/39 lệnh chờ khớp trong 24 giờ, tới 72 giờ thì khớp 24/39, phần lớn chạm TP |
| Tầm nhìn | ≤ 20 ngày; tối đa 3 lệnh đang mở (chờ khớp cộng đã khớp chưa chấm xong; desk từ chối lệnh thứ 4) |
| Hạng | `plan` in `Hạng tối đa`. Là B khi stop dính `WARN`, khi lệnh chờ có 72 giờ hiệu lực trùm một sự kiện vĩ mô Mỹ (CPI, PPI, việc làm, FOMC; lịch nằm ở `macro_events.json`, gốc repo skills), hoặc khi entry chờ cách mark hơn 1 ATR. Báo cáo được hạ hạng, **không được nâng** |

## Quy trình
1. **Dữ liệu:** `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py scan` (khoảng 15 giây, 40 hợp đồng lớn nhất). Săn mã cờ `OK` (x5) và `OKxN` (dùng `--leverage N`). Bỏ `ATR` (quá biến động kể cả ở x2, hoặc mã mới chưa đủ 15 nến ngày) và `PUMP` (vừa pump hoặc funding cực đoan).
   - Dòng `Xu hướng` (ngay sau dòng tóm tắt): BTC đóng cửa ngày so với EMA20. `chỉ SHORT` nghĩa là `plan` FAIL mọi lệnh LONG, `chỉ LONG` thì ngược lại; chỉ dựng setup theo chiều được phép.
   - Bảng chỉ còn mã đặt được trên OKX: cùng tên, cùng loại coin, giá OKX lệch Binance ≤ 1%, volume OKX 24h ≥ 2 triệu USD (`--okx-min-qv`). Bị loại: mã chỉ có trên Binance (DODOX, KAVA, XMR…), hợp đồng 1000x của Binance (1000PEPE, 1000SHIB, 1000BONK…), và mã trùng tên một cổ phiếu trên OKX (BB, ON, QNT).
2. **Tin tức. REQUIRED SUB-SKILL:** agent-reach.
   - Đọc [references/nguon-tin.md](references/nguon-tin.md) trước: các trang đọc được khi Exa bị chặn (bản đồ thanh lý, ETF, lịch sự kiện) và các bẫy số liệu đã gặp.
   - Chạy `agent-reach doctor --text` trước.
   - Tìm bằng `agent-reach web search "..." --limit 5` (Exa) **tuần tự, cách nhau khoảng 15 giây**; đọc bài chính bằng `agent-reach web read <url>`; quét RSS rộng bằng `uv run -q --no-project --with feedparser python3` (feedparser lấy được ngày và link từng bài). Twitter/Reddit chỉ dùng khi doctor không báo `not_added`. agent-reach lỗi thì dùng web search có sẵn của runtime (`WebSearch` trên Claude Code, `search_web` trên Gemini).
   - Phải có đủ bốn nhóm, mỗi tin có ngày (bỏ tin không ngày):
     - vĩ mô và địa chính trị 48 giờ qua (dầu, chiến sự, Fed và ngày họp FOMC kế tiếp)
     - dòng tiền ETF BTC/ETH ngày gần nhất, bản đồ thanh lý BTC/ETH (cụm long/short; với altcoin không có bài heatmap trong ngày thì dùng vùng swing high/low kết hợp OI để ước lượng vùng quét stop)
     - lịch sự kiện 2 tuần tới: mở khóa token, nâng cấp, FOMC
     - tin riêng từng mã trong shortlist (OI kỷ lục, hack, unlock, ETF)
3. **Soi kỹ 3–6 mã:** `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py detail SYM1 SYM2 ...` (mức hỗ trợ/kháng cự đã gom cụm 0,25 ATR và tính cả S/R flip, vị thế nhỏ lẻ và top trader, nến hôm nay, nến 4h).
   - Dòng `OKX <hợp đồng>`: giá OKX so với Binance, volume 24h trên OKX, 1 hợp đồng bằng bao nhiêu coin, đòn bẩy tối đa.
   - Dòng `OKX crowd 100d`: OI, L/S nhỏ lẻ, top trader và taker của riêng OKX trong 100 ngày (`pct100` là phân vị 100 ngày), cùng funding OKX, tức khoản người dùng thực trả. Ngày OKX bắt đầu lúc 16:00 UTC (0h giờ Hồng Kông), nên dòng mới nhất là ngày đang chạy. Dòng vị thế Binance (`pct30`) vẫn là đám đông lớn nhất; dòng OKX cho biết đám đông trên chính sàn đặt lệnh.
4. **Dựng setup theo chiều dòng `Xu hướng` cho phép:** hồi về hỗ trợ trong xu hướng; phá vỡ hoặc thủng mức có OI và taker xác nhận; đảo chiều khi đòn bẩy quá nóng (OI tăng mạnh, funding cao, nhỏ lẻ dồn một phía, top trader phía kia); catalyst có ngày. Stop đặt ở mức luận điểm sai **và** vượt qua cụm thanh lý / đỉnh đáy quét stop gần đó; target ở mức cấu trúc (hỗ trợ, kháng cự, EMA).
   - Dò stop bằng `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py stops LONG|SHORT SYM [--span 0.07] [--step 0.005]`, đừng viết script dò riêng. Lệnh này in, cho từng entry tính từ mark, mức stop chặt nhất mà `plan` cho qua. Mục tiêu 1,5R/2R đi kèm chỉ để tham chiếu. `WARN near` là đỉnh/đáy 20 ngày gần ngay sát stop.
5. **Kiểm từng lệnh ngay trước khi báo:** `python3 ~/.gemini/config/skills/tho-san/scripts/hunt_data.py plan LONG|SHORT SYM --stop X --target Y [--entry E] [--capital C]`. `FAIL` thì sửa mức hoặc bỏ lệnh; entry xa mark là lệnh chờ (`limit` hoặc `stop` theo output của script). Lệnh vào ngay khớp quanh mark, nên `plan` tính rủi ro từ giá xấu hơn giữa entry và mark. `PASS` thì `plan` in `Hạng tối đa`, sẵn 3 dòng `TG:` (tiêu đề; Vào/Stop/TP/R:R; Size/Ký quỹ/Rủi ro/Thanh lý) và dòng `DESK:`. Báo cáo dán nguyên văn các dòng `TG:` (bỏ tiền tố `TG: `), kể cả `(tối đa hạng B)` ở dòng đầu; desk chạy đúng dòng `DESK:`. Không gõ lại con số nào.
   - `plan` và `stops` từ chối mã không đặt được trên OKX (`không đặt được trên OKX`): bỏ mã đó.
   - Dòng Size tính theo **số hợp đồng OKX**, ví dụ `0.9 hợp đồng ETH-USDT-SWAP (0.09 ETH ≈ 157.95 USDT)`; người dùng đặt đúng số hợp đồng này trên OKX. Gặp `FAIL size >= OKX minimum` hoặc `FAIL … OKX max leverage` thì đổi đòn bẩy hoặc bỏ lệnh.
   - Dòng `DESK:` vẫn dùng mã Binance, vì desk chấm điểm theo nến Binance (giá hai sàn thường lệch 0,03–0,05%).
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
     - `Error: Đã có ... lệnh tho-san đang mở`: đủ 3 lệnh đang mở. Hủy lệnh chờ yếu nhất (`desk cancel-call ID`) rồi chạy lại, hoặc đưa lệnh này vào **Đã loại** với lý do đủ 3 lệnh.
   - Lệnh chờ kiểu `stop` không có dòng `DESK:` vì desk chưa chấm được; báo cáo ghi "chưa ghi desk". Desk không có lệnh này, nên lượt săn sau lấy nó từ mục Lệnh chờ của báo cáo gần nhất trong `~/.local/share/tho-san/` và kiểm khớp bằng nến 5m.
   - Kết quả xem bằng `desk scorecard`, dòng `tho-san`.

## Báo cáo (tiếng Việt)
Báo cáo là đúng khung dưới đây: các mục này, theo thứ tự này. Chữ trong `<...>` là chỗ điền; mục không có gì thì ghi "Không có.". Bối cảnh tối đa 5 dòng, mỗi dòng có ngày. Hạng của mỗi lệnh không vượt `Hạng tối đa` mà `plan` in ra.

```markdown
**Kết luận:** <có / không có> lệnh hạng A; <n> lệnh vào ngay, <m> lệnh chờ, <k> lệnh cũ đang chạy.

## Bối cảnh
- <dd/mm>: <một ý> (<nguồn>)

## Lệnh vào ngay
### <dòng TG: đầu của plan, bỏ "TG: "> #<id desk>
<dòng TG: thứ hai, nguyên văn, bỏ "TG: ">
<dòng TG: thứ ba, nguyên văn, bỏ "TG: ">
- **Lý do:** <...>
- **Phản biện:** <lý do của `Hạng tối đa: B` nếu có> <...>
- **Sai nếu:** <mức đóng sớm hoặc hủy>

## Lệnh chờ (hiệu lực 72 giờ)
<mỗi lệnh trình bày như trên; lệnh kiểu stop ghi "chưa ghi desk" thay cho #id>

## Lệnh cũ
- #<id> <MÃ> <chiều>, chờ khớp: <giữ / hủy / thay bằng #id mới>
- #<id> <MÃ> <chiều>, đang chạy, entry <...>, khớp <filled_at>: <giữ / đóng sớm ở mức ...>

## Đã loại
- <MÃ>: <lý do một câu>

## Quản lý rủi ro
- <lệnh cùng chiều là tương quan; sự kiện sắp tới; mức BTC để đóng sớm>

## Nguồn
- <link bài đã dùng>

_Phân tích tham khảo, không phải lời khuyên đầu tư._
```

## Gửi Telegram (mỗi lần săn — bản rút gọn 1 tin nhắn)
- Bản đầy đủ lưu vào `~/.local/share/tho-san/report-<YYYYmmdd-HHMM>.md` và hiển thị trong khung chat. Không lưu ở `/tmp`, vì WSL khởi động lại là mất.
- Bản gửi Telegram lưu riêng vào `~/.local/share/tho-san/tg-<YYYYmmdd-HHMM>.md` (**tối đa ~2500 ký tự, gọn trong 1 tin nhắn duy nhất (Telegram cắt ở 4096), không dùng bảng Markdown, không kèm danh sách link URL và danh sách mã đã loại**):
  - **Dòng đầu:** Kết luận ngắn (số lệnh vào ngay / lệnh chờ).
  - **Bối cảnh:** tối đa 3 gạch đầu dòng, mỗi dòng 1 câu ngắn kèm ngày.
  - **Mỗi lệnh (vào ngay hoặc chờ):**
    - 3 dòng `TG:` của `plan`, nguyên văn, bỏ tiền tố `TG: `; thêm ` #id` desk vào cuối dòng đầu
    - `• Lý do: <1 câu ngắn>`
    - `• Sai nếu: <mức đóng sớm / hủy lệnh>`
  - **Lệnh cũ** (từ desk, bước 6): mỗi lệnh 1 dòng; lệnh chờ: giữ / hủy / thay kèm #id; lệnh đang chạy: #id đã khớp, giữ hay đóng sớm ở mức nào.
  - **Quản trị rủi ro:** 1–2 dòng (tối đa mấy lệnh cùng lúc, mốc BTC đóng sớm, giờ sự kiện lớn).
- Kiểm `wc -m ~/.local/share/tho-san/tg-<...>.md` ≤ 2500 rồi gửi bằng lệnh:
  `hermes send --to telegram --subject "🎯 Thợ săn <dd/mm HH:MM>" --file ~/.local/share/tho-san/tg-<...>.md`
- Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục. Người dùng nói "không gửi" thì bỏ bước này.

## Lỗi thường gặp
| Lỗi | Cách đúng |
|---|---|
| Chỉ đọc tiêu đề RSS hoặc web search không ngày, bỏ sót chiến sự và unlock | Đủ bốn nhóm tin ở bước 2, có ngày |
| Gọi Exa song song, bị `RATE_LIMITED` | Tuần tự, cách khoảng 15 giây; bị chặn thì đợi `retry_after_seconds` rồi thử lại, tối đa 3 lần |
| Stop vừa đủ 1 ATR, giá chạy làm còn 0,99 ATR | Chạy lại `plan` với giá mới ngay trước khi báo |
| Stop nằm sát đỉnh/đáy ngày hoặc ngay dưới cụm thanh lý (`plan` FAIL `stop >= 0.25 ATR from daily highs/lows`) | Dời stop qua hẳn mọi mức trong `too close` và cụm thanh lý; R:R không còn đủ thì bỏ lệnh, không ép stop sát lại |
| Gọi "stop sạch" khi `plan` in `WARN … (near: …)` (BTC 13/11: stop 77.450 nằm giữa đỉnh/đáy ngày 77.060–77.868 của vùng 30/10–03/11) | `WARN` không chặn lệnh nhưng hạ trần xuống B. Dời stop qua mức đó nếu R:R còn đủ, không thì để hạng B |
| Gọi lệnh là hạng A trong khi dòng `TG:` đầu ghi `(tối đa hạng B)` (lệnh chờ trùm PPI/CPI/FOMC, hoặc cách mark hơn 1 ATR) | Hạng ≤ `Hạng tối đa`; chép lý do vào **Phản biện** |
| Viết lại script dò stop/entry trong scratchpad mỗi lần săn | `hunt_data.py stops` |
| Nói "gãy", "thủng", "bị từ chối" khi mark chỉ tạm vượt mức, hoặc đọc nến 4h `LIVE` như nến đã đóng | Chỉ tính trên nến ngày/4h đã đóng; nến `LIVE` là nến đang chạy |
| Coi funding 0,0100% là long quá nóng; gọi `avg last 21` là trung bình 30 ngày | 0,01%/8h là mức mặc định của Binance (trung tính); `avg last 21` là 21 kỳ, tức 7 ngày với kỳ 8h |
| Mục bản đồ thanh lý chỉ ghi số tiền đã bị thanh lý | Ghi mức giá các cụm long/short đang chờ, rồi đặt stop vượt các cụm đó |
| Chọn mã vừa pump vì ATR nến đóng còn nhỏ | Bỏ mã flag `PUMP` |
| Bỏ mã `OKxN` vì nghĩ là "quá biến động", hoặc chạy `plan` ở x5 cho mã `OKx3` | `OKxN` vẫn săn được: chạy `stops` / `plan` với `--leverage N` và dán dòng Size có `(xN)` |
| Mở báo cáo bằng bối cảnh, thêm bảng quét rổ hay bảng tổng hợp lệnh (báo cáo 15/11 08:17) | Dòng đầu là **Kết luận:**; điền đúng khung ở mục Báo cáo |
| Đặt lệnh chờ đánh thủng đáy nhưng ghi là `limit bán` | Đánh thủng đáy (SHORT dưới giá mark) hoặc vượt đỉnh (LONG trên giá mark) phải là lệnh `stop` |
| Ba lệnh cùng chiều không cảnh báo | Nêu tương quan, khuyên tối đa 2 lệnh |
| Bịa số hoặc mức giá | Chỉ dùng số từ script và bài có nguồn |
| Đề xuất mã chỉ có trên Binance, hoặc tự quy đổi size từ coin sang hợp đồng | Chỉ chọn mã có trong bảng `scan`; `plan` chặn mã không có trên OKX; dán nguyên dòng Size (đã là số hợp đồng OKX) |
| Gõ lại số vào báo cáo, Telegram hoặc desk (desk ghi stop 2455 khi `plan` đã duyệt 2462) | Dán dòng `TG:`, chạy dòng `DESK:` của lần `plan` cuối |
| Ghi lại lệnh chờ đang giữ thành lệnh mới (#24, #25, #26 là cùng một lệnh ETH) | Desk trả `"duplicate": true` kèm id cũ; báo cáo ghi "giữ #id" |
| Thay hoặc bỏ lệnh chờ nhưng lệnh cũ vẫn `LOGGED` và vẫn được chấm điểm | `desk cancel-call ID` trước khi ghi lệnh thay |
| Lọc lệnh cũ theo `expires_at`, coi lệnh limit đã khớp là lệnh chờ rồi hủy hoặc quên nó (#28 HYPE khớp 31/10 mà vẫn `LOGGED`, `outcome` null) | Đọc `filled_at`: có giờ là vị thế đang chạy, không hủy, báo giữ hay đóng sớm |
| Desk báo đủ lệnh trong 24 giờ, đổi số cho khác để ghi bằng được | Bỏ lệnh yếu nhất, hoặc hủy lệnh bị thay rồi ghi lại |
| Đẩy giá chờ ra xa mark cho đủ R:R 1,5 rồi tưởng lệnh sẽ khớp (25/10–21/11: lệnh chờ cách mark trung vị 0,65 ATR, trong khi 24 giờ giá chỉ hồi trung vị 0,29 ATR; 25/28 lệnh không khớp vẫn chạy về TP) | Lệnh chờ cách mark trên ~0,6 ATR thì ghi vào **Phản biện** là khó khớp; ưu tiên setup có stop và TP cấu trúc cho R:R ≥ 1,5 gần mark |
| Mua bắt đáy khi BTC dưới EMA20 (2/2 lệnh LONG thua, TRX −0,82R) | Theo dòng `Xu hướng`; `plan` FAIL lệnh ngược xu hướng BTC |

