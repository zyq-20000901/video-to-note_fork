"""批次只持久化输入与任务映射，不保存模型配置、凭据或笔记正文。"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID


class BatchStore:
    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "_batches"

    def path(self, batch_id: str) -> Path:
        if str(UUID(batch_id)) != batch_id:
            raise ValueError("非法批次 ID")
        return self.root / f"{batch_id}.json"

    def load(self, batch_id: str) -> dict[str, Any]:
        payload = json.loads(self.path(batch_id).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("批次记录无效")
        return payload

    def save(self, batch: dict[str, Any]) -> None:
        path = self.path(batch["batch_id"])
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
