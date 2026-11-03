# Project Versioning & Release Rules (RK7 Pro Manager)

Mọi thay đổi liên quan đến cập nhật và phát hành phiên bản mới cho dự án này PHẢI tuân thủ nghiêm ngặt chuẩn Semantic Versioning: `MAJOR.MINOR.PATCH` (định dạng `X.Y.Z`, tag Git: `vX.Y.Z`).

---

## 1. Phân loại Version & Quyền quyết định

### A. PATCH (`X.Y.Z` -> tăng `Z`) - TỰ ĐỘNG ĐÁNH SỐ
Áp dụng cho các thay đổi sửa chữa, vá lỗi, tối ưu hiệu năng:
- Sửa lỗi crash, ngoại lệ, lỗi load DLL (`python312.dll`), lỗi auto-update script.
- Sửa lỗi hiển thị UI nhỏ: canh lề, font chữ, màu sắc, chính tả nhãn.
- Sửa lỗi logic tính toán, filter, query SQL hiện hữu.
- Tinh chỉnh/sửa lỗi các mẫu `invoice_templates` hoặc `master_refs` hiện có.
- Cập nhật các giá trị config mặc định (timeout, retry delay...).

👉 **Hành động của AI:** Tự động tăng `PATCH` lên 1 đơn vị (ví dụ `4.0.2` -> `4.0.3`), tự động đồng bộ vào các file cấu hình và tiến hành build/update mà không cần hỏi lại.

---

### B. MINOR (`X.Y.0` -> tăng `Y`) - BẮT BUỘC HỎI NGƯỜI DÙNG
Áp dụng khi bổ sung tính năng mới hoặc thay đổi chức năng nhưng vẫn tương thích ngược:
- Thêm tab mới, màn hình mới, luồng làm việc mới.
- Thêm mẫu `invoice_template` hoàn toàn mới hoặc bộ `master_refs` mới.
- Bổ sung cấu hình cài đặt mới trong `settings.json` cho người dùng thiết lập.
- Thêm tính năng xuất báo cáo mới (Excel, PDF...), thêm endpoint / API mới trong `web_bridge.py`.
- Tái cấu trúc (redesign) lại giao diện hoặc thêm chế độ giao diện mới (Dark/Light mode).

👉 **Hành động của AI:** KHÔNG được tự ý nâng version. BẮT BUỘC thông báo tóm tắt các tính năng mới bổ sung, đề xuất số phiên bản MINOR tiếp theo (ví dụ: `4.1.0`), và hỏi ý kiến người dùng trước khi cập nhật.

---

### C. MAJOR (`X.0.0` -> tăng `X`) - BẮT BUỘC HỎI NGƯỜI DÙNG
Áp dụng khi có thay đổi mang tính đột phá hoặc phá vỡ tính tương thích ngược:
- Viết lại toàn bộ kiến trúc ứng dụng hoặc đổi nền tảng runtime/framework.
- Thay đổi cấu trúc cơ sở dữ liệu hoặc file cấu hình khiến dữ liệu ở bản cũ không thể đọc được nếu không migrate.
- Loại bỏ các module cốt lõi cũ.

👉 **Hành động của AI:** BẮT BUỘC trình bày lý do, kế hoạch chuyển đổi dữ liệu và xin xác nhận trực tiếp từ người dùng trước khi nâng version MAJOR.

---

## 2. Quy chuẩn Đồng bộ Phiên bản
Khi thực hiện nâng version (sau khi đã được phép hoặc tự động với PATCH), AI PHẢI đồng bộ số phiên bản tại tất cả các vị trí sau:
1. `rk7_pro/core/auto_update_service.py`: Biến `CURRENT_VERSION = "X.Y.Z"`
2. `version_info.txt`: Các trường `filevers=(X, Y, Z, 0)`, `prodvers=(X, Y, Z, 0)`, `FileVersion`, `ProductVersion`
3. Git tag: `vX.Y.Z` (khi tạo GitHub Release)
4. Tên file release: Cố định `RK7_Pro_Manager_WebView.exe` hoặc file đóng gói nén `RK7_Pro_Manager-vX.Y.Z.zip`
