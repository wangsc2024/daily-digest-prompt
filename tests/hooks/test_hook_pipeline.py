"""
tests/hooks/test_hook_pipeline.py — HookPipeline TDD（P1-A）

覆蓋重點：
  - HookPipeline 短路機制（block 即停止）
  - 中介軟體累積 modified 欄位傳遞
  - compose_pipeline / compose_middlewares 工廠函數
  - log_trace_middleware / schema_validate_middleware 內建中介軟體
  - build_worker_pipeline（P5-A 整合點）
  - hook_utils.compose_middlewares 委派
"""
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from hook_pipeline import (  # noqa: E402
    HookPipeline,
    allow_all_middleware,
    build_worker_pipeline,
    compose_pipeline,
    log_trace_middleware,
    schema_validate_middleware,
)


# ─── fixtures & helpers ──────────────────────────────────────────────────────

def make_block_middleware(reason: str = "blocked"):
    def _block(context: dict) -> dict:
        return {"decision": "block", "reason": reason, "guard_tag": "test-guard"}
    _block.__name__ = f"block({reason})"
    return _block


def make_allow_middleware(tag: str = "allow"):
    def _allow(context: dict) -> dict:
        return {"decision": "allow", "modified": {tag: True}}
    _allow.__name__ = f"allow_{tag}"
    return _allow


# ─── HookPipeline 基本行為 ───────────────────────────────────────────────────

class TestHookPipelineBasic:
    def test_empty_pipeline_returns_allow(self):
        pipeline = HookPipeline([])
        result = pipeline.execute({})
        assert result["decision"] == "allow"

    def test_single_allow_returns_allow(self):
        pipeline = HookPipeline([allow_all_middleware])
        result = pipeline.execute({"tool": "Bash"})
        assert result["decision"] == "allow"

    def test_single_block_returns_block(self):
        blocker = make_block_middleware("test reason")
        pipeline = HookPipeline([blocker])
        result = pipeline.execute({})
        assert result["decision"] == "block"
        assert result["reason"] == "test reason"

    def test_len_returns_middleware_count(self):
        pipeline = HookPipeline([allow_all_middleware, allow_all_middleware])
        assert len(pipeline) == 2

    def test_repr_contains_middleware_names(self):
        pipeline = HookPipeline([allow_all_middleware])
        assert "allow_all_middleware" in repr(pipeline)


# ─── 短路機制（short-circuit）───────────────────────────────────────────────

class TestShortCircuit:
    def test_block_stops_subsequent_middlewares(self):
        executed = []

        def track_allow(context):
            executed.append("track_allow")
            return {"decision": "allow"}

        pipeline = HookPipeline([
            make_block_middleware("early block"),
            track_allow,
        ])
        result = pipeline.execute({})

        assert result["decision"] == "block"
        assert "track_allow" not in executed  # 後續不應執行

    def test_allow_continues_all_middlewares(self):
        executed = []

        def mw1(context):
            executed.append("mw1")
            return {"decision": "allow"}

        def mw2(context):
            executed.append("mw2")
            return {"decision": "allow"}

        pipeline = HookPipeline([mw1, mw2])
        pipeline.execute({})
        assert executed == ["mw1", "mw2"]

    def test_block_in_middle_stops_chain(self):
        calls = []

        def mw_before(ctx):
            calls.append("before")
            return {"decision": "allow"}

        def mw_block(ctx):
            calls.append("block")
            return {"decision": "block", "reason": "mid-block"}

        def mw_after(ctx):
            calls.append("after")
            return {"decision": "allow"}

        pipeline = HookPipeline([mw_before, mw_block, mw_after])
        result = pipeline.execute({})

        assert calls == ["before", "block"]
        assert result["decision"] == "block"


# ─── modified 欄位累積傳遞 ───────────────────────────────────────────────────

class TestModifiedPropagation:
    def test_modified_fields_accumulate(self):
        pipeline = HookPipeline([
            make_allow_middleware("step1"),
            make_allow_middleware("step2"),
        ])
        result = pipeline.execute({})
        assert result["modified"]["step1"] is True
        assert result["modified"]["step2"] is True

    def test_later_middleware_sees_earlier_modified(self):
        seen_value = {}

        def mw1(ctx):
            return {"decision": "allow", "modified": {"shared_key": "value_from_mw1"}}

        def mw2(ctx):
            seen_value["shared_key"] = ctx.get("shared_key")
            return {"decision": "allow"}

        pipeline = HookPipeline([mw1, mw2])
        pipeline.execute({})
        assert seen_value["shared_key"] == "value_from_mw1"

    def test_original_context_not_mutated(self):
        original = {"tool": "Bash", "command": "ls"}
        pipeline = HookPipeline([make_allow_middleware("extra")])
        pipeline.execute(original)
        # 原始 context 不應被修改
        assert "extra" not in original


# ─── compose_pipeline 工廠 ───────────────────────────────────────────────────

class TestComposePipeline:
    def test_returns_hook_pipeline_instance(self):
        pipeline = compose_pipeline([allow_all_middleware])
        assert isinstance(pipeline, HookPipeline)

    def test_empty_list_creates_empty_pipeline(self):
        pipeline = compose_pipeline([])
        assert len(pipeline) == 0

    def test_multiple_middlewares_in_order(self):
        order = []

        def mw_a(ctx):
            order.append("a")
            return {"decision": "allow"}

        def mw_b(ctx):
            order.append("b")
            return {"decision": "allow"}

        compose_pipeline([mw_a, mw_b]).execute({})
        assert order == ["a", "b"]


# ─── 內建中介軟體 ────────────────────────────────────────────────────────────

class TestLogTraceMiddleware:
    def test_injects_trace_with_timestamp(self):
        result = log_trace_middleware({"tool": "Write"})
        assert result["decision"] == "allow"
        trace = result["modified"]["_trace"]
        assert "timestamp" in trace
        assert trace["tool"] == "Write"

    def test_unknown_tool_defaults_to_unknown(self):
        result = log_trace_middleware({})
        assert result["modified"]["_trace"]["tool"] == "unknown"


class TestSchemaValidateMiddleware:
    def test_all_fields_present_returns_allow(self):
        mw = schema_validate_middleware(["task_id", "worker_type"])
        result = mw({"task_id": "abc", "worker_type": "web_search"})
        assert result["decision"] == "allow"

    def test_missing_field_returns_block(self):
        mw = schema_validate_middleware(["task_id", "worker_type"])
        result = mw({"task_id": "abc"})  # worker_type 缺失
        assert result["decision"] == "block"
        assert "worker_type" in result["reason"]
        assert result["guard_tag"] == "schema-guard"

    def test_empty_required_list_always_allow(self):
        mw = schema_validate_middleware([])
        result = mw({})
        assert result["decision"] == "allow"

    def test_middleware_name_reflects_fields(self):
        mw = schema_validate_middleware(["task_id"])
        assert "task_id" in mw.__name__


# ─── build_worker_pipeline（P5-A 整合點）────────────────────────────────────

class TestBuildWorkerPipeline:
    @pytest.mark.parametrize("worker_type", [
        "web_search", "kb_import", "file_sync", "notification"
    ])
    def test_known_worker_types_return_pipeline(self, worker_type):
        pipeline = build_worker_pipeline(worker_type)
        assert isinstance(pipeline, HookPipeline)
        assert len(pipeline) > 0

    def test_valid_context_passes_web_search_pipeline(self):
        pipeline = build_worker_pipeline("web_search")
        result = pipeline.execute({"task_id": "t1", "worker_type": "web_search"})
        assert result["decision"] == "allow"

    def test_missing_task_id_blocks_pipeline(self):
        pipeline = build_worker_pipeline("kb_import")
        result = pipeline.execute({"worker_type": "kb_import"})  # task_id 缺失
        assert result["decision"] == "block"

    def test_unknown_worker_type_still_returns_pipeline(self):
        pipeline = build_worker_pipeline("future_worker_type")
        assert isinstance(pipeline, HookPipeline)


# ─── hook_utils.compose_middlewares 委派 ─────────────────────────────────────

class TestHookUtilsComposeMiddlewares:
    def test_compose_middlewares_delegates_to_pipeline(self):
        HOOKS_DIR_STR = str(HOOKS_DIR)
        if HOOKS_DIR_STR not in sys.path:
            sys.path.insert(0, HOOKS_DIR_STR)

        from hook_utils import compose_middlewares
        pipeline = compose_middlewares([allow_all_middleware])
        assert isinstance(pipeline, HookPipeline)

    def test_compose_middlewares_executes_correctly(self):
        from hook_utils import compose_middlewares
        pipeline = compose_middlewares([make_block_middleware("via utils")])
        result = pipeline.execute({})
        assert result["decision"] == "block"
        assert result["reason"] == "via utils"
