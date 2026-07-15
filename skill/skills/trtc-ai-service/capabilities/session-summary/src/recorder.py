"""Session turn recorder.

Persistence strategy:
- Each session generates ``{session_id}.json`` under storage_dir, permissions 0600.
- Sensitive fields redacted before writing (same standard as skeleton log_filter).
- File structure:
    {
      "session_id": "...",
      "opened_at": 1717830000.0,
      "closed_at": null,
      "turns": [
        {"role": "user", "ts": 1717830001.0, "text": "..."},
        {"role": "assistant", "ts": 1717830002.0, "text": "..."}
      ],
      "summary": null  # Populated after finalize
    }
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


_DEFAULT_STORAGE_DIR = Path(
    os.getenv(
        "SS_STORAGE_DIR",
        str(Path(__file__).resolve().parent.parent / "data"),
    )
)
_RETENTION_DAYS = int(os.getenv("SS_RETENTION_DAYS", "30"))


# Default redaction mode (aligned with skeleton log_filter)
_REDACT_PATTERNS = [
    re.compile(r"(?i)(secret_id|secret_key|api_key|token|credential|authorization)\s*[:=]\s*([^\s,'\"\\]+)"),
]


def _redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _REDACT_PATTERNS:
        out = pat.sub(lambda m: f"{m.group(1)}=***", out)
    return out


@dataclass
class Turn:
    role: str
    text: str
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"role": self.role, "text": self.text, "ts": self.ts}


@dataclass
class SessionRecord:
    session_id: str
    opened_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    turns: List[Turn] = field(default_factory=list)
    summary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "turns": [t.to_dict() for t in self.turns],
            "summary": self.summary,
        }


class Recorder:
    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._lock = threading.RLock()
        self._dir = Path(storage_dir or _DEFAULT_STORAGE_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, SessionRecord] = {}
        self._cleanup_old_files()

    @property
    def storage_dir(self) -> Path:
        return self._dir

    def open(self, session_id: str) -> SessionRecord:
        with self._lock:
            rec = self._cache.get(session_id)
            if rec is not None:
                return rec
            path = self._path(session_id)
            if path.exists():
                rec = self._load(path)
            else:
                rec = SessionRecord(session_id=session_id)
            self._cache[session_id] = rec
            self._persist(rec)
            return rec

    def add_turn(self, session_id: str, role: str, text: str) -> None:
        if not text or not text.strip():
            return
        if role not in ("user", "assistant", "system", "tool"):
            return
        with self._lock:
            rec = self._cache.get(session_id) or self.open(session_id)
            rec.turns.append(Turn(role=role, text=_redact(text)[:4096]))
            self._persist(rec)

    def get(self, session_id: str) -> Optional[SessionRecord]:
        with self._lock:
            rec = self._cache.get(session_id)
            if rec is not None:
                return rec
            path = self._path(session_id)
            if path.exists():
                rec = self._load(path)
                self._cache[session_id] = rec
                return rec
            return None

    def list_recent(self, offset: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        files = sorted(
            self._dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[offset : offset + limit]
        out: List[Dict[str, Any]] = []
        for p in files:
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return out

    def finalize(self, session_id: str, summary: Dict[str, Any]) -> SessionRecord:
        with self._lock:
            rec = self.get(session_id)
            if rec is None:
                raise ValueError(f"session not found: {session_id}")
            rec.closed_at = time.time()
            rec.summary = summary
            self._persist(rec)
            return rec

    # ------------------------------------------------------------------
    def _path(self, session_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_\-]", "_", session_id)[:64]
        return self._dir / f"{safe}.json"

    def _load(self, path: Path) -> SessionRecord:
        data = json.loads(path.read_text(encoding="utf-8"))
        rec = SessionRecord(
            session_id=data.get("session_id", path.stem),
            opened_at=float(data.get("opened_at", time.time())),
            closed_at=data.get("closed_at"),
            summary=data.get("summary"),
        )
        for t in data.get("turns") or []:
            rec.turns.append(Turn(role=t.get("role", "user"), text=t.get("text", ""), ts=float(t.get("ts", 0))))
        return rec

    def _persist(self, rec: SessionRecord) -> None:
        path = self._path(rec.session_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _cleanup_old_files(self) -> None:
        cutoff = time.time() - _RETENTION_DAYS * 86400
        for p in self._dir.glob("*.json"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                continue


# ---------------------------------------------------------------------------
# Global singleton + manifest.extensions injection functions
# ---------------------------------------------------------------------------
_global_recorder = Recorder()


def get_recorder() -> Recorder:
    return _global_recorder


def open_session(session_id: str) -> None:
    _global_recorder.open(session_id)


def record_user_turn(session_id: str, text: str) -> None:
    _global_recorder.add_turn(session_id, "user", text)


def record_assistant_turn(session_id: str, text: str) -> None:
    _global_recorder.add_turn(session_id, "assistant", text)
