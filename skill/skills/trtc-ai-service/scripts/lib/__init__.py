"""Phase 2 shared infrastructure (no business logic).

This package exposes reusable modules to CLI tools like add-capability / detect-stack:

- manifest_resolver  Capability manifest loading / dependency graph / topological sort / circular dependency detection
- stack_detector     Tech stack detection (package.json / pom.xml / requirements.txt, etc.)
- degrader           Three-tier fallback decision engine (L1 auto / L2 semi-auto / L3 manual)
- injector           Code injection based on manifest.injection_points position descriptions
- arbitrator         α/β dual-track tool-call arbitration (for internal use by the tool-calling capability)

Design principle: this package has no business logic dependencies; protocol parsing and policy decisions only.
"""

__all__ = [
    "manifest_resolver",
    "stack_detector",
    "degrader",
    "injector",
    "arbitrator",
]
