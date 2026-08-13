# Creation Brief Playbook

`creation_brief` turns selected source material into a writing contract. It does not write the script.

## Responsibilities

- Identify the source's retention mechanism, viewer position, authority posture, body logic, and must-keep elements.
- Decide whether the source, body plan, and current business goal naturally earn a CTA. No CTA is acceptable.
- Record risk observations and set `risk_policy: defer_to_risk_review` for methodology v3. Legacy v2 tasks may retain `defer_to_risk_cleanup`.
- Classify the work as `adaptation`, `half_original`, or `original`.
- Select `none`, `guardrail_only`, or `one_support_point` for professional support. Standard adaptation may cite at most one support card.

## Output Contract

- `retention_mechanism`
- `must_keep_elements`
- `rewrite_strategy`
- `body_logic_plan`
- `cta_fit_decision`
- `risk_policy`
- `adaptation_mode`
- `professional_support_mode`
- `support_card_ids`
- `support_function`
- `target_gap`

## Hard Boundaries

- Do not provide replacement sentences for risky words.
- Do not propose a safer rewritten opening.
- Do not write `draft_text`, `final_copy`, publish titles, video description, or pinned comment.
