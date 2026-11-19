"""Working-task lifecycle with real transactions and offline model/worker fixtures."""

import asyncio
import os
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AlreadyExistsError, BadRequestError, NotFoundError
from app.db.models.conversation import Message
from app.db.models.work_task import WorkTask, WorkTaskConversation, WorkTaskRevision
from app.db.session import get_worker_db_context
from app.repositories.agent_run import AgentRunRepository
from app.schemas.agent_run import AgentRunResume
from app.schemas.project import ProjectWrite
from app.schemas.work_task import WorkTaskControl
from app.services.agent_run import AgentRunService
from app.services.chat_execution import prepare_context
from app.services.conversation_context import revalidate
from app.services.model_config import resolve_generation_config
from app.services.project import ProjectService
from app.services.run_artifact import RunArtifactService
from app.services.work_task import WorkTaskService
from app.services.work_task_intent import intent
from app.worker.agent_runs import try_run
from tests.model_fixtures import ScriptedModel, tool_delta
from tests.test_agent_runs_integration import get, text_stream, users
from tests.test_durable_chat import state, submit

pytestmark = pytest.mark.skipif(os.getenv("RUN_TASK_DB_TESTS") != "1", reason="disposable DB only")


def selection(run, action="continue", revision=None):
    ref = run.request["work_task"]
    return {
        "action": action,
        "task_id": ref["id"],
        "expected_revision": revision or ref["revision"],
    }


async def describe(uid, run, project_id=None):
    async with get_worker_db_context() as db:
        service = WorkTaskService(db, uid, project_id=project_id)
        return await service.describe(await service.owned(UUID(run.request["work_task"]["id"])))


async def execute(run):
    with patch(
        "app.agents.assistant._build_model", return_value=ScriptedModel(stream_function=text_stream)
    ):
        await try_run(run.id)


def test_intent_is_conservative_and_explicit():
    assert intent("数学题：计算一个二次函数的零点") is None
    assert intent("今天晚饭怎么做") is None
    assert intent("创建任务：整理资料") == "new"
    assert intent("分析两种方案，比较优缺点并导出报告") == "new"
    assert intent("继续") == "continue"
    assert intent("暂停当前任务") == "pause"
    assert intent("把当前任务改成只生成 Markdown") == "revise"


def test_work_survives_turns_new_conversations_and_topic_changes():
    async def check():
        seen = []

        async def stream(messages, info):
            seen.append(str(messages))
            yield "前一步已经整理的独特结果"

        async with users() as (a, b):
            first = await submit(
                a, message="创建任务：比较甲乙两种方案，预算严格限制为 73 元，导出报告"
            )
            task_id = UUID(first.request["work_task"]["id"])
            with patch(
                "app.agents.assistant._build_model",
                return_value=ScriptedModel(stream_function=stream),
            ):
                await try_run(first.id)
                other = await submit(
                    a, conversation_id=first.conversation_id, message="番茄炒蛋怎么做？"
                )
                assert "work_task" not in other.request
                await try_run(other.id)
                second = await submit(a, message="继续")  # unique project task, fresh conversation
                assert second.conversation_id != first.conversation_id
                assert second.request["work_task"]["id"] == str(task_id)
                await try_run(second.id)
            assert "73 元" in seen[-1] and "前一步已经整理的独特结果" in seen[-1]
            assert "番茄炒蛋" not in seen[-1]
            saved = await describe(a, second)
            assert saved["status"] == "active"  # a successful turn is not acceptance
            assert len(saved["steps"]) == 2 and all(
                s["status"] == "completed" for s in saved["steps"]
            )
            async with get_worker_db_context() as db:
                assert (await WorkTaskService(db, a).list(first.conversation_id))[0]["id"] == str(
                    task_id
                )
                with pytest.raises(NotFoundError):
                    await WorkTaskService(db, b).owned(task_id)
                assert await WorkTaskService(db, b).list() == []
            done = await submit(
                a,
                conversation_id=second.conversation_id,
                message="当前任务已完成",
                work_task=selection(second, "complete"),
            )
            assert done.status == "completed" and done.attempt == 0
            assert (await describe(a, second))["status"] == "completed"
            restored = await submit(a, message="继续完成", work_task=selection(second, revision=2))
            assert restored.request["work_task"]["revision"] == 3

    asyncio.run(check())


def test_project_isolation_and_database_rejects_cross_scope_links():
    async def check():
        async with users() as (a, b):
            async with get_worker_db_context() as db:
                project = await ProjectService(db, a).save(ProjectWrite(name="隔离项目"))
            first = await submit(a, project_id=project.id, message="创建任务：项目内目标")
            foreign = await submit(b, message="另一个账号的秘密")
            local = await submit(a, message="默认项目内容")
            with pytest.raises(NotFoundError):
                await submit(a, message="继续", work_task=selection(first))
            with pytest.raises(NotFoundError):
                await submit(b, message="继续", work_task=selection(first))
            assert "work_task" not in (await submit(a, message="继续")).request
            task_id = UUID(first.request["work_task"]["id"])
            for cid in (foreign.conversation_id, local.conversation_id):
                with pytest.raises(IntegrityError):
                    async with get_worker_db_context() as db:
                        db.add(WorkTaskConversation(task_id=task_id, conversation_id=cid))
                        await db.flush()
            with pytest.raises(IntegrityError):
                async with get_worker_db_context() as db:
                    db.add(
                        WorkTaskRevision(
                            task_id=task_id,
                            revision=2,
                            source_message_id=foreign.user_message_id,
                            source_hash="0" * 64,
                            created_at=first.created_at,
                        )
                    )
                    await db.flush()

    asyncio.run(check())


def test_revision_bypasses_waiting_input_and_old_approval_cannot_resume():
    async def stream(messages, info):
        yield {
            0: tool_delta(
                name="ask_user",
                json_args='{"questions":[{"question":"选择格式？","options":["Word","PPT"]}]}',
                tool_call_id="format",
            )
        }

    async def check():
        async with users() as (a, _):
            first = await submit(a, message="创建任务：整理任务报告")
            with patch(
                "app.agents.assistant._build_model",
                return_value=ScriptedModel(stream_function=stream),
            ):
                await try_run(first.id)
            old = await get(a, first.id)
            assert old.status == "waiting_input", old.error
            second = await submit(
                a,
                conversation_id=first.conversation_id,
                message="只生成 Markdown，增加成本分析",
                work_task=selection(first, "revise"),
            )
            assert (await get(a, first.id)).status == "cancelled"
            assert second.request["work_task"]["revision"] == 2
            async with get_worker_db_context() as db:
                with pytest.raises(AlreadyExistsError):
                    await AgentRunService(db, a).resume(
                        first.id,
                        AgentRunResume(
                            question_id=old.pending_input["question_id"],
                            answers={"format": ["Word"]},
                        ),
                    )
            await execute(second)
            assert (await get(a, second.id)).status == "completed"
            desc = await describe(a, second)
            assert len(desc["requirements"]) == 2 and desc["steps"][1]["historical"]

    asyncio.run(check())


def test_pause_control_is_atomic_idempotent_and_works_at_capacity_without_model():
    async def check():
        async with users() as (a, _):
            first = await submit(a, message="创建任务：等待处理")
            for i in range(4):
                await submit(a, message=f"普通请求 {i}")
            key = uuid4()
            with patch(
                "app.services.chat_turn.resolve_generation_config",
                side_effect=AssertionError("control must not resolve model"),
            ):
                one, two = await asyncio.gather(
                    *[
                        submit(
                            a,
                            conversation_id=first.conversation_id,
                            message="暂停当前任务",
                            idempotency_key=key,
                            work_task=selection(first, "pause"),
                        )
                        for _ in range(2)
                    ]
                )
            assert one.id == two.id and one.status == "completed"
            assert (await get(a, first.id)).status == "cancelled"
            assert (await describe(a, first))["revision"] == 2
            messages = (await state(a, first.conversation_id))["messages"]
            assert len(messages) == 4 and "任务已暂停" in messages[-1].content
            with pytest.raises(AlreadyExistsError):
                await submit(a, message="调整目标", work_task=selection(first, "revise"))

    asyncio.run(check())


def test_two_windows_cannot_overwrite_same_revision_and_repeated_control_is_idempotent():
    async def check():
        async with users() as (a, _):
            first = await submit(a, message="创建任务：最初要求")
            results = await asyncio.gather(
                *[
                    submit(a, message=f"新要求 {i}", work_task=selection(first, "revise"))
                    for i in range(2)
                ],
                return_exceptions=True,
            )
            assert sum(isinstance(r, AlreadyExistsError) for r in results) == 1
            second = next(r for r in results if not isinstance(r, Exception))
            data = WorkTaskControl(operation_id=uuid4(), expected_revision=2, action="cancel")
            for _ in range(2):
                async with get_worker_db_context() as db:
                    task = await WorkTaskService(db, a).control(
                        UUID(first.request["work_task"]["id"]), data
                    )
                    assert task.revision == 3
            assert (await get(a, second.id)).status == "cancelled"

    asyncio.run(check())


def test_old_stream_and_artifact_cannot_commit_after_goal_change():
    async def check():
        entered, release = asyncio.Event(), asyncio.Event()

        async def stream(messages, info):
            yield "旧版本的部分内容"
            entered.set()
            await release.wait()
            yield "不允许写入的迟到结果"

        async with users() as (a, _):
            first = await submit(a, message="创建任务：生成原始报告")
            with patch(
                "app.agents.assistant._build_model",
                return_value=ScriptedModel(stream_function=stream),
            ):
                running = asyncio.create_task(try_run(first.id))
                try:
                    await asyncio.wait_for(entered.wait(), 10)
                    second = await submit(
                        a, message="新的完整目标", work_task=selection(first, "replace")
                    )
                    assert (await get(a, first.id)).status == "cancelling"
                    async with get_worker_db_context() as db:
                        assert second.id not in await AgentRunRepository(db).candidates()
                        with pytest.raises(AlreadyExistsError):
                            await RunArtifactService(db, a).save(first.id, 1, uuid4(), [])
                    release.set()
                    await asyncio.wait_for(running, 10)
                finally:
                    release.set()
                    if not running.done():
                        running.cancel()
                        await asyncio.gather(running, return_exceptions=True)
            saved = await get(a, first.id)
            assert saved.status == "cancelled"
            messages = (await state(a, first.conversation_id))["messages"]
            assert "不允许写入的迟到结果" not in messages[-1].content
            async with get_worker_db_context() as db:
                assert second.id in await AgentRunRepository(db).candidates()
            await execute(second)
            assert (await get(a, second.id)).status == "completed"

    asyncio.run(check())


def test_restart_and_checkpoint_removal_do_not_remove_work_state():
    async def check():
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from app.worker.agent_runs import connect

        entered, release = asyncio.Event(), asyncio.Event()

        async def stream(messages, info):
            entered.set()
            await release.wait()
            yield "恢复后保存的结果"

        async with users() as (a, _):
            first = await submit(a, message="创建任务：需要跨天恢复的工作")
            with patch(
                "app.agents.assistant._build_model",
                return_value=ScriptedModel(stream_function=stream),
            ):
                worker = asyncio.create_task(try_run(first.id))
                await asyncio.wait_for(entered.wait(), 10)
                worker.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await worker
                assert (await get(a, first.id)).status == "running"
                release.set()
                await try_run(first.id)
            assert (await get(a, first.id)).attempt == 2
            async with await connect() as conn:
                await AsyncPostgresSaver(conn).adelete_thread(f"run:{first.id}")
            task = await describe(a, first)
            assert task["status"] == "active" and len(task["steps"]) == 1
            assert task["steps"][0]["status"] == "completed"

    asyncio.run(check())


def test_source_changes_fail_closed_and_full_replacement_restores_validity():
    async def check():
        async with users() as (a, _):
            first = await submit(a, message="创建任务：必须保留的数值为 17.92")
            await execute(first)
            second = await submit(a, message="继续", work_task=selection(first))
            config = resolve_generation_config({})
            context = await prepare_context(second.request, a, None, config)
            assert "17.92" in context["work_context"]
            async with get_worker_db_context() as db:
                source = await db.get(Message, first.user_message_id)
                source.content = "后来被编辑的内容，不再可信"
            with pytest.raises(BadRequestError):
                await revalidate(second.request, context, a, None)
            await execute(second)
            assert (await get(a, second.id)).status == "failed"
            desc = await describe(a, first)
            assert not desc["source_valid"] and desc["requirements"][0]["content"] is None
            with pytest.raises(BadRequestError):
                await submit(a, message="继续", work_task=selection(first))
            third = await submit(
                a, message="替换后的完整新要求", work_task=selection(first, "replace")
            )
            assert (await describe(a, third))["source_valid"]
            async with get_worker_db_context() as db:
                await db.execute(delete(Message).where(Message.id == first.user_message_id))
                # Old source deletion doesn't invalidate a new full replacement.
                current = await db.get(WorkTask, UUID(third.request["work_task"]["id"]))
                assert (await WorkTaskService(db, a).requirements(current))[1]
            await execute(third)
            assert (await get(a, third.id)).status == "completed"

    asyncio.run(check())


def test_complete_requirements_are_budgeted_strict_excludes_prior_assistant_results():
    async def check():
        from app.services.context_budget import cost, envelope

        async with users() as (a, _):
            first = await submit(a, message="创建任务：不能省略的关键约束是 98.71")
            await execute(first)
            second = await submit(a, message="继续", work_task=selection(first))
            async with get_worker_db_context() as db:
                service = WorkTaskService(db, a)
                plain = await service.context(second.request)
                strict = await service.context(
                    {
                        **second.request,
                        "knowledge_base_ids": [str(uuid4())],
                        "knowledge_strict": True,
                    }
                )
            assert "持久保存" in plain and "持久保存" not in strict
            config = resolve_generation_config({})
            budgets = envelope({**second.request, "work_context": plain}, config)
            assert budgets["work"] == cost(plain) and "98.71" in plain
            with pytest.raises(BadRequestError):
                envelope({**second.request, "work_context": "完整目标" * 40000}, config)
            # Historical replies are checked too, not copied blindly from a checkpoint.
            context = await prepare_context(second.request, a, None, config)
            async with get_worker_db_context() as db:
                answer = await db.get(Message, first.assistant_message_id)
                answer.content = "被篡改的回复"
            with pytest.raises(BadRequestError):
                await revalidate(second.request, context, a, None)

    asyncio.run(check())


def test_business_context_rebuilds_progress_and_scoped_artifact_references():
    async def check():
        import hashlib

        from app.db.models.run_artifact import RunArtifact

        async with users() as (a, b):
            first = await submit(a, message="创建任务：比较方案，预算不得超过 98.71 元")
            await execute(first)
            artifact_id, foreign_id = uuid4(), uuid4()
            content = b"outline"
            async with get_worker_db_context() as db:
                for aid, uid in [(artifact_id, a), (foreign_id, b)]:
                    db.add(
                        RunArtifact(
                            id=aid,
                            run_id=first.id,
                            user_id=uid,
                            execution_id=uuid4(),
                            name="outline.md",
                            mime_type="text/markdown",
                            size=len(content),
                            sha256=hashlib.sha256(content).hexdigest(),
                            content=content,
                        )
                    )
            second = await submit(a, message="继续", work_task=selection(first))
            assert second.conversation_id != first.conversation_id
            async with get_worker_db_context() as db:
                snapshot = await WorkTaskService(db, a).context_snapshot(second.request)
                strict = await WorkTaskService(db, a).context_snapshot(
                    {
                        **second.request,
                        "knowledge_base_ids": [str(uuid4())],
                        "knowledge_strict": True,
                    }
                )
            assert snapshot.current_message_id == str(second.user_message_id)
            assert "98.71" in snapshot.requirements[0].requirement
            assert snapshot.progress[0].run_id == str(first.id)
            assert snapshot.progress[0].status == "completed"
            assert [f.id for f in snapshot.artifacts] == [str(artifact_id)]
            assert snapshot.artifacts[0].verification == "not_verified"
            assert snapshot.artifacts[0].validation is None
            assert str(foreign_id) not in snapshot.model_dump_json()
            assert strict.previous_results == [] and strict.artifacts == snapshot.artifacts

    asyncio.run(check())


def test_ambiguous_continue_creates_a_clarification_without_mutating_either_task():
    async def check():
        async with users() as (a, _):
            first = await submit(a, message="创建任务：工作 A")
            second = await submit(a, message="创建任务：工作 B")
            clarified = await submit(a, message="继续")
            assert clarified.status == "completed" and clarified.request["action"] == "clarify"
            assert "多个" in clarified.result["content"]
            assert (
                (await describe(a, first))["revision"]
                == (await describe(a, second))["revision"]
                == 1
            )

    asyncio.run(check())


@pytest.mark.parametrize("named_project", [False, True])
def test_python_reuses_selected_task_output_across_conversations(named_project):
    import base64
    import json
    from unittest.mock import AsyncMock

    from app.core.config import settings
    from app.db.models.run_artifact import RunArtifact
    from app.services import sandbox_client
    from app.services.artifact_validation import inspect_artifact
    from app.services.sandbox_files import input_name, load_execution_inputs, validate_artifacts
    from tests.test_sandbox_files import artifact

    async def check():
        async with users() as (a, b):
            project_id = None
            if named_project:
                async with get_worker_db_context() as db:
                    project_id = (await ProjectService(db, a).save(ProjectWrite(name="Files"))).id
            first = await submit(a, project_id=project_id, message="创建任务：计算数据并核对结果")
            await execute(first)
            file = validate_artifacts([artifact()], "completed")[0]
            fid = uuid4()
            async with get_worker_db_context() as db:
                db.add(
                    RunArtifact(
                        id=fid,
                        run_id=first.id,
                        user_id=a,
                        execution_id=uuid4(),
                        validation=inspect_artifact(file),
                        **file,
                    )
                )
            selected_path = "/inputs/" + input_name(fid, file["name"])
            code = f"print(open({selected_path!r}).read())"
            seen = []

            async def stream(messages, info):
                seen.append(str(messages))
                if any(
                    getattr(p, "name", None) == "run_python" and p.type == "tool" for p in messages
                ):
                    yield "已读取上一轮文件并计算"
                else:
                    yield {
                        0: tool_delta(
                            name="run_python",
                            json_args=json.dumps({"code": code, "artifact_ids": [str(fid)]}),
                            tool_call_id="reuse",
                        )
                    }

            with (
                patch.object(settings, "SANDBOX_ALLOW_PUBLIC", True),
                patch.object(
                    sandbox_client,
                    "health",
                    AsyncMock(
                        return_value={
                            "status": "ready",
                            "file_execution": {"inputs_read_only": True},
                        }
                    ),
                ),
                patch.object(
                    sandbox_client,
                    "run_python",
                    AsyncMock(
                        return_value={
                            "state": "completed",
                            "execution_id": str(uuid4()),
                            "exit_code": 0,
                            "stdout": "a,b\n1,2",
                        }
                    ),
                ) as remote,
                patch(
                    "app.agents.assistant._build_model",
                    return_value=ScriptedModel(stream_function=stream),
                ),
            ):
                second = await submit(
                    a,
                    project_id=project_id,
                    message="继续读取此前文件计算",
                    python_enabled=True,
                    work_task=selection(first),
                )
                assert second.conversation_id != first.conversation_id
                await try_run(second.id)
                async with get_worker_db_context() as db:
                    saved = await AgentRunService(db, a, project_id=project_id).get(second.id)
                    context = await WorkTaskService(db, a, project_id=project_id).context(
                        second.request
                    )
                    restored = json.loads(context.rsplit("\n", 1)[-1])
                    assert restored["artifacts"][0]["validation"]["sha256"] == file["sha256"]
                assert saved.status == "completed", saved.error
                assert selected_path in seen[0]
                remote.assert_awaited_once()
                mounted = remote.call_args.kwargs["inputs"]
                assert base64.b64decode(mounted[0]["content_base64"]) == file["content"]
                assert mounted[0]["name"] == selected_path.removeprefix("/inputs/")
                assert "content_base64" not in str(saved.result)
                # Repeated loads reconstruct the identical input identity without storing bytes.
                async with get_worker_db_context() as db:
                    again, _ = await load_execution_inputs(
                        db,
                        a,
                        second.request,
                        artifact_ids=[fid],
                        work_context=context,
                        project_id=project_id,
                    )
                    assert again == mounted
                    with pytest.raises(NotFoundError):
                        await load_execution_inputs(
                            db,
                            b,
                            second.request,
                            artifact_ids=[fid],
                            work_context=context,
                            project_id=project_id,
                        )
                    with pytest.raises(NotFoundError):
                        await load_execution_inputs(
                            db,
                            a,
                            second.request,
                            artifact_ids=[fid],
                            work_context=context,
                            project_id=None if named_project else uuid4(),
                        )
                # Same account/project, unrelated task: no inherited access to this file.
                unrelated = await submit(a, project_id=project_id, message="创建任务：另一个目标")
                async with get_worker_db_context() as db:
                    other = await WorkTaskService(db, a, project_id=project_id).context(
                        unrelated.request
                    )
                    with pytest.raises(NotFoundError):
                        await load_execution_inputs(
                            db,
                            a,
                            {**unrelated.request, "sandbox_protocol": 2},
                            artifact_ids=[fid],
                            work_context=other,
                            project_id=project_id,
                        )
                # Same-length corruption is rejected even when database metadata is unchanged.
                async with get_worker_db_context() as db:
                    item = await RunArtifactService(db, a, project_id=project_id).get(first.id, fid)
                    item.content = b"a,b\n3,4"
                async with get_worker_db_context() as db:
                    with pytest.raises(BadRequestError, match="完整性"):
                        await load_execution_inputs(
                            db,
                            a,
                            second.request,
                            artifact_ids=[fid],
                            work_context=context,
                            project_id=project_id,
                        )
                    await RunArtifactService(db, a, project_id=project_id).delete(first.id, fid)
                async with get_worker_db_context() as db:
                    with pytest.raises(BadRequestError, match="已变化"):
                        await load_execution_inputs(
                            db,
                            a,
                            second.request,
                            artifact_ids=[fid],
                            work_context=context,
                            project_id=project_id,
                        )
                await submit(
                    a,
                    project_id=project_id,
                    message="更新任务目标",
                    work_task=selection(second, "revise"),
                )
                async with get_worker_db_context() as db:
                    with pytest.raises(AlreadyExistsError):
                        await load_execution_inputs(
                            db,
                            a,
                            second.request,
                            artifact_ids=[fid],
                            work_context=context,
                            project_id=project_id,
                        )

    asyncio.run(check())
