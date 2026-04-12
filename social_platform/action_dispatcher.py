"""把通道消息翻译成具体平台操作的分发器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .platform import Platform


class PlatformActionDispatcher:
    """把动作名路由到平台上的具体状态变更。"""

    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    async def dispatch(self, agent_id: int, action_name: str, message: object) -> dict:
        # 这里统一做消息解包和类型校验，平台本身只关注状态更新。
        if action_name == "register_agent":
            if isinstance(message, dict):
                return self.platform.register_agent(
                    agent_id=int(message.get("agent_id", agent_id)),
                    agent_name=str(message.get("agent_name", f"agent_{agent_id}")),
                )
            return self.platform.register_agent(agent_id=agent_id, agent_name=str(message))
        if action_name == "browse_feed":
            return self.platform.browse_feed(agent_id)
        if action_name == "create_post":
            if not isinstance(message, dict):
                raise ValueError("create_post expects a payload dict.")
            payload = dict(message)
            post = self.platform.create_post(
                author_id=agent_id,
                content=str(payload.get("content", "")),
                emotion=str(payload.get("emotion", "calm")),
                intensity=float(payload.get("intensity", 0.2)),
                sentiment=float(payload.get("sentiment", 0.0)),
                emotion_analysis=payload.get("emotion_analysis"),
            )
            return {"success": True, "post": post}
        if action_name == "reply_post":
            if not isinstance(message, dict):
                raise ValueError("reply_post expects a payload dict.")
            payload = dict(message)
            reply = self.platform.reply_post(
                author_id=agent_id,
                post_id=int(payload["post_id"]),
                content=str(payload.get("content", "")),
                emotion=str(payload.get("emotion", "calm")),
                intensity=float(payload.get("intensity", 0.2)),
                sentiment=float(payload.get("sentiment", 0.0)),
                emotion_analysis=payload.get("emotion_analysis"),
            )
            return {"success": True, "reply": reply}
        if action_name == "like_post":
            post_id = int(message["post_id"]) if isinstance(message, dict) else int(message)
            return {"success": True, "like": self.platform.like_post(agent_id=agent_id, post_id=post_id)}
        if action_name == "share_post":
            if not isinstance(message, dict):
                raise ValueError("share_post expects a payload dict.")
            payload = dict(message)
            post = self.platform.share_post(
                agent_id=agent_id,
                post_id=int(payload["post_id"]),
                emotion=str(payload.get("emotion", "calm")),
                intensity=float(payload.get("intensity", 0.2)),
                sentiment=float(payload.get("sentiment", 0.0)),
                content=payload.get("content"),
                emotion_analysis=payload.get("emotion_analysis"),
            )
            return {"success": True, "post": post}
        if action_name == "apply_influence":
            if not isinstance(message, dict):
                raise ValueError("apply_influence expects a payload dict.")
            payload = dict(message)
            event = self.platform.apply_influence(
                source_agent_id=int(payload.get("source_agent_id", agent_id)),
                target_agent_id=int(payload["target_agent_id"]),
                delta=float(payload.get("delta", 0.0)),
                reason=str(payload.get("reason", "")),
            )
            return {"success": True, "event": event}
        if action_name == "do_nothing":
            reason = str(message.get("reason", "")) if isinstance(message, dict) else str(message or "")
            self.platform.record_idle(agent_id=agent_id, reason=reason)
            return {"success": True}
        raise ValueError(f"Unsupported action: {action_name}")
