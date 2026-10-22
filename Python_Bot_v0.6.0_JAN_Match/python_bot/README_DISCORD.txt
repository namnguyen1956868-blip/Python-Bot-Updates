PYTHON BOT v0.5.0 - DISCORD AUTO TRIGGER

1. Cài Python 3.10+ trên Windows. Cài thư viện: py -m pip install discord.py
2. Vào https://discord.com/developers/applications -> New Application -> Bot.
3. Bật Message Content Intent trong mục Bot. Mời bot vào server với View Channel và Read Message History.
4. Dùng BOT TOKEN chính thức (không phải Discord user token). Trong PowerShell, chạy:
   [Environment]::SetEnvironmentVariable("PYTHON_BOT_DISCORD_TOKEN", "YOUR_BOT_TOKEN", "User")
   Giữ token bí mật; đóng rồi mở lại Python Bot sau khi thiết lập.
5. Discord -> Settings -> Advanced -> Developer Mode -> Copy Channel ID từ kênh được phép đọc.
6. Python Bot -> Discord -> điền Channel ID, bật 3 tùy chọn, bấm Lưu cài đặt -> Kết nối Discord.
7. Khi tin nhắn MỚI xuất hiện trong kênh đã chọn:
   - Nếu có URL ở nội dung/Discord embed, bot tự thêm tác vụ kiểm tra link.
   - Tin chỉ có chữ vẫn có thể kích hoạt chạy các tác vụ đã được lưu, nếu bật tùy chọn.
   - Tin nhắn từ các notification bot/webhook trong kênh cũng được xử lý.
8. Chỉ chạy khi ứng dụng đang mở và bot Discord được kết nối. Không lấy các thông báo từ Discord Desktop hay đọc tin nhắn cũ.
9. Python Bot chỉ kiểm tra website. Không checkout, không tự thanh toán và không vượt CAPTCHA.
10. Cập nhật bản tương lai: vào Cài đặt -> UPDATE. Người phát hành vẫn phải đăng đúng version ZIP lên GitHub Releases.

Không chia sẻ BOT TOKEN, không tải token lên GitHub. Chỉ theo dõi kênh được cấp quyền.
