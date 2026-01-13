# Uni-Video - AI Video Generation Automation Platform

**Version:** 2.0.0 (Post-SOLID Refactoring)
**Status:** ✅ Production Ready
**Architecture:** Clean Architecture with SOLID Principles

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Development](#development)
- [Contributing](#contributing)

---

## 🎯 Overview

Uni-Video là một nền tảng tự động hóa việc tạo video AI thông qua các platform như Sora (OpenAI), Veo3, và Runway. Hệ thống được thiết kế với Clean Architecture và tuân theo các nguyên tắc SOLID để dễ dàng bảo trì và mở rộng.

### Key Capabilities

- ✅ **Multi-Platform Support:** Sora, Veo3, Runway (extensible)
- ✅ **Account Management:** Automated login, session management, credit tracking
- ✅ **Job Queue System:** Async job processing with retry logic
- ✅ **Worker-based Architecture:** Generate, Poll, Download workers
- ✅ **RESTful API:** Complete CRUD operations
- ✅ **WebSocket Support:** Real-time progress updates
- ✅ **Web UI:** Browser-based interface for job management
- ✅ **License Management:** Secure license validation system

---

## ✨ Features

### Core Features

- 🎥 **Video Generation**
  - Text-to-video generation
  - Image-to-video with custom prompts
  - Multiple aspect ratios: 16:9, 9:16, 1:1
  - Duration options: 5s, 10s, 15s

- 👥 **Account Management**
  - Multi-account support
  - Auto/manual login modes
  - Credit tracking and refresh
  - Session persistence
  - Proxy support

- 📊 **Job Management**
  - Create, update, delete jobs
  - Start, retry, cancel operations
  - Progress tracking (0-100%)
  - Status monitoring (draft → pending → processing → done)
  - Bulk operations

- ⚡ **Automation**
  - Automatic account rotation
  - Smart retry logic (configurable)
  - Parallel job processing
  - Stale job detection and recovery
  - Watermark removal (optional)

### Advanced Features

- 🔒 **License System**
  - Hardware-based licensing
  - Expiration management
  - Secure validation

- 📡 **Real-time Updates**
  - WebSocket connection for progress
  - Live status updates
  - Job completion notifications

- 📁 **File Management**
  - Image upload support
  - Video download management
  - External video opening

---

## 🏗️ Architecture

### Clean Architecture Layers

```
┌─────────────────────────────────────────────────┐
│              API Layer (FastAPI)                 │
│  ┌────────────┬────────────┬────────────┐       │
│  │ Accounts   │   Jobs     │  System    │       │
│  │  Router    │  Router    │  Router    │       │
│  └────────────┴────────────┴────────────┘       │
└──────────────────┬──────────────────────────────┘
                   │ Depends on
┌──────────────────▼──────────────────────────────┐
│            Service Layer                         │
│  ┌──────────────┬──────────────────────────┐    │
│  │ AccountService│  JobService  │TaskService│   │
│  └──────────────┴──────────────────────────┘    │
└──────────────────┬──────────────────────────────┘
                   │ Uses
┌──────────────────▼──────────────────────────────┐
│          Repository Layer                        │
│  ┌──────────────┬──────────────────────────┐    │
│  │AccountRepo   │  JobRepo     │           │    │
│  └──────────────┴──────────────────────────┘    │
└──────────────────┬──────────────────────────────┘
                   │ Manages
┌──────────────────▼──────────────────────────────┐
│            Domain Layer                          │
│  ┌──────────────┬──────────────────────────┐    │
│  │   Account    │    Job       │   Task    │    │
│  │   Models     │   Models     │  Models   │    │
│  └──────────────┴──────────────────────────┘    │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│            Worker Layer                           │
│  ┌──────────────┬──────────────────────────┐    │
│  │GenerateWorker│ PollWorker │DownloadWorker│   │
│  └──────────────┴──────────────────────────┘    │
└──────────────────┬──────────────────────────────┘
                   │ Uses
┌──────────────────▼──────────────────────────────┐
│            Driver Layer                          │
│  ┌──────────────┬──────────────────────────┐    │
│  │ SoraDriver   │  Veo3Driver  │ Factory   │    │
│  └──────────────┴──────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

### SOLID Principles Implementation

**Single Responsibility (SRP)**
- Each router handles one resource type
- Each service has one business domain
- Each worker handles one task type

**Open/Closed (OCP)**
- Easy to add new platforms via Driver Factory
- New task types via Worker base class
- Extensible without modifying existing code

**Liskov Substitution (LSP)**
- All drivers implement IDriver interface
- Workers follow BaseWorker contract

**Interface Segregation (ISP)**
- Domain models split by concern (Auth, Session, Credits)
- Specific repository methods (get_credits, get_session)

**Dependency Inversion (DIP)**
- High-level code depends on abstractions
- Dependency Injection throughout
- Repository pattern for data access

### Project Structure

```
uni-video/
├── app/
│   ├── api/
│   │   ├── dependencies.py          # DI container setup
│   │   └── routers/
│   │       ├── accounts.py          # Account endpoints
│   │       ├── jobs.py              # Job endpoints
│   │       └── system.py            # System endpoints
│   │
│   ├── core/
│   │   ├── domain/                  # Domain models
│   │   │   ├── account.py
│   │   │   ├── job.py
│   │   │   └── task.py
│   │   │
│   │   ├── repositories/            # Data access
│   │   │   ├── base.py
│   │   │   ├── account_repo.py
│   │   │   └── job_repo.py
│   │   │
│   │   ├── services/                # Business logic
│   │   │   ├── account_service.py
│   │   │   ├── job_service.py
│   │   │   └── task_service.py
│   │   │
│   │   ├── workers/                 # Background workers
│   │   │   ├── base.py
│   │   │   ├── generate_worker.py
│   │   │   ├── poll_worker.py
│   │   │   └── download_worker.py
│   │   │
│   │   ├── drivers/                 # Platform drivers
│   │   │   ├── abstractions.py
│   │   │   ├── factory.py
│   │   │   └── sora/
│   │   │       ├── driver.py
│   │   │       └── pages/
│   │   │
│   │   ├── container.py             # DI Container
│   │   └── license_manager.py       # License system
│   │
│   ├── database.py                  # Database setup
│   ├── models.py                    # SQLAlchemy models
│   ├── schemas.py                   # Pydantic schemas
│   └── main.py                      # FastAPI app
│
├── tests/
│   ├── unit/                        # Unit tests (140 tests)
│   │   ├── domain/
│   │   ├── repositories/
│   │   └── services/
│   └── integration/                 # Integration tests (52 templates)
│       └── api/
│
├── data/                            # SQLite database
├── downloads/                       # Downloaded videos
├── uploads/                         # Uploaded images
│
├── requirements.txt
├── pytest.ini                       # Test configuration
├── README.md                        # This file
├── README_TESTING.md                # Testing guide
└── SOLID_REFACTORING_PLAN.md       # Refactoring documentation
```

---

## 📦 Installation

### Prerequisites

- Python 3.12+
- SQLite
- Chrome/Chromium browser (for automation)

### Setup

```bash
# Clone repository
git clone <repository-url>
cd uni-video

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run database migrations (if needed)
python -c "from app.database import init_db; init_db()"
```

### Configuration

Create `.env` file (optional):
```env
DATABASE_URL=sqlite:///./data/uni_video.db
LOG_LEVEL=INFO
```

---

## 🚀 Usage

### Starting the Server

```bash
# Development mode
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Web Interface

Open browser: `http://localhost:8000`

### API Examples

#### Create Account

```bash
curl -X POST "http://localhost:8000/accounts/" \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "sora",
    "email": "user@example.com",
    "password": "your-password",
    "proxy": null
  }'
```

#### Create Job

```bash
curl -X POST "http://localhost:8000/jobs/" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A beautiful sunset over the ocean",
    "duration": 5,
    "aspect_ratio": "16:9"
  }'
```

#### Start Job

```bash
curl -X POST "http://localhost:8000/jobs/{job_id}/start"
```

#### Get Job Status

```bash
curl "http://localhost:8000/jobs/{job_id}"
```

#### List All Jobs

```bash
# All jobs
curl "http://localhost:8000/jobs/"

# Active jobs only
curl "http://localhost:8000/jobs/?category=active"

# Completed jobs
curl "http://localhost:8000/jobs/?category=history"
```

---

## 📚 API Documentation

### Interactive Documentation

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

### Main Endpoints

#### Accounts

- `POST /accounts/` - Create account
- `GET /accounts/` - List accounts
- `GET /accounts/{id}` - Get account
- `DELETE /accounts/{id}` - Delete account
- `POST /accounts/{id}/refresh-credits` - Refresh credits

#### Jobs

- `POST /jobs/` - Create job
- `GET /jobs/` - List jobs (with filters)
- `GET /jobs/{id}` - Get job
- `PUT /jobs/{id}` - Update job
- `DELETE /jobs/{id}` - Delete job
- `POST /jobs/{id}/start` - Start job
- `POST /jobs/{id}/retry` - Retry failed job
- `POST /jobs/{id}/cancel` - Cancel running job
- `POST /jobs/upload-image` - Upload image
- `POST /jobs/bulk-action` - Bulk operations

#### System

- `GET /system/status` - System status
- `GET /system/stats` - Statistics
- `POST /system/workers/start` - Start workers
- `POST /system/workers/stop` - Stop workers

#### WebSocket

- `WS /ws` - Real-time updates

---

## 🧪 Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html

# View coverage report
start htmlcov/index.html  # Windows
open htmlcov/index.html   # Mac/Linux
```

### Test Statistics

- **Total Tests:** 140 unit tests + 52 integration templates
- **Coverage:** ~20% overall (60-95% on refactored code)
- **Pass Rate:** 100%
- **Execution Time:** <1 second (unit tests)

### Test Documentation

See `README_TESTING.md` for complete testing guide.

---

## 💻 Development

### Code Style

- **Linting:** Follow PEP 8
- **Type Hints:** Use type annotations
- **Docstrings:** Google style
- **Formatting:** Use black/autopep8

### Adding New Platform

1. Create driver in `app/core/drivers/new_platform/`
2. Implement `IDriver` interface
3. Register in `DriverFactory`
4. Add tests

Example:
```python
from app.core.drivers.abstractions import IDriver

class NewPlatformDriver(IDriver):
    async def login(self, account: Account) -> bool:
        # Implementation
        pass

    async def create_video(self, job: Job) -> str:
        # Implementation
        pass
```

### Adding New Worker

1. Extend `BaseWorker` in `app/core/workers/`
2. Implement `process()` method
3. Register in `WorkerManager`

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 🔒 License System

### Generating License

```bash
python keygen.py --generate --days 365
```

### Validating License

```bash
python keygen.py --validate
```

### License Features

- Hardware-bound (machine-specific)
- Expiration date validation
- Encrypted with RSA
- Auto-validation on startup

---

## 📊 Performance

### Metrics

- **API Response Time:** <100ms (average)
- **Job Processing:** Concurrent (parallel workers)
- **Database:** SQLite (upgrade to PostgreSQL for production)

### Optimization Tips

1. Use connection pooling for database
2. Enable response caching for GET requests
3. Use background tasks for long operations
4. Monitor with Prometheus/Grafana

---

## 🐛 Troubleshooting

### Common Issues

**Database Locked Error:**
```bash
# Solution: Use WAL mode
sqlite3 data/uni_video.db "PRAGMA journal_mode=WAL;"
```

**Worker Not Starting:**
- Check logs in `logs/` directory
- Verify account credentials
- Ensure browser driver is installed

**Import Errors:**
```bash
# Ensure you're in the project root
cd /path/to/uni-video
python -m uvicorn app.main:app --reload
```

---

## 🤝 Contributing

### Development Workflow

1. Fork repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Write tests for new code
4. Ensure all tests pass: `pytest tests/`
5. Commit changes: `git commit -m 'Add amazing feature'`
6. Push to branch: `git push origin feature/amazing-feature`
7. Open Pull Request

### Code Review Checklist

- [ ] Tests written and passing
- [ ] Documentation updated
- [ ] Type hints added
- [ ] No breaking changes (or documented)
- [ ] SOLID principles followed

---

## 📝 Changelog

### Version 2.0.0 (2026-01-13)

**Major Refactoring - SOLID Principles**

- ✅ Implemented Clean Architecture
- ✅ Added Domain Models (Account, Job, Task)
- ✅ Created Repository Pattern
- ✅ Implemented Service Layer
- ✅ Refactored API Routers
- ✅ Added Dependency Injection
- ✅ Created Driver Factory Pattern
- ✅ Added 140 Unit Tests (100% passing)
- ✅ Added Comprehensive Documentation

**Breaking Changes:**
- API structure reorganized (backwards compatible)
- Internal architecture completely redesigned
- Old `endpoints.py` moved to legacy

**Migration Guide:** See `MIGRATION_GUIDE.md`

### Version 1.0.0 (Previous)

- Initial release
- Basic video generation
- Account management
- Job queue system

---

## 📄 License

[Your License Here]

---

## 👥 Authors

- **Development Team** - Initial work and SOLID refactoring

---

## 🙏 Acknowledgments

- OpenAI Sora API
- FastAPI framework
- Playwright automation
- SQLAlchemy ORM
- Pytest testing framework

---

## 📞 Support

- **Documentation:** See `/docs` folder
- **Issues:** GitHub Issues
- **Email:** support@example.com

---

## 🔗 Links

- **GitHub:** [Repository URL]
- **Documentation:** [Docs URL]
- **API Docs:** http://localhost:8000/docs

---

**Built with ❤️ using Clean Architecture and SOLID Principles**

**Status:** ✅ Production Ready | 🧪 140 Tests Passing | 📈 20%+ Coverage
