# Testing Documentation - Uni-Video

Tài liệu hướng dẫn testing cho dự án Uni-Video sau khi refactor SOLID principles.

## 📋 Mục lục

- [Tổng quan](#tổng-quan)
- [Cấu trúc Tests](#cấu-trúc-tests)
- [Chạy Tests](#chạy-tests)
- [Coverage Report](#coverage-report)
- [Test Categories](#test-categories)
- [Writing Tests](#writing-tests)

---

## 🎯 Tổng quan

Project hiện tại có **140 unit tests** covering:
- ✅ Domain Models (Account, Job, Task)
- ✅ Repositories (AccountRepository, JobRepository)
- ✅ Services (AccountService, JobService)

### Test Statistics

```
Total Tests: 140
Passed: 140 (100%)
Failed: 0
Coverage: ~20% (focused on refactored code)
```

---

## 📁 Cấu trúc Tests

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures và configuration
├── unit/                          # Unit tests
│   ├── domain/                    # Domain model tests
│   │   ├── test_account.py       # 27 tests
│   │   ├── test_job.py           # 35 tests
│   │   └── test_task.py          # 14 tests
│   ├── repositories/              # Repository tests
│   │   ├── test_account_repo.py  # 32 tests
│   │   └── test_job_repo.py      # 17 tests
│   └── services/                  # Service tests
│       ├── test_account_service.py # 8 tests
│       └── test_job_service.py     # 17 tests
├── integration/                   # Integration tests (TODO)
│   ├── api/
│   └── workers/
└── e2e/                          # End-to-end tests (TODO)
```

---

## 🚀 Chạy Tests

### 1. Cài đặt Dependencies

```bash
pip install -r requirements.txt
```

Dependencies testing:
- pytest
- pytest-asyncio
- pytest-cov
- pytest-mock
- httpx

### 2. Chạy All Tests

```bash
# Chạy tất cả tests
python -m pytest tests/

# Chạy với verbose output
python -m pytest tests/ -v

# Chạy với coverage
python -m pytest tests/ --cov=app --cov-report=html
```

### 3. Chạy Specific Tests

```bash
# Chỉ unit tests
python -m pytest tests/unit/

# Chỉ domain tests
python -m pytest tests/unit/domain/

# Test một file cụ thể
python -m pytest tests/unit/domain/test_account.py

# Test một class cụ thể
python -m pytest tests/unit/domain/test_account.py::TestAccountId

# Test một function cụ thể
python -m pytest tests/unit/domain/test_account.py::TestAccountId::test_valid_account_id
```

### 4. Chạy với Markers

```bash
# Chỉ unit tests
python -m pytest tests/ -m unit

# Chỉ integration tests (khi có)
python -m pytest tests/ -m integration

# Chỉ e2e tests (khi có)
python -m pytest tests/ -m e2e

# Skip slow tests
python -m pytest tests/ -m "not slow"
```

---

## 📊 Coverage Report

### Xem Coverage

```bash
# Generate HTML coverage report
python -m pytest tests/ --cov=app --cov-report=html

# Mở report trong browser
# Windows:
start htmlcov/index.html

# Mac/Linux:
open htmlcov/index.html
```

### Coverage Breakdown

Hiện tại coverage tập trung vào các module đã refactor:

| Module | Coverage | Tests |
|--------|----------|-------|
| Domain Models | ~95% | 76 tests |
| Repositories | ~60% | 49 tests |
| Services | ~50% | 25 tests |
| **Overall** | **~20%** | **140 tests** |

**Lưu ý:** Coverage thấp là do phần lớn codebase (drivers, workers, old code) chưa có tests.

---

## 🏷️ Test Categories

### Unit Tests

Test các component riêng lẻ với dependencies được mock.

**Domain Models** (`tests/unit/domain/`):
- Test validation logic
- Test business rules
- Test value object behavior

**Repositories** (`tests/unit/repositories/`):
- Test CRUD operations
- Test queries
- Mock database session

**Services** (`tests/unit/services/`):
- Test business logic
- Mock repositories
- Test error handling

### Integration Tests (TODO)

Test tích hợp giữa nhiều components.

**API Endpoints** (`tests/integration/api/`):
- Test HTTP endpoints
- Use TestClient
- Real database (test DB)

**Workers** (`tests/integration/workers/`):
- Test worker flow
- Test job processing
- Mock external services

### E2E Tests (TODO)

Test toàn bộ flow từ đầu đến cuối.

---

## ✍️ Writing Tests

### Test Structure

```python
"""
Module docstring - mô tả test file
"""
import pytest
from unittest.mock import Mock, AsyncMock

# Fixtures
@pytest.fixture
def sample_data():
    """Create sample test data"""
    return {...}

# Test Class
class TestFeature:
    """Test feature description"""

    @pytest.mark.asyncio
    async def test_something(self, sample_data):
        """Test specific behavior"""
        # Arrange
        ...

        # Act
        result = await some_function(sample_data)

        # Assert
        assert result == expected
```

### Best Practices

1. **Test Names**: Mô tả rõ ràng behavior being tested
   ```python
   ✅ def test_account_id_cannot_be_negative(self):
   ❌ def test_account_id(self):
   ```

2. **AAA Pattern**: Arrange, Act, Assert
   ```python
   # Arrange - setup test data
   account_id = 1

   # Act - execute the code
   result = await service.get_account(account_id)

   # Assert - verify results
   assert result is not None
   ```

3. **Mock External Dependencies**
   ```python
   @pytest.fixture
   def mock_repo():
       repo = Mock(spec=AccountRepository)
       repo.get_by_id = AsyncMock(return_value=sample_account)
       return repo
   ```

4. **Test Both Happy and Error Paths**
   ```python
   async def test_get_account_found(self):  # Happy path
       ...

   async def test_get_account_not_found(self):  # Error path
       ...
   ```

5. **Use Descriptive Assertions**
   ```python
   ✅ assert result.email == "test@example.com"
   ✅ with pytest.raises(ValueError, match="cannot be negative"):

   ❌ assert result
   ❌ with pytest.raises(Exception):
   ```

### Example: Domain Model Test

```python
class TestAccountId:
    """Test AccountId value object"""

    def test_valid_account_id(self):
        """Test creating valid AccountId"""
        account_id = AccountId(value=1)
        assert account_id.value == 1
        assert str(account_id) == "1"

    def test_account_id_cannot_be_negative(self):
        """Test AccountId cannot be negative"""
        with pytest.raises(ValueError, match="Account ID cannot be negative"):
            AccountId(value=-1)
```

### Example: Repository Test

```python
class TestAccountRepositoryGet:
    """Test get operations"""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, account_repo, mock_session, sample_orm_account):
        """Test getting account by ID when found"""
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter_by.return_value.first.return_value = sample_orm_account

        result = await account_repo.get_by_id(1)

        assert result is not None
        assert result.id.value == 1
        mock_session.query.assert_called_once()
```

### Example: Service Test

```python
class TestAccountServiceCreate:
    """Test account creation"""

    @pytest.mark.asyncio
    async def test_create_account_success(self, account_service, mock_account_repo):
        """Test successfully creating a new account"""
        mock_account_repo.get_by_email.return_value = None
        mock_account_repo.create.return_value = sample_account

        result = await account_service.create_account(
            platform="sora",
            email="test@example.com",
            password="password123"
        )

        assert result is not None
        assert result.email == "test@example.com"
        mock_account_repo.create.assert_called_once()
        mock_account_repo.commit.assert_called_once()
```

---

## 🔧 Pytest Configuration

File `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
addopts =
    -v
    --tb=short
    --strict-markers
    --cov=app
    --cov-report=term-missing
    --cov-report=html
    --cov-branch
    --cov-fail-under=80
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow running tests
```

---

## 🐛 Debugging Tests

### Run with verbose output

```bash
python -m pytest tests/ -vv
```

### Show print statements

```bash
python -m pytest tests/ -s
```

### Stop on first failure

```bash
python -m pytest tests/ -x
```

### Run last failed tests

```bash
python -m pytest tests/ --lf
```

### Debug with pdb

```bash
python -m pytest tests/ --pdb
```

---

## 📝 Next Steps

### Phase 5 Remaining Tasks:

1. ✅ **Unit Tests cho Domain Models** - COMPLETED (76 tests)
2. ✅ **Unit Tests cho Repositories** - COMPLETED (49 tests)
3. ✅ **Unit Tests cho Services** - COMPLETED (25 tests)
4. ⏸️ **Unit Tests cho Workers** - TODO
5. ⏸️ **Integration Tests cho API Endpoints** - TODO
6. ⏸️ **Integration Tests cho Workers** - TODO
7. ⏸️ **End-to-End Tests** - TODO
8. ⏸️ **Performance Optimization** - TODO
9. ⏸️ **Documentation Updates** - TODO

### Coverage Goals:

- **Target:** >80% coverage
- **Current:** ~20% (focused on refactored code)
- **Strategy:**
  - Prioritize testing new refactored code
  - Legacy code testing là optional
  - Focus on critical paths first

---

## 🎓 Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-Asyncio](https://pytest-asyncio.readthedocs.io/)
- [Python Mock Library](https://docs.python.org/3/library/unittest.mock.html)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)

---

**Last Updated:** 2026-01-13
**Status:** ✅ Phase 5 Unit Tests COMPLETED - 140/140 tests passing
