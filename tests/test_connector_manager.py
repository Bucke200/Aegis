"""
Tests for the social media connector manager.
"""

import asyncio
from datetime import datetime

import pytest

from ingestion.base_connector import BaseSocialMediaConnector
from ingestion.connector_manager import (
    MonitoringMode,
    MonitoringTask,
    SocialMediaConnectorManager,
)
from messaging.schemas import SourceType


class FakeConnector(BaseSocialMediaConnector):
    """Minimal connector used to exercise the manager without network access."""

    def __init__(self):
        super().__init__(source_type=SourceType.TWITTER, api_credentials={})
        self.search_queries = []
        self.stream_calls = 0

    async def _get_default_headers(self):
        return {}

    async def _validate_credentials(self):
        return True

    async def _setup_rate_limiting(self):
        return None

    async def search_posts(self, query, limit=100, since=None):
        self.search_queries.append(query)
        yield {
            "post_id": "1",
            "author_id": "7",
            "author_username": "user",
            "content": f"mention of {query}",
            "created_at": datetime.utcnow(),
        }

    async def get_user_posts(self, user_id, limit=100, since=None):
        if False:
            yield {}

    async def stream_real_time(self, keywords, callback):
        self.stream_calls += 1


def build_manager():
    manager = SocialMediaConnectorManager()
    connector = FakeConnector()
    manager.connectors[SourceType.TWITTER] = connector
    manager.is_running = True
    return manager, connector


def make_task(task_id, mode=MonitoringMode.SEARCH_ONLY, interval=300):
    return MonitoringTask(
        task_id=task_id,
        keywords=["scam"],
        vips=["VIP"],
        platforms=[SourceType.TWITTER],
        mode=mode,
        interval=interval,
    )


@pytest.mark.asyncio
async def test_callbacks_use_consistent_signature():
    manager, _ = build_manager()
    captured = []

    async def callback(post, task_id, monitored_vip, keyword):
        captured.append((post, task_id, monitored_vip, keyword))

    manager.add_message_callback(callback)
    manager.monitoring_tasks["task1"] = make_task("task1")

    await manager._handle_search_result({"content": "VIP scam"}, "task1", "scam")
    await manager._handle_stream_message({"content": "VIP"}, "task1")

    assert len(captured) == 2
    assert captured[0][1] == "task1"
    assert captured[0][2] == "VIP"
    assert captured[0][3] == "scam"
    assert captured[1][3] is None


@pytest.mark.asyncio
async def test_polling_uses_search_instead_of_stream():
    manager, connector = build_manager()

    original_dispatch = manager._handle_search_result

    async def stop_after_first(post, task_id, keyword):
        await original_dispatch(post, task_id, keyword)
        manager._stop_event.set()

    manager._handle_search_result = stop_after_first

    task = make_task("poll", mode=MonitoringMode.POLLING, interval=0)
    manager.monitoring_tasks[task.task_id] = task

    await asyncio.wait_for(
        manager._run_polling_monitoring(task, task.platforms), timeout=2
    )

    assert connector.stream_calls == 0
    assert set(connector.search_queries) == {"scam", "VIP"}


@pytest.mark.asyncio
async def test_stop_monitoring_removes_task():
    manager, _ = build_manager()
    task = make_task("stopme")
    manager.monitoring_tasks[task.task_id] = task
    manager.active_streams[task.task_id] = asyncio.create_task(asyncio.sleep(30))

    stopped = await manager.stop_monitoring("stopme")

    assert stopped is True
    assert "stopme" not in manager.monitoring_tasks
    assert "stopme" not in manager.active_streams
