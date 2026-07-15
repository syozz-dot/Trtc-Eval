# Q1 —— Business Description (free text)

> Path B Question 1. AI uses `ask_followup_question` as a standalone question, **without options**, letting the user type freely.
>
> AI saves the user's answer to the internal variable `business_desc`, for later use in:
> 1. Rendering `{{business_desc}}` in `scenarios/customer-service/system-prompt.template.md`
> 2. Writing to `<workspace>/recipe.yaml` at `agent_runtime.system_prompt.variables.business_desc`
>
> AI must **not** guess the industry; leave unsaid fields blank and backfill after Q4.

---

## What the AI should say

> Question 1 (of 4): What business is your customer service bot for?
> Just describe the **business scope** and **typical questions** in a sentence or two. For example:
>
> - "We are an e-commerce store selling smart home appliances — air fryers, robot vacuums, humidifiers. Users usually ask about warranty, returns, and shipping."
> - "I run customer support for a SaaS HR platform. Common issues are login failures, org structure sync, and plan upgrades."
> - "A restaurant delivery service. Users mainly ask about order status, refunds, menu stock, and delivery fees."
>
> The more specific your business, the better the final system prompt will match your real scenario.

---

## Validation after receiving the answer

- Length ≥ 8 and ≤ 600 characters. If too short, follow up: "That's quite brief — could you add a bit more about typical issues or industry keywords?"
- Must contain at least one noun phrase (industry name, product name, user type); pure interjections or casual chat → **re-ask**
- Do not ask the user to provide brand name / company name (if needed, the template uses placeholder `{{business_name | default('we')}}`)

---

## Answer write-back

```yaml
# Render to <workspace>/recipe.yaml
agent_runtime:
  system_prompt:
    variables:
      business_desc: |
        <user's original text>
```
