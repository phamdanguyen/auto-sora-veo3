# Uni-Video Architecture & SOLID Guidelines

Tài liệu này định nghĩa các nguyên tắc kiến trúc và tiêu chuẩn SOLID bắt buộc cho dự án Uni-Video. Toàn bộ mã nguồn mới phải tuân thủ nghiêm ngặt các hướng dẫn này để đảm bảo tính ổn định, dễ bảo trì và mở rộng.

---

## 1. Kiến trúc Backend (Python/FastAPI)

Dự án áp dụng mô hình **Domain-Driven Design (DDD)** kết hợp với **Clean Architecture**.

### 1.1 Phân tầng (Layers)

1.  **Domain Layer** (`app/core/domain/`)
    *   **Trách nhiệm**: Chứa các business logic cốt lõi, entity và value object thuần túy.
    *   **Nguyên tắc**: Không phụ thuộc vào framework, database, hoặc driver bên ngoài.
    *   **Ví dụ**: `Account`, `Job`, `AccountCredits`.

2.  **Application/Service Layer** (`app/core/services/`)
    *   **Trách nhiệm**: Điều phối các hoạt động nghiệp vụ, sử dụng Repository và Driver để thực hiện use cases.
    *   **Nguyên tắc**: Implement logic như `CreateJob`, `UpdateAccount`. Không chứa logic framework (như HTTP request/response).
    *   **Ví dụ**: `AccountService`, `JobService`.

3.  **Infrastructure/Repository Layer** (`app/core/repositories/`, `app/core/drivers/`)
    *   **Trách nhiệm**: Tương tác với Database, API bên ngoài, hoặc File system.
    *   **Nguyên tắc**: Implement các interface định nghĩa bởi Domain hoặc Service layer.
    *   **Ví dụ**: `SQLAlchemyAccountRepository`, `SoraBrowserDriver`.

4.  **Interface/Adapter Layer** (`app/api/`, `app/web/`)
    *   **Trách nhiệm**: Giao tiếp với thế giới bên ngoài (REST API, Web UI).
    *   **Nguyên tắc**: Chuyển đổi dữ liệu input thành Domain model và gọi Service layer.

### 1.2 Nguyên tắc SOLID trong Backend

1.  **Single Responsibility Principle (SRP)**
    *   *Sai*: Một file `main.py` chứa cả định nghĩa DB model, API route và logic xử lý video.
    *   *Đúng*: Tách `models.py` (DB), `routers/` (API), `services/` (Logic), `repositories/` (Data Access).
    *   *Áp dụng*: Mỗi Class/Module chỉ thay đổi vì một lý do duy nhất.

2.  **Open/Closed Principle (OCP)**
    *   *Sai*: Sửa trực tiếp class `SoraDriver` để thêm hỗ trợ cho `KlingAI`.
    *   *Đúng*: Tạo interface `IDriver`. Tạo class mới `KlingDriver` implement interface này. Sử dụng `DriverFactory` để mở rộng mà không sửa code cũ.

3.  **Liskov Substitution Principle (LSP)**
    *   *Áp dụng*: Mọi class con của `BaseWorker` (GenerateWorker, PollWorker) phải có thể thay thế class cha mà không làm hỏng chương trình. Các phương thức override phải có cùng signature và behavior contract.

4.  **Interface Segregation Principle (ISP)**
    *   *Sai*: Một interface lớn `IWorker` có cả `generate()`, `download()`, `poll()`.
    *   *Đúng*: Tách thành các interface nhỏ theo chức năng nếu cần, hoặc đảm bảo worker chỉ implement những gì nó thực sự cần. Trong Domain model: tách `Account` thành `AccountAuth`, `AccountSession`, `AccountCredits`.

5.  **Dependency Inversion Principle (DIP)**
    *   *Sai*: `AccountService` import trực tiếp `SQLAlchemyAccountRepo`.
    *   *Đúng*: `AccountService` phụ thuộc vào abstract `AccountRepository`. Dependency Injection sẽ inject implementation cụ thể (`SQLAlchemyAccountRepo`) vào lúc runtime.

---

## 2. Kiến trúc Frontend (Alpine.js Modular)

Do giới hạn về công nghệ (không dùng React/Vue/Node build complex), chúng ta áp dụng kiến trúc **Modular Monolith cho Frontend** sử dụng Alpine.js.

### 2.1 Cấu trúc Module

1.  **Core Application** (`app.js`)
    *   Entry point. Khởi tạo Alpine data global.
    *   Kết nối các module con.

2.  **Functional Modules** (`modules/*.js`)
    *   Tách biệt logic theo nghiệp vụ: `account.js` (quản lý tk), `job.js` (quản lý job), `system.js` (UI state).
    *   **Nguyên tắc**: Module trả về object chứa data và methods. Không truy cập trực tiếp DOM nếu có thể tránh (dùng x-model/x-bind).

3.  **Components** (`templates/components/`)
    *   Tách HTML thành các file nhỏ, tái sử dụng được (Sidebar, Modal, Table).
    *   Sử dụng Jinja2 `{% include %}` để lắp ghép.

### 2.2 Nguyên tắc SOLID trong Frontend

1.  **SRP**:
    *   File `job.js` chỉ chứa logic liên quan đến Job (fetch, create, delete). Không chứa logic login hay system settings.
    *   Component `job_queue.html` chỉ hiển thị danh sách job. Modal tạo job nằm ở `create_job.html`.

2.  **OCP**:
    *   Khi thêm một loại Job mới (ví dụ: "Text to Speech"), ta nên mở rộng `job.js` hoặc cấu hình tham số, thay vì viết lại hàm `createJob` hiện tại quá nhiều. Sử dụng cơ chế config/strategy nếu logic phức tạp.

3.  **LSP**:
    *   (Ít áp dụng trực tiếp trong JS object literals nhưng tư tưởng tương tự): Các module con khi được merge vào `appData` global không được ghi đè hoặc làm hỏng các phương thức hệ thống (như `showToast`).

4.  **ISP**:
    *   UI Module không nên ép buộc View phải có các data mà nó không cần. Ví dụ: `AccountManager` view chỉ cần binding vào `accounts` array và các action `add/delete`, không cần biết về cấu hình `JobQueue`.

5.  **DIP**:
    *   Logic JS không nên phụ thuộc cứng vào cấu trúc HTML cụ thể (như querySelector class `.my-btn`). Nên dùng Data Binding (`x-data`, `@click`) để tách biệt Logic và View.

---

## 3. Quy trình làm việc & Verification

1.  **Plan First**: Luôn bắt đầu bằng việc xác định thay đổi thuộc về Layer nào (Domain, Service hay UI).
2.  **Implementation**: Viết code theo nguyên tắc đã định.
3.  **Refactor**: Nếu thấy một file quá lớn (>300 dòng) hoặc một hàm quá phức tạp, hãy tách nó ra ngay lập tức.
4.  **Verify**: Kiểm tra lại xem sự thay đổi có vi phạm các nguyên tắc trên không (ví dụ: API gọi thẳng DB).

> [!IMPORTANT]
> Tài liệu này là "Luật". Mọi hành động của AI Agent phải đối chiếu với tài liệu này để đảm bảo không bị "lạc lối" giữa đống code hỗn độn.
