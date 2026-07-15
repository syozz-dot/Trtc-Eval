# Q3 —— UI Form (3 choose 1)

> Path B Question 3. AI uses `ask_followup_question` in **single-select** mode.
>
> Answer written to internal variable `ui_form`, later used to determine:
> 1. Floating widget / fullscreen page / headless three deployment modes
> 2. Whether to overlay UI onto `capabilities/conversation-core/web-demo`
> 3. Whether to generate integration guides (references to `integration-templates/*.md`)

---

## What the AI should say

> Question 3: Where do you want the AI customer service to "appear"?

`options`:

```text
① Floating widget (embedded in the bottom-right corner of your existing page, recommended)
② Fullscreen chat page (standalone page / sub-route, full-page conversation)
③ Backend API only (you build your own frontend / integrate into existing IM, no demo UI needed)
```

`multiSelect: false`

---

## Option → Behavior Mapping

| User Option | Internal Enum (`ui_form`) | recipe.ui_overlay | Notes |
|---|---|---|---|
| ① Floating | `floating` | source=`scenarios/customer-service/ui/widget-floating`, target=`web-demo/` | Same as Path A |
| ② Fullscreen | `fullscreen` | source=`scenarios/customer-service/ui/widget-floating` but `target=web-demo/`; after launch, guide user to open `/?layout=full` (or self-extend a dedicated template) | No dedicated fullscreen template in this release; reuses floating template forced to fullscreen via CSS class hook |
| ③ Backend only | `headless` | `ui_overlay: null` | Only installs capability packages; artifacts only expose `/api/v1/*` |

> **Note**: This release does not generate a dedicated fullscreen conversation template (`fullscreen` reuses floating CSS forced to fullscreen);
> for finer control, a `widget-fullscreen/` subdirectory under `scenarios/customer-service/ui/` can be added later.

---

## Validation / Fallback

- Cross-validation with Q2 (`io_modality`): see Q2 "Validation / Fallback"
- Choosing ③ skips cp overlay; but AI must still remind user about external integration docs per §8 (`auto_adapters/integration_templates/generic-frontend.md`)

---

## Answer write-back

```yaml
# Render to <workspace>/recipe.yaml
ui:
  form: floating                 # floating | fullscreen | headless
  overlay_required: true         # false in headless mode
```
