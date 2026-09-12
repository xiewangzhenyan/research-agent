# Code Patterns

## Dependency Injection

Use FastAPI's `Depends()` for injecting dependencies:

```python
from app.api.deps import get_db, get_current_user

@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ConversationService(db)
    return await service.get_by_user(current_user.id)
```

> **Important:** Routes never contain direct database calls. All data access
> goes through a service, which in turn delegates to a repository.

Available dependencies in `app/api/deps.py`:
- `get_db` - Database session
- `get_current_user` - Authenticated user (raises 401 if not authenticated)
- `get_current_user_optional` - User or None
- `get_redis` - Redis connection

## Service Layer Pattern

Every feature uses the same pattern: a service class receives a DB session,
instantiates its repository, and provides business-level methods. Services
are the **only** layer that raises domain exceptions.

```python
class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ConversationRepository()

    async def create(self, data: ConversationCreate, user_id: UUID) -> Conversation:
        # Business validation
        return await self.repo.create(self.db, user_id=user_id, **data.model_dump())

    async def get_or_raise(self, id: UUID) -> Conversation:
        conv = await self.repo.get_by_id(self.db, id)
        if not conv:
            raise NotFoundError(message="Conversation not found", details={"id": str(id)})
        return conv
```

All current services follow this pattern: `UserService`, `ConversationService`,
`FileUploadService`, `FileStorageService`.

## Repository Layer Pattern

Repositories handle data access only. They contain **no** business logic and
always use `flush()` instead of `commit()` so the caller controls transactions:

```python
class ConversationRepository:
    async def get_by_id(self, db: AsyncSession, id: UUID) -> Conversation | None:
        return await db.get(Conversation, id)

    async def create(self, db: AsyncSession, **kwargs) -> Conversation:
        conv = Conversation(**kwargs)
        db.add(conv)
        await db.flush()  # Not commit! Let dependency manage transaction
        await db.refresh(conv)
        return conv

    async def get_by_user(
        self, db: AsyncSession, user_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[Conversation]:
        result = await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .offset(skip).limit(limit)
        )
        return list(result.scalars().all())
```

## Exception Handling

Use domain exceptions in services:

```python
from app.core.exceptions import NotFoundError, AlreadyExistsError, ValidationError

# In service
if not conversation:
    raise NotFoundError(
        message="Conversation not found",
        details={"id": str(id)}
    )

if await self.repo.exists_by_email(self.db, email):
    raise AlreadyExistsError(
        message="User with this email already exists"
    )
```

Exception handlers convert to HTTP responses automatically.

## Schema Patterns

Separate schemas for different operations:

```python
# Base with shared fields
class UserBase(BaseModel):
    email: str
    full_name: str | None = None

# For creation (input)
class UserCreate(UserBase):
    password: str

# For updates (all optional)
class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None

# For responses (with DB fields)
class UserResponse(UserBase):
    id: UUID
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
```

## Frontend Patterns

### Authentication (HTTP-only cookies)

```typescript
import { useAuth } from '@/hooks/use-auth';

function Component() {
    const { user, isAuthenticated, login, logout } = useAuth();
}
```

### State Management (Zustand)

```typescript
import { useAuthStore } from '@/stores/auth-store';

const { user, setUser, logout } = useAuthStore();
```

### WebSocket Chat

```typescript
import { useChat } from '@/hooks/use-chat';

function ChatPage() {
    const { messages, sendMessage, isStreaming } = useChat();
}
```
