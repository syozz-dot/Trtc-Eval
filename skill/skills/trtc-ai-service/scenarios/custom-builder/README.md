# scenarios/custom-builder —— Path B Custom Flow

> Companion doc: repo root `SKILL.md` (Path B SOP §6).

This directory contains all artifacts for **Path B** ("Custom"). It has **no executable scripts** —
the 4-round Q&A is entirely facilitated by the Coding Agent using `ask_followup_question`.
This directory provides only two types of static materials:

```
scenarios/custom-builder/
├── README.md                              ← This file
├── prompts/                               ← Question templates for AI (does not modify user's project)
│   ├── q1-business-scenario.md            ←  Q1: Business description (free text)
│   ├── q2-io-modality.md                  ←  Q2: I/O modality (4 choose 1)
│   ├── q3-ui-form.md                      ←  Q3: UI form (3 choose 1)
│   └── q4-capabilities.md                 ←  Q4: Capability selection (multi-select; defaults to none)
└── output-templates/
    └── recipe.yaml.j2                     ← AI rendering artifact template (output to <workspace>/recipe.yaml)
```

---

## AI Execution Flow (aligned with SKILL.md §6)

| Step | Tool | Source |
|---|---|---|
| 6.1 | `ask_followup_question` (free text) | `prompts/q1-business-scenario.md` |
| 6.2 | `ask_followup_question` (single-select 4 items) | `prompts/q2-io-modality.md` |
| 6.3 | `ask_followup_question` (single-select 3 items) | `prompts/q3-ui-form.md` |
| 6.4 | `ask_followup_question` (multi-select 4 items) | `prompts/q4-capabilities.md` |
| 6.5 | `write_to_file` render `recipe.yaml` | `output-templates/recipe.yaml.j2` |
| 6.6 | `execute_command("python3 scripts/add-capability.py <Q4 selections> --apply --json")` | Q4 selections; skip if none |
| 6.7 | Remaining steps same as Path A (§7 Keys → §8 Contract → §9 Launch) | SKILL.md |

---

## Constraints / Red Lines

- **No builder.py**: The 4-round Q&A is **entirely** facilitated by AI; do not turn this into a local script (the user experience would drop out of the chat window)
- **No manifest.yaml generation**: Each capability already has its own `manifest.yaml`; Path B does not need to regenerate
- **prompts/q*.md are static materials**: AI **reads** them only; no content modification / re-formatting
- **recipe.yaml.j2 uses Jinja2 syntax**: But the AI does not need to actually invoke a Jinja2 interpreter; it can do string replacement mentally and then `write_to_file` the final yaml. The template is just a **structural contract** for the AI

---

## After Collecting All Answer Variables, AI Constructs This Context

```python
context = {
    # Q1
    "business_desc": "<user's original text>",
    "business_name": "<optional; defaults to 'we' if user didn't specify>",

    # Q2 option → internal enum
    "io_modality": "text_with_tts",     # text_only | text_with_tts | omni | voice_only

    # Q3 option → internal enum
    "ui_form": "floating",              # floating | fullscreen | headless

    # Q4 user-selected capability array
    "extra_capabilities": [             # any subset; empty array installs skeleton only
        "knowledge-base",
        "human-handoff",
        # "tool-calling",
        # "session-summary",
    ],

    # Meta info (AI fills in)
    "render_time": "<ISO 8601>",
    "rendered_by": "Coding Agent",
}
```

Feed this to `output-templates/recipe.yaml.j2` to get the customized `<workspace>/recipe.yaml`.

---

## Differences from Path A (reference table)

| Dimension | Path A | Path B |
|---|---|---|
| Entry | "Build me an AI customer service agent with TRTC" | Same, SKILL.md §4 choose B |
| Installed capabilities | Default `knowledge-base + human-handoff` | Default none; user selects via Q4 |
| Business prompt | Just ask "describe your business" before launch | Q1 is required (more explicit) |
| UI | Floating widget + ticket dashboard (default) | Controlled by Q3: floating / fullscreen / headless |
| recipe.yaml location | `scenarios/customer-service/recipe.yaml` (static in repo) | `<workspace>/recipe.yaml` (generated each time; can be manually edited and re-installed) |
