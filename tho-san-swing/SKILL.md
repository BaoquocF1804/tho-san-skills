---
name: tho-san-swing
description: >-
  Use when the user asks to run or check the swing paper-trading hunter on Binance stock perpetuals — "thợ săn swing", "sổ lệnh giấy", "chạy sổ giấy", "paper trade cổ phiếu", "swing RSI2 Turtle", "lệnh giấy hôm nay thế nào" — or asks about that paper portfolio's positions, profit or comparison with buy-and-hold. Not for real orders, crypto hunts (tho-san) or the discretionary stock hunt (tho-san-co-phieu).
---

# Thợ săn Swing (sổ lệnh giấy)

## Tổng quan
Chạy thử bằng sổ lệnh giấy hai chiến lược đã backtest trên hợp đồng cổ phiếu Mỹ của Binance: **RSI(2) của Connors** (mua lúc mở cửa phiên sau) và **Turtle 20/10**. **Không bao giờ đặt lệnh thật.**
- Mọi con số lấy từ [`swing_paper.py`](./scripts/swing_paper.py).
- Sổ lệnh nằm ở `~/.local/share/tho-san-swing/ledger.json`; không sửa tay.

## Luật (cố định, không tự chỉnh)
| | RSI(2) | Turtle 20/10 |
|---|---|---|
| Vào | Đóng cửa > SMA200 và RSI(2) < 5 → mua lúc mở cửa 09:30 New York phiên sau | Lệnh dừng mua khi giá vượt đỉnh 20 phiên (trong phiên 09:30–16:00 New York) |
| Thoát | Đóng cửa > SMA5 → bán lúc mở cửa phiên sau | Giá thủng max(giá vào − 2N, đáy 10 phiên), N = ATR 20 phiên |
| Vị thế | Tối đa 10, mỗi vị thế 7,5% vốn | Tối đa 10, mỗi vị thế 7,5% vốn |

- **Danh sách mã:** hợp đồng cổ phiếu Mỹ trên Binance, không gồm ETF, khối lượng trung vị ≥ 1 triệu USDT/ngày.
- **Chi phí:** phí 0,05% taker cộng 0,02% trượt giá mỗi chiều, cộng funding thật.
- **Mốc so sánh:** giữ đều các mã từ ngày bắt đầu sổ.
- **Backtest gốc:** `~/vintage_book/nill-backtest/results/swing.md`.
- **Nâng cấp 08/11/2026:** Turtle 20/10 thay 55/20, vì tốt hơn ở cả 4 giai đoạn backtest. Chi tiết ở `~/vintage_book/nill-backtest/results/swing-upgrade.md`.
- **Cỡ lệnh 08/11/2026:** 7,5% mỗi vị thế thay 5%, tổng tối đa 150% vốn, theo lựa chọn của người dùng. Trong backtest, lãi và mức sụt cùng tăng 1,5 lần, Sharpe giữ nguyên. Chi tiết ở `~/vintage_book/nill-backtest/results/swing-upgrade-2.md`.
- **Đã thử và loại (vòng 2):** giới hạn 2 lệnh RSI(2) cùng ngành hoặc cùng nhịp giá, dừng lỗ RSI(2) 10%. Không cải thiện Sharpe ở cả 2006–2015 và 2016–2024.

## Quy trình
`swing_paper.py` dưới đây là `python3 ~/.gemini/config/skills/tho-san-swing/scripts/swing_paper.py`.

1. Chạy `swing_paper.py scan` (1–3 phút). Sổ chưa có thì tạo với `--capital` (mặc định 1000 USDT).
   - Script tự xử lý mọi phiên đã đóng cửa chưa xử lý: khớp lệnh bằng giá Binance thật, xếp lệnh cho phiên tới, in báo cáo.
   - Chạy lúc nào cũng được: phiên đang mở bị bỏ qua.
2. Dán nguyên văn báo cáo vào khung chat. Không gõ lại hay tự tính con số.
3. Gửi Telegram:
   - Lệnh: `hermes send --to telegram --file <TG_FILE>`. Đường dẫn file nằm ở dòng `TG_FILE:` cuối báo cáo, và dòng đầu của file đã là tiêu đề.
   - Exit khác 0 thì báo người dùng kèm lỗi, không thử lại liên tục.
   - Người dùng nói "không gửi" thì bỏ bước này.
   - Báo cáo ghi "Chưa có phiên mới" thì không gửi: phiên đó đã được gửi lúc được xử lý.
4. Chỉ xem sổ, không xử lý phiên mới: `swing_paper.py status`.

## Chạy tự động
- **Đang tắt từ 14/11/2026** theo yêu cầu người dùng. Crontab không còn dòng `tho-san-swing`, nên sổ chỉ chạy khi gọi `scan` bằng tay; lượt `scan` kế tiếp tự bù các phiên đã lỡ. Chỉ bật lại khi người dùng bảo: `(crontab -l 2>/dev/null; cat ~/.local/share/tho-san-swing/crontab.bak-20261114) | crontab -`.
- Khi bật, cron trong WSL chạy `bash scripts/cron_scan.sh` vào phút thứ 7 mỗi giờ.
  - Script chỉ thật sự xử lý mỗi phiên Mỹ một lần, sau giờ đóng cửa, và gửi Telegram đúng một lần cho phiên đó.
  - WSL hoặc máy tắt thì lượt chạy kế tiếp tự bù các phiên bị lỡ.
  - Quét lỗi 3 lần liền thì gửi một tin cảnh báo ⚠️; vẫn lỗi thì cứ 24 lần, khoảng mỗi ngày, nhắc lại.
  - Tin Telegram gửi hỏng được giữ trong `tg_pending` và gửi lại ở lượt sau.
- Log: `~/.local/share/tho-san-swing/cron.log`. Tự kiểm tra script cron (scan và hermes giả, không gửi gì): `bash scripts/test_cron_scan.sh`.
- Xem lịch: `crontab -l`. Tắt: xoá dòng `tho-san-swing` bằng `crontab -e`.

## Lỗi thường gặp
| Lỗi | Cách đúng |
|---|---|
| Đặt lệnh thật theo báo cáo, hoặc ghi vào desk bằng `desk log-call` | Skill này chỉ ghi sổ giấy |
| Tự thêm hoặc sửa lệnh, đổi ngưỡng RSI hay số vị thế | Luật cố định để đánh giá. Muốn đổi thì backtest lại trước (`~/vintage_book/nill-backtest/swing.py`) |
| Sửa tay `ledger.json` | Không sửa. Dữ liệu sai thì báo người dùng |
| Chạy `scan` nhiều lần mong có lệnh mới | Mỗi phiên chỉ xử lý một lần; chạy lại chỉ in lại báo cáo |
| Kết luận chiến lược tốt hay xấu sau vài tuần | Cần ít nhất 2–3 tháng, luôn so với dòng "giữ đều các mã cùng kỳ" |
| Gõ lại con số vào Telegram | Gửi nguyên file `TG_FILE` |
| Gửi Telegram lần nữa sau khi chạy tay một phiên cron đã xử lý | Chỉ gửi khi báo cáo có phiên mới |
| Báo "Turtle canh" ít mã hẳn so với thường lệ (thường gần 80 mã) | Yahoo hoặc Binance lỗi giữa chừng: báo người dùng, chạy lại sau |
