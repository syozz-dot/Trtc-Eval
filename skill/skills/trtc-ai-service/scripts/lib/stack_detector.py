"""Tech stack detection.

Reads signal files from the target project root and outputs standardized tech_stack labels:
    react / vue / angular / next /
    express / koa / fastify /
    spring-boot / quarkus /
    flask / fastapi / django

On detection failure, primary is None; degrader decides fallback to L2 or L3.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


_PRIORITY = [
    "next",
    "react",
    "vue",
    "angular",
    "express",
    "koa",
    "fastify",
    "spring-boot",
    "quarkus",
    "fastapi",
    "flask",
    "django",
]


@dataclass
class DetectResult:
    primary: Optional[str]
    candidates: List[str]
    signals: List[str]

    def to_dict(self) -> dict:
        return {
            "primary": self.primary,
            "candidates": self.candidates,
            "signals": self.signals,
        }


def _safe_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _detect_node(project: Path, signals: List[str]) -> List[str]:
    pkg = project / "package.json"
    if not pkg.exists():
        return []
    try:
        data = json.loads(_safe_text(pkg))
    except json.JSONDecodeError:
        return []
    deps = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(data.get(k) or {})
    out: List[str] = []
    mapping = {
        "next": "next",
        "react": "react",
        "vue": "vue",
        "@angular/core": "angular",
        "express": "express",
        "koa": "koa",
        "fastify": "fastify",
    }
    for dep_key, label in mapping.items():
        if dep_key in deps:
            out.append(label)
            signals.append(f"package.json:{dep_key}")
    return out


def _detect_java(project: Path, signals: List[str]) -> List[str]:
    out: List[str] = []
    pom = project / "pom.xml"
    gradle = project / "build.gradle"
    gradle_kts = project / "build.gradle.kts"
    text = ""
    for p in (pom, gradle, gradle_kts):
        if p.exists():
            text += _safe_text(p)
            signals.append(p.name)
    if "spring-boot-starter" in text or "org.springframework.boot" in text:
        out.append("spring-boot")
    if "quarkus-core" in text or "io.quarkus" in text:
        out.append("quarkus")
    return out


def _detect_python(project: Path, signals: List[str]) -> List[str]:
    out: List[str] = []
    chunks: List[str] = []
    for fname in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.py"):
        p = project / fname
        if p.exists():
            chunks.append(_safe_text(p).lower())
            signals.append(fname)
    blob = "\n".join(chunks)
    if not blob:
        return out
    # Order: fastapi has higher priority than flask (some projects declare both)
    if "fastapi" in blob:
        out.append("fastapi")
    if "django" in blob:
        out.append("django")
    if "flask" in blob:
        out.append("flask")
    return out


def _ordered_unique(items: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def detect(project_root: Path) -> DetectResult:
    """Run tech stack detection on the target project."""
    project_root = Path(project_root).resolve()
    signals: List[str] = []
    cands: List[str] = []
    cands += _detect_node(project_root, signals)
    cands += _detect_java(project_root, signals)
    cands += _detect_python(project_root, signals)
    cands = _ordered_unique(cands)

    # Select primary by _PRIORITY
    primary: Optional[str] = None
    for label in _PRIORITY:
        if label in cands:
            primary = label
            break
    return DetectResult(primary=primary, candidates=cands, signals=signals)


def match_adapter(tech_stack: str, auto_adapters: list) -> Optional[str]:
    """Find the matching adapter name in manifest.integration.auto_adapters."""
    if not tech_stack or not auto_adapters:
        return None
    for entry in auto_adapters:
        if not isinstance(entry, dict):
            continue
        if tech_stack in (entry.get("tech_stack") or []):
            return entry.get("adapter")
    return None
