"""Agent 侧环境封装。"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .agent_action import SocialAction

if TYPE_CHECKING:
    from social_platform.platform import Platform


class SocialEnvironment:
    """把平台状态转成 agent 可读取观察的轻量适配器。"""

    def __init__(self, agent_id: int, action: SocialAction | None = None) -> None:
        self.agent_id = agent_id
        self.action = action

    def bind(self, action: SocialAction | None = None) -> None:
        if action is not None:
            self.action = action

    async def get_feed(self) -> List[dict]:
        """异步读取 agent 当前可见的信息流。"""

        if self.action is None:
            raise RuntimeError("SocialEnvironment requires a bound SocialAction.")
        result = await self.action.browse_feed()
        return list(result.get("feed", [])) if result.get("success") else []

    def get_feed_snapshot(self, platform: Platform) -> List[dict]:
        """直接从平台对象读取一份同步快照。"""
        return platform.get_feed_for_agent(self.agent_id)

    def to_text_prompt(self, feed: List[dict], scenario_prompt: str) -> str:
        """把场景和部分 feed 内容拼成文本提示。"""

        parts = [scenario_prompt.strip()]
        for item in feed[:3]:
            parts.append(str(item.get("content", "")).strip())
        return " ".join(part for part in parts if part)
