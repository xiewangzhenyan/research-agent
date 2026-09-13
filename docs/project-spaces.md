# Project spaces and account knowledge

Knowledge bases belong to an account. Multiple projects can reference the same
knowledge base without copying documents, chunks or embeddings. The knowledge
page always lists the authenticated account's libraries.

A project stores a name, description and up to five default knowledge base IDs.
New conversations and tasks snapshot these defaults. Explicit knowledge selection
overrides them, including an empty selection. Changing defaults does not rewrite
existing conversations or task requests. Deleted libraries disappear from project
defaults; existing conversation scopes retain their unavailable-selection warning.

## Scope contract

- `GET/POST /api/v1/projects` and `PUT /api/v1/projects/{id}` manage account-owned
  projects. Up to 50 named projects per account.
- `X-Project-ID: <uuid>` selects a named workspace for conversation and task APIs.
  Omission means **only the default project**, never all projects.
- Normal chat uses `/api/v1/chat/turns` and scoped conversation state endpoints; see [durable chat](durable-chat.md).
- Legacy WebSocket clients connect to `/api/v1/ws/agent?project_id=<uuid>`. The scope is
  validated before accepting the connection and fixed for that connection.
  Authentication remains in the existing token subprotocol, not in the URL.
- Conversation lists, counts, messages, mutations and owner share actions respect
  scope. Existing explicit recipient shares and public read links retain their
  authorization rules. Admin inspection uses the dedicated admin endpoints;
  ordinary chat endpoints apply workspace ownership even to administrators.
- Task detail, events, cancellation, human replies and artifact operations require
  both the account and project. Idempotency keys remain account-wide; reusing one
  in another project is rejected. The five-active-task limit remains account-wide.
- Workers use the project stored on the task, revalidate ownership at execution,
  and pass that scope to artifact persistence. Checkpoints remain keyed by unique
  run ID, independent of the user's browser selection.

The database uses nullable `project_id` columns on conversations and tasks, with
composite foreign keys binding project and account. Existing NULL rows stay in
the default workspace. No backfill or knowledge ownership migration is required.
The additive migration is compatible with old writers. Do not roll back application
code to a version without scope checks after creating named-project resources:
older readers do not know how to isolate them. Migration downgrade refuses to
collapse populated project namespaces.

## Browser behavior

Selection lives in `sessionStorage`, keyed by account, so tabs can select different
projects. Switching performs a full navigation to a fresh chat, disposing the old
socket, query cache, selected task and conversation state. Selection is committed
in the new document, so cancelling an unsaved-input warning leaves the old scope
intact. Streaming chat warns before switching; background tasks continue in their
original project. Artifact downloads use authenticated scoped fetches.

Project deletion, resource moves and cross-account team libraries are not implemented.
Opt-in, user-confirmed [project memory](project-memory.md) uses the same account/project
boundary. Knowledge base ownership remains account-wide and independent of memory.

## Verification

Run `tests/test_project_spaces_integration.py` only on a migrated disposable
PostgreSQL database whose name ends in `_review`, with `RUN_TASK_DB_TESTS=1`.
Set up LangGraph checkpoint tables using `python -m app.worker.agent_runs --setup`.
The suite exercises account-wide library reuse, default snapshots, project access,
legacy NULL scope, WebSocket history rejection, task idempotency, event/artifact
boundaries, database owner constraints and deleted-library handling.

Also run the conversation/knowledge regression workflow and frontend project scope,
knowledge selector, task proxy and artifact panel tests. Browser checks must cover
separate tabs, project switching, stale URLs, unsaved input and mobile dialogs.
