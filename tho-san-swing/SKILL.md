---
name: tho-san-swing
description: >-
  Use when the user asks to run or check the swing paper-trading hunter on Binance stock perpetuals — "thợ săn swing", "sổ lệnh giấy", "chạy sổ giấy", "paper trade cổ phiếu", "swing RSI2 Turtle", "lệnh giấy hôm nay thế nào" — or asks about that paper portfolio's positions, profit or comparison with buy-and-hold. Not for real orders, crypto hunts (tho-san) or the discretionary stock hunt (tho-san-co-phieu).
---

# Thợ săn Swing (sổ lệnh giấy)

## Tổng quan
Chạy thử bằng sổ lệnh giấy hai chiến lược đã backtest trên hợp đồng cổ phiếu Mỹ của Binance: **RSI(2) của Connors** (mua lúc mở cửa phiên sau) và **Turtle hệ 2**. **Không bao giờ đặt lệnh thật.**
- Mọi con số lấy từ [`swing_paper.py`](./scripts/swing_paper.py).
- Sổ lệnh nằm ở `~/.local/share/tho-san-swing/ledger.json`; không sửa tay.

## Luật (cố định, không tự chỉnh)
| | RSI(2) | Turtle hệ 2 |
|---|---|---|
| Vào | Đóng cửa > SMA200 và RSI(2) < 5 → mua lúc mở cửa 09:30 New York phiên sau | Lệnh dừng mua khi giá vượt đỉnh 55 phiên (hợp đồng Binance chạy 24/7) |
| Thoát | Đóng cửa > SMA5 → bán lúc mở cửa phiên sau | Giá thủng max(giá vào − 2N, đáy 20 phiên), N = ATR 20 phiên |
| Vị thế | Tối đa 10, mỗi vị thế 5% vốn | Tối đa 10, mỗi vị thế 5% vốn |

- **Danh sách mã:** hợp đồng cổ phiếu Mỹ trên Binance, không gồm ETF, khối lượng trung vị ≥ 1 triệu USDT/ngày.
- **Chi phí:** phí 0,05% taker cộng 0,02% trượt giá mỗi chiều, cộng funding thật.
- **Mốc so sánh:** giữ đều các mã từ ngày bắt đầu sổ.
- **Backtest gốc:** `~/vintage_book/nill-backtest/results/swing.md`.

## Quy trình
`swing_paper.py` dưới đây là `python3 ~/.gemini/config/skills/tho-san-swing/scripts/swing_paper.py`.

1. Chạy `swing_paper.py scan` (1–3 phút). Sổ chưa có thì tạo với `--capital` (mặc định 1000 USDT).
   - Script tự xử lý mọi phiên đã đóng cửa chưa xử lý: khớp lệnh bằng giá Binance thật, xếp lệnh cho phiên tới, in báo cáo.
   - Chạy lúc nào cũng được: phiên đang mở bị bỏ qua.
2. Dán nguyên văn báo cáo vào khung chat. Không gõ lại hay tự tính con số.
3. Gửi Telegram:
   - Lệnh: `hermes send --to telegram --subject "📒 Thợ săn Swing <dd/mm>" --file <TG_FILE>`. Đường dẫn file nằm ở dòng `TG_FILE:` cuối báo cáo.
   - Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục.
   - Người dùng nói "không gửi" thì bỏ bước này.
4. Chỉ xem sổ, không xử lý phiên mới: `swing_paper.py status`.

## Lỗi thường gặp
| Lỗi | Cách đúng |
|---|---|
| Đặt lệnh thật theo báo cáo, hoặc ghi vào desk bằng `desk log-call` | Skill này chỉ ghi sổ giấy |
| Tự thêm hoặc sửa lệnh, đổi ngưỡng RSI hay số vị thế | Luật cố định để đánh giá. Muốn đổi thì backtest lại trước (`~/vintage_book/nill-backtest/swing.py`) |
| Sửa tay `ledger.json` | Không sửa. Dữ liệu sai thì báo người dùng |
| Chạy `scan` nhiều lần mong có lệnh mới | Mỗi phiên chỉ xử lý một lần; chạy lại chỉ in lại báo cáo |
| Kết luận chiến lược tốt hay xấu sau vài tuần | Cần ít nhất 2–3 tháng, luôn so với dòng "giữ đều các mã cùng kỳ" |
| Gõ lại con số vào Telegram | Gửi nguyên file `TG_FILE` |
| Báo "Turtle canh" ít mã hẳn so với thường lệ (thường gần 80 mã) | Yahoo hoặc Binance lỗi giữa chừng: báo người dùng, chạy lại sau |
