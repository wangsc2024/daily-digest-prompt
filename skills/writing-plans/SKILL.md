---
name: writing-plans
version: 1.0.0
description: |
  建立詳細的實作計畫（多步驟功能）。將工作拆解為微小的 TDD 任務（2-5 分鐘粒度），包含準確檔案路徑、程式碼範例與驗證步驟。
  Use when: 規劃新功能、複雜重構、多檔案修改、建立路線圖，or when user mentions 計畫, plan, 規劃, 實作計畫, implementation plan, 步驟, 任務拆解.
allowed-tools: Read, Write, Bash
cache-ttl: N/A
triggers:
  - write plan
  - create plan
  - implementation plan
  - 計畫
  - 規劃
  - 怎麼實作
  - 步驟
  - 拆解任務
---

# Writing Implementation Plans

建立詳細的實作計畫，讓任何工程師都能執行。

## 核心原則

> 計畫要詳細到「不熟悉程式碼庫的工程師也能執行」

- 每個任務 2-5 分鐘完成
- 遵循 TDD（測試驅動開發）
- 包含完整程式碼範例
- 明確的驗證步驟

## 計畫結構

```markdown
# 實作計畫：[功能名稱]

## 概要
- **目標**：[一句話描述目標]
- **預估任務數**：[N] 個
- **相關文件**：[連結]

## 架構說明
[簡短說明技術架構和設計決策]

## 技術棧
- 語言：[Python/TypeScript/etc.]
- 框架：[FastAPI/React/etc.]
- 測試：[pytest/Jest/etc.]

## 執行方式
使用 `executing-plans` skill 執行此計畫

---

## Task 1: [任務標題]

### 目標
[這個任務要達成什麼]

### 步驟

#### 1.1 寫測試
檔案：`tests/test_xxx.py`

```python
def test_xxx():
    # 測試程式碼
    pass
```

#### 1.2 驗證測試失敗
```bash
pytest tests/test_xxx.py -v
# 預期輸出：FAILED
```

#### 1.3 實作
檔案：`src/xxx.py`

```python
# 實作程式碼
```

#### 1.4 驗證測試通過
```bash
pytest tests/test_xxx.py -v
# 預期輸出：PASSED
```

#### 1.5 Commit
```bash
git add .
git commit -m "feat: [描述]"
```

---

## Task 2: [下一個任務]
...
```

## 計畫範例

```markdown
# 實作計畫：使用者認證 API

## 概要
- **目標**：實作 JWT 認證，包含註冊、登入、登出
- **預估任務數**：6 個
- **相關文件**：docs/auth-spec.md

## 架構說明
使用 FastAPI + JWT + SQLAlchemy，密碼使用 bcrypt 加密。
Token 存於 HTTP-only cookie，支援 refresh token。

## 技術棧
- 語言：Python 3.11
- 框架：FastAPI
- 測試：pytest + httpx

## 執行方式
使用 `executing-plans` skill 執行此計畫

---

## Task 1: 建立 User Entity

### 目標
定義 User 實體與資料庫模型

### 步驟

#### 1.1 寫測試
檔案：`tests/domain/test_user.py`

```python
import pytest
from src.domain.entities.user import User
from src.domain.value_objects.email import Email

def test_create_user_with_valid_data():
    user = User(
        email=Email("test@example.com"),
        password_hash="hashed_password"
    )
    assert user.email.value == "test@example.com"
    assert user.password_hash == "hashed_password"

def test_create_user_with_invalid_email_raises_error():
    with pytest.raises(ValueError):
        User(
            email=Email("invalid-email"),
            password_hash="hashed_password"
        )
```

#### 1.2 驗證測試失敗
```bash
pytest tests/domain/test_user.py -v
# 預期：ModuleNotFoundError 或 ImportError
```

#### 1.3 實作
檔案：`src/domain/value_objects/email.py`

```python
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(pattern, self.value):
            raise ValueError(f"Invalid email: {self.value}")
```

檔案：`src/domain/entities/user.py`

```python
from dataclasses import dataclass, field
from uuid import uuid4
from src.domain.value_objects.email import Email

@dataclass
class User:
    email: Email
    password_hash: str
    id: str = field(default_factory=lambda: str(uuid4()))
    is_active: bool = True
```

#### 1.4 驗證測試通過
```bash
pytest tests/domain/test_user.py -v
# 預期：2 passed
```

#### 1.5 Commit
```bash
git add .
git commit -m "feat(domain): add User entity and Email value object"
```

---

## Task 2: 實作密碼加密服務

### 目標
建立密碼 hash 和驗證服務

### 步驟

#### 2.1 寫測試
檔案：`tests/application/test_password_service.py`

```python
import pytest
from src.application.services.password_service import PasswordService

def test_hash_password_returns_different_value():
    service = PasswordService()
    password = "Test-P@ss-12345"
    hashed = service.hash(password)
    assert hashed != password
    assert len(hashed) > 20

def test_verify_correct_password_returns_true():
    service = PasswordService()
    password = "Test-P@ss-12345"
    hashed = service.hash(password)
    assert service.verify(password, hashed) is True

def test_verify_wrong_password_returns_false():
    service = PasswordService()
    hashed = service.hash("correct_password")
    assert service.verify("wrong_password", hashed) is False
```

#### 2.2 驗證測試失敗
```bash
pytest tests/application/test_password_service.py -v
```

#### 2.3 實作
檔案：`src/application/services/password_service.py`

```python
import bcrypt

class PasswordService:
    def hash(self, password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()

    def verify(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())
```

#### 2.4 驗證測試通過
```bash
pytest tests/application/test_password_service.py -v
# 預期：3 passed
```

#### 2.5 Commit
```bash
git add .
git commit -m "feat(application): add PasswordService for secure hashing"
```

---

[繼續 Task 3-6...]
```

## 計畫寫作原則

### DRY (Don't Repeat Yourself)
- 共用邏輯提取到函式/類別
- 避免複製貼上

### YAGNI (You Aren't Gonna Need It)
- 只實作當前需要的功能
- 不要過度設計

### 小步快跑
- 每個任務可獨立驗證
- 頻繁 commit
- 快速回饋

## 計畫儲存位置

```bash
docs/plans/YYYY-MM-DD-<feature-name>.md

# 範例
docs/plans/2024-01-15-user-authentication.md
docs/plans/2024-01-16-payment-integration.md
```

## 執行選項

計畫完成後，提供兩種執行方式：

### 選項 1：子代理執行（同一會話）
```markdown
使用新的子代理執行每個任務，在當前會話中進行。
適合：需要即時監督的情況
```

### 選項 2：獨立會話執行
```markdown
在新的 Claude 會話中使用 `executing-plans` skill 執行。
適合：長時間執行、需要分階段的情況
```

## Checklist

寫計畫前確認：

- [ ] 目標明確
- [ ] 架構決策已確定
- [ ] 任務粒度適當（2-5 分鐘）
- [ ] 每個任務包含測試
- [ ] 程式碼範例完整
- [ ] 驗證步驟明確
- [ ] Commit 訊息規範
- [ ] 儲存到正確位置
