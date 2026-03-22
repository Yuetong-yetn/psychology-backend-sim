"""平台状态存储与导出。

当前实现为轻量 JSON 导出层，便于后续替换成数据库。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SimulationStorage:
    """保存仿真快照和中间结果。"""

    output_dir: str

    def ensure_dir(self) -> Path:
        """确保输出目录存在。"""
        path = Path(self.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, filename: str, payload: Any) -> str:
        """把任意可序列化对象保存为 JSON 文件。"""
        path = self.ensure_dir() / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
