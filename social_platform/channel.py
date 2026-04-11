"""Agent 与平台共享的异步消息通道。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any


class AsyncSafeDict:
    """带锁的异步字典，用来暂存响应结果。"""

    def __init__(self) -> None:
        self._items: dict[str, Any] = {}  # 以 message_id 为键暂存响应
        self._lock = asyncio.Lock()  # 避免并发读写冲突

    async def put(self, key: str, value: Any) -> None:
        async with self._lock:
            self._items[key] = value

    async def pop(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._items.pop(key, default)

    async def keys(self) -> list[str]:
        async with self._lock:
            return list(self._items.keys())


class Channel:
    """简化版请求/响应通道。"""

    def __init__(self) -> None:
        self.receive_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()  # 平台消费的请求队列
        self.send_dict = AsyncSafeDict()  # 发送方按 message_id 取回结果

    async def receive_from(self) -> tuple[str, Any]:
        return await self.receive_queue.get()

    async def send_to(self, message: tuple[str, Any, Any]) -> None:
        message_id = str(message[0])
        await self.send_dict.put(message_id, message)

    async def write_to_receive_queue(self, action_info: Any) -> str:
        message_id = str(uuid.uuid4())  # 每个请求单独分配唯一 ID
        await self.receive_queue.put((message_id, action_info))
        return message_id

    async def read_from_send_queue(self, message_id: str) -> tuple[str, Any, Any]:
        while True:
            if message_id in await self.send_dict.keys():
                message = await self.send_dict.pop(message_id, None)
                if message is not None:
                    return message
            await asyncio.sleep(0.05)
