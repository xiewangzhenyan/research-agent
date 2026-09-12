
# Permissions & Access Control

## Roles

Two roles are defined in `app/db/models/user.py`:

- **admin** -- Full access to all features. Can manage users, RAG collections,
  sync sources, webhooks, and export data.
- **user** -- Standard access. Can chat with the AI agent, manage their own
  profile, view their own conversations, upload files to chat, and search
  the knowledge base.

Admins implicitly have all user permissions. The `User.has_role()` method
returns `True` for any role if the user is an admin.

## Dependency Aliases

These are defined in `app/api/deps.py` and used throughout the route layer:

| Alias | Resolves To | Access Level |
|-------|------------|--------------|
| `CurrentUser` | `Depends(get_current_user)` | Any authenticated user |
| `CurrentAdmin` | `Depends(RoleChecker(UserRole.ADMIN))` | Admin role required |
| `CurrentSuperuser` | `Depends(get_current_active_superuser)` | Admin role required (legacy alias) |

## Endpoint Access Matrix

### Authentication

| Endpoint | Method | Admin | User | Unauthenticated | Notes |
|----------|--------|-------|------|-----------------|-------|
| `/auth/login` | POST | Y | Y | Y | Returns JWT tokens |
| `/auth/register` | POST | Y | Y | Y | Creates new user account |
| `/auth/refresh` | POST | Y | Y | -- | Requires valid refresh token |

### Users

| Endpoint | Method | Admin | User | Notes |
|----------|--------|-------|------|-------|
| `/users/me` | GET | Y | Y | Own profile |
| `/users/me` | PATCH | Y | Y | Own profile; non-admins cannot change role |
| `/users/me/avatar` | POST | Y | Y | Upload own avatar image |
| `/users/avatar/{user_id}` | GET | Y | Y | Public avatar access |
| `/users` | GET | Y | -- | List all users (admin only) |
| `/users/{id}` | GET | Y | -- | View any user (admin only) |
| `/users/{id}` | PATCH | Y | -- | Update any user including role (admin only) |
| `/users/{id}` | DELETE | Y | -- | Delete any user (admin only) |

### AI Agent

| Endpoint | Method | Admin | User | Notes |
|----------|--------|-------|------|-------|
| `/ws/agent` | WS | Y | Y | WebSocket chat with AI agent |

### Conversations

| Endpoint | Method | Admin | User | Notes |
|----------|--------|-------|------|-------|
| `/conversations` | GET | Y | Y | Own conversations only (filtered by user_id) |
| `/conversations` | POST | Y | Y | Create new conversation |
| `/conversations/{id}` | GET | Y | Y | Own conversations only (IDOR protection) |
| `/conversations/{id}` | PATCH | Y | Y | Update title / archived status |
| `/conversations/{id}` | DELETE | Y | Y | Delete own conversation |
| `/conversations/{id}/archive` | POST | Y | Y | Archive own conversation |
| `/conversations/{id}/messages` | GET | Y | Y | List messages in own conversation |
| `/conversations/{id}/messages` | POST | Y | Y | Add message to own conversation |
| `/conversations/export` | GET | Y | -- | Export all conversations (admin only) |

### Message Ratings

| Endpoint | Method | Admin | User | Notes |
|----------|--------|-------|------|-------|
| `/conversations/{id}/messages/{msg_id}/rate` | POST | Y | Y | Rate/update a message (like/dislike) |
| `/conversations/{id}/messages/{msg_id}/rate` | DELETE | Y | Y | Remove own rating |
| `/admin/ratings` | GET | Y | -- | List all ratings with filters (admin only) |
| `/admin/ratings/summary` | GET | Y | -- | Aggregated statistics (admin only) |
| `/admin/ratings/export` | GET | Y | -- | Export ratings JSON/CSV (admin only) |
| `/admin/conversations` | GET | Y | -- | List all conversations (admin only) |

### Files

| Endpoint | Method | Admin | User | Notes |
|----------|--------|-------|------|-------|
| `/files/upload` | POST | Y | Y | Upload file for chat |
| `/files/{id}` | GET | Y | Y | Download own files only (ownership check) |
| `/files/{id}/info` | GET | Y | Y | File metadata for own files only |

### Health

| Endpoint | Method | Admin | User | Unauthenticated | Notes |
|----------|--------|-------|------|-----------------|-------|
| `/health` | GET | Y | Y | Y | No auth required |

## How It Works

### JWT Flow

1. User sends credentials to `POST /auth/login`.
2. Server validates credentials, returns `access_token` + `refresh_token`.
3. Client includes `Authorization: Bearer <access_token>` on subsequent requests.
4. `get_current_user` dependency extracts the JWT, verifies it, loads the user.
5. If the token is expired, the client uses `POST /auth/refresh` to get a new one.

### Role Checking

`RoleChecker` is a callable class that wraps `get_current_user`:

```python
class RoleChecker:
    def __init__(self, required_role: UserRole):
        self.required_role = required_role

    async def __call__(self, user = Depends(get_current_user)) -> User:
        if not user.has_role(self.required_role):
            raise AuthorizationError(...)
        return user
```

`User.has_role()` returns `True` if:
- The user's role matches the required role, OR
- The user is an admin (admin has all permissions).

### IDOR Protection

Resources owned by users (conversations, files) are protected at the service
layer. The service receives the current user's ID from the route and uses it
to filter queries:

```python
# In conversation route
items, total = await service.list_conversations(user_id=current_user.id, ...)

# In file route
chat_file = await file_upload_svc.get_user_file(file_id, current_user.id)
# Raises NotFoundError if user_id doesn't match
```

### API Key Authentication

For programmatic access, clients can authenticate via API key:

```
X-API-Key: your-api-key-here
```

The `verify_api_key` dependency validates the key using constant-time comparison.
API key auth grants full access (no role distinction). Use it for trusted
server-to-server communication.

## Creating Users

### Via CLI

```bash
# Create a regular user
uv run agent user create --email user@example.com --password secret

# Create an admin user
uv run agent user create-admin --email admin@example.com --password secret

# Change user role
uv run agent user set-role user@example.com --role admin
```

### Via Make

```bash
make create-admin    # Interactive admin creation
make user-create     # Interactive user creation
make user-list       # List all users
```

### Via Quickstart

```bash
make quickstart      # Creates admin@example.com / admin123 automatically
```
