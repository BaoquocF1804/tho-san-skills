# Bẫy số liệu cổ phiếu (thợ săn cổ phiếu)

Ghi lại từ các lượt săn 27/10–14/11/2026. Đọc trước khi viết mục **Cơ bản & KQKD** và trước khi đặt lệnh chờ.

## Báo cáo tài chính
- Trước khi kết luận lợi nhuận hay biên lợi nhuận sụp, đọc Exhibit 99.1 của 8-K KQKD để tìm khoản bất thường.
  - Meta "biên 40→20%" thật ra là khoản phí pháp lý 9,89 tỷ USD; bỏ khoản đó thì còn khoảng 35%.
  - Lợi nhuận ròng Alphabet −24% là do lỗ 8,7 tỷ USD trên chứng khoán nắm giữ, trong khi lãi hoạt động +30%.
  - Cách lấy: bỏ tên file khỏi link SEC trong `news` để có thư mục hồ sơ, rồi mở file `*exhibit99*.htm`. WebFetch đọc được; curl có thể bị SEC trả "Undeclared Automated Tool".
- Cột `GP/Op` trong bảng quý SEC là lãi gộp nếu công ty có báo, không thì là lãi hoạt động. Đừng so biên giữa hai công ty hay gọi "biên sụp" từ cột này.
- Số quý mới nhất của TradingView trễ sau bản tin KQKD vừa ra (APP: script ghi doanh thu +52,8%, bản tin +55%). Dán dòng `TG:` nguyên văn rồi ghi số thật trong báo cáo.
- P/E có thể sai sau lãi bất thường (GOOGL P/E 14,8 nhờ hai quý lãi ròng phình to). Lãi ròng +264% có thể chỉ vì quý gốc thấp.

## Hồ sơ SEC
- 8-K không có dấu `!` vẫn có thể là chất xúc tác: Item 8.01/7.01 hay chứa đợt phát hành nợ, bán cổ phiếu kỳ hạn, trái phiếu chuyển đổi. Với mã đã vào shortlist, mở các 8-K 8.01.
- Dòng `6-K ?`: công ty nước ngoài nộp 6-K cho mọi việc (doanh thu tháng, KQKD, thông báo). Mở để biết nội dung.
- Script ghi `SEC không trả lời` thì mở EDGAR bằng WebFetch.

## Giá và giờ giao dịch
- Nến ngày của hợp đồng là ngày UTC, gồm cả giờ sau phiên, nên giá "đóng cửa" của hợp đồng khác giá đóng cửa thật (AVGO 29/10: 335,97 so với 345,00). Giá đóng cửa thật lấy từ lịch sử Yahoo hoặc Exa "<MÃ> stock <ngày>".
- Lệnh limit 24 giờ đặt thứ Bảy hoặc Chủ nhật hết hạn trước khi sàn cơ sở nào mở cửa (Hàn Quốc mở 07:00 thứ Hai giờ VN). Vì vậy chỉ lệnh trong khoảng 1% quanh mark mới khớp được. Riêng mã `PRE` (OPENAI, ANTHROPIC) có giao dịch thật cuối tuần.
- Lệnh bán chờ phía trên giá, đặt trước một tin vĩ mô Mỹ, chỉ khớp khi tin tốt (CPI ra lúc 20:30 giờ VN, trước giờ mở cửa 21:30). `plan` đã hạ trần xuống B; ghi rõ vào **Phản biện**.
- Lệnh limit hết hạn mà vẫn để trên sàn có thể khớp sau đó. Khi người dùng hỏi, kiểm nến 1h cả sau mốc 24 giờ.
- Người dùng đặt lệnh trên OKX. OKX niêm yết 186/227 hợp đồng cổ phiếu của Binance (15/11), nhưng volume chỉ khoảng 1/8. Script lấy nến từ Binance, nên Binance dừng giao dịch thì không săn được dù OKX vẫn chạy: chỉ quản lý lệnh đang mở trên OKX bằng stop theo Mark Price.

## Dựng setup
- Mã vốn hóa lớn có đỉnh/đáy dày đặc (MSFT 486–510, AAPL 321–358) có thể không có stop hợp lệ ở R:R ≥ 1,5. Chạy `stops` trước khi tốn công phân tích.
- Giá hợp đồng `PRE` xấp xỉ định giá tính bằng tỷ USD (Binance ước tính số cổ phiếu). Vòng gọi vốn mới (OpenAI 1.250 tỷ USD) neo giá.
- Ngày KQKD: tìm Exa "<công ty> earnings date"; TipRanks ghi "(Confirmed)" khi đã xác nhận. Có ngày xác nhận thì chạy `plan --earnings-date YYYY-MM-DD`.
