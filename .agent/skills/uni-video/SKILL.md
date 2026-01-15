---
name: univideo_expert
description: Chuyên gia am hiểu sâu sắc về kiến trúc, logic nghiệp vụ và quy trình xử lý video của dự án Uni-Video.
---

# Uni-Video Expert Skill

Bạn là chuyên gia cốt lõi của dự án Uni-Video. Khi Skill này được kích hoạt, bạn phải đảm bảo mọi thay đổi đều tuân thủ các chuẩn mực sau:

## 1. Kiến trúc SOLID & Domain-Driven
> **Xem chi tiết tại:** [ARCHITECTURE.md](file:///c:/Code/uni-video/docs/ARCHITECTURE.md)

- **Domain Models:** Luôn sử dụng `app/core/domain/`. Không dùng dict thô.
- **Service Layer:** Logic nghiệp vụ nằm ở Service, không nằm trong API Router.
- **Anti-Corruption Layer:** Sử dụng Repository và Driver Adapter để cách ly core logic với hạ tầng.

## 2. Quy trình Xử lý Video (Sora)
- **Driver Abstraction:** Sử dụng `DriverFactory` để khởi tạo driver. Luôn tuân thủ interface `IDriver`.
- **API Client:** Các tương tác API với Sora phải qua `SoraApiClient`.
- **Watermark Removal:** Khi có yêu cầu xóa watermark, sử dụng `WatermarkRemover` (tích hợp API dyysy.com). Quy trình chuẩn: Post video (Public) -> Lấy Share URL -> Gọi API xóa watermark -> Download clean video.

## 3. Hệ thống Workers
- Hiểu rõ vai trò của 3 loại worker:
    - `GenerateWorker`: Gửi request và bắt đầu job.
    - `PollWorker`: Kiểm tra trạng thái job từ server Sora.
    - `DownloadWorker`: Tải video và thực hiện xóa watermark nếu cần.
- Sử dụng `WorkerManager` để điều phối hoạt động của các worker này.

## 4. Tiêu chuẩn Mã nguồn & Bảo mật
- **Logging:** Sử dụng `app/core/logger.py`. Mỗi log phải có prefix rõ ràng (ví dụ: `[JOB]`, `[DRIVER]`, `[WATERMARK]`).
- **Secret Hygiene:** Tuyệt đối không commit hoặc log `access_token`, `sentinel_token` hay `cookie` của người dùng.
- **Verification:** Luôn cập nhật `task.md` và tạo `walkthrough.md` sau mỗi thay đổi lớn.

> [!IMPORTANT]
> Dự án này đã trải qua một cuộc đại tu SOLID toàn diện. Mọi dòng code mới phải duy trì tính "Sạch" và "Dễ mở rộng" này.
