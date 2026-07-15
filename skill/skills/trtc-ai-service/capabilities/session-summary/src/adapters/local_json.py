"""local_json write-back sink — append to local JSONL for offline verification."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

from .base import SummarySink

_LOCK = threading.RLock()


class LocalJsonSink(SummarySink):
    name = "local_json"

    def __init__(self) -> None:
        base = os.getenv(
            "SS_STORAGE_DIR",
            str(Path(__file__).resolve().parents[2] / "data"),
        )
        self._file = Path(base) / "_writeback.jsonl"
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def write(self, summary_record: Dict[str, Any]) -> Dict[str, Any]:
        sid = str(summary_record.get("session_id", ""))
        record_id = "CRM-LOCAL-" + hashlib.md5(sid.encode("utf-8")).hexdigest()[:10].upper()
        line = json.dumps(
            {"record_id": record_id, "written_at": int(time.time()), "record": summary_record},
            ensure_ascii=False,
        )
        with _LOCK:
            with self._file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            try:
                os.chmod(self._file, 0o600)
            except OSError:
                pass
        return {"record_id": record_id, "accepted": True, "sink": self.name}
