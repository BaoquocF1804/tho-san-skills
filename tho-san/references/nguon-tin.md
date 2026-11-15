# Nguồn tin và bẫy số liệu (thợ săn crypto)

Ghi lại từ các lượt săn 25/10–15/11/2026. Trang nào hỏng thì thử trang kế tiếp; đọc tuần tự, không gọi song song.

## Khi Exa (`agent-reach web search`) bị chặn
- Có ngày Exa chặn ngay sau 2 lượt tìm và cả kênh `web` dừng khoảng 1 giờ. Gặp `RATE_LIMITED` thì thôi dùng Exa trong lượt săn đó; chuyển sang RSS và các trang dưới đây (WebFetch, hoặc `curl -A Mozilla` rồi bỏ thẻ HTML).
- RSS đọc được bằng feedparser: CoinDesk, Cointelegraph, The Block, Decrypt, CryptoSlate, CryptoPotato, U.Today, CNBC, BBC, Al Jazeera, NYT, Guardian, OilPrice. WSJ và Investing hay trả 0 bài. BeInCrypto chặn cả curl lẫn WebFetch: chỉ trích tiêu đề từ RSS.
- WebFetch bị chặn: bbc.co.uk, theguardian.com, apnews.com, beincrypto.com. Farside nằm sau Cloudflare.

## Bản đồ thanh lý
| Trang | Cho gì | Ghi chú |
|---|---|---|
| swiftedge.uk/btc/liquidation-heatmap | bảng cụm BTC trên/dưới kèm số tiền, tổng ±1/2/5% | bảng nằm sau "Largest clusters above price"; độ chính xác của chính trang chỉ ngang việc dự đoán bằng chuyển động giá, coi là bằng chứng yếu |
| cryptokeyhole.com/ethereum-liquidation-heatmap/ | 5 vùng dày nhất mỗi phía, tổng ±5/10/15% | WebFetch có lúc lỗi: dùng curl |
| coinperps.com/{solana,hype,xrp}-liquidation-heatmap | mức chính và tổng ±1/2/3/5% | xem dấu "updated": có khi cũ 18–31 giờ, ghi rõ trong báo cáo |
| alphafinance.io/liquidation-heatmap/bitcoin/, pumpglass.com/heatmap/BTCUSDT | cụm BTC | đọc qua Exa hoặc WebFetch |
| liqflow.app/coin/{BTC,ETH} | tổng cộng dồn ở ±2/5/10% | không phải cụm: đọc khoảng chênh giữa các bậc |

Bản đồ đổi chiều trong vài giờ (29/10: BTC từ 653 triệu USD long bên dưới thành 588 triệu USD short bên trên). Đọc lại trước khi quản lý vị thế đang mở.

## Dòng tiền ETF
- Số cuối cùng: Farside (qua Cointelegraph hoặc CoinDesk), SoSoValue. alphafinance.io/etf/{bitcoin,ethereum}/ ra sớm nhưng là số tạm khi còn quỹ "pending"; khi đó báo phiên trước và nói phiên mới nhất chưa đủ.
- Số "thứ Sáu" đăng sớm (Economic Times trích OwlChart) là số tạm trước khi IBIT báo. Bài ETF của Phemex đăng trước phiên Mỹ, nên "hôm nay" của họ là phiên trước.
- cryptokeyhole.com/etf-flows/ (thêm /ethereum/, /solana/): từng quỹ theo ngày.

## Lịch sự kiện
- cryptokeyhole.com/crypto-calendar/: FOMC, CPI, việc làm, đáo hạn quyền chọn kèm max pain, unlock, giờ UTC. Trong text đã bỏ thẻ, danh sách sự kiện bắt đầu ở chữ "This week" thứ hai.
- basecamp.markets (tuần tới, giờ UTC), bls.gov/schedule (CPI, việc làm).
- Tin 8:30 New York là 19:30 giờ VN khi Mỹ theo giờ mùa hè, 20:30 khi hết giờ mùa hè (từ Chủ nhật đầu tháng 11).
- Messari, Tokenomist và RootData tính unlock theo toàn bộ phần phân bổ, nên con số bị thổi phồng. Ví dụ HYPE: phần trả cho đội ngũ ngày 6 hằng tháng thật ra khoảng 180.000 HYPE, không phải hàng tỷ USD.

## Kiểm tra nhanh
- Limit đã khớp chưa, khớp lúc nào: `https://fapi.binance.com/fapi/v1/klines?symbol=X&interval=5m&startTime=<created_at ms>`, lấy min/max. Lưu ý nến 1h với `startTime` giữa giờ bắt đầu từ giờ tròn kế tiếp.
- Sàn gặp sự cố: so `premiumIndex` của Binance với OKX (`/api/v5/market/ticker?instId=X-USDT-SWAP`) và Bybit (`/v5/market/tickers?category=linear`). Sàn bị tấn công thì đứng ngoài dù setup đạt.
- Tư vấn vị thế thật: nhắc người dùng kiểm lệnh SL còn trên sàn. So `markPriceKlines` với `klines` để biết stop theo giá mark hay theo giá khớp sẽ chạy.
- Trong `detail`, OI 1d, L/S pct30, top và taker là số theo ngày, chỉ đổi lúc 00:00 UTC.
- Limit mua vào hỗ trợ trước sự kiện: điều kiện hủy kiểu "nến 4h đóng dưới X" không cứu được cú sập trong một nến. Dùng điều kiện giá ("hủy nếu BTC chạm X").
