# Material Selection Playbook

`material_selection` decides whether a source is worth adapting for the target IP. It does not write viewer-facing copy.

## Decision Principles

Judge:

- audience and target-IP fit;
- topic freshness within the current batch;
- whether the source has a clear and recoverable content task and retention mechanism;
- whether speaker position and core value can be translated without replacing what made the source work;
- whether the source contains enough usable substance to be reduced and reorganized into the requested output.

Source thickness is a compression-margin judgment, not a checklist of required components. A source is too thin when meeting the target length would require inventing claims, attaching an unrelated conclusion, or expanding beyond the source's earned value.

Reject or reclassify a source when its core mechanism conflicts with the target IP, when its value cannot survive perspective translation, or when downstream rewriting would need to create a different content task.

Separate **formal rewrite bases** from **topic clues**:

- viral metrics, audience fit, and topic coverage make a source worth studying, but do not prove adaptation viability;
- a formal rewrite base must already contain enough argument, evidence, or scene value to reach the target through compression and translation;
- a topic clue may inspire later search, but must not enter `rewrite_draft` as the sole source;
- “requires substantial reconstruction” is a rejection or reclassification signal, not permission to invent the missing article.

Selection must preserve known weaknesses instead of ignoring them after acceptance. Record why the source was considered, what would be lost or invented during adaptation, and the maximum safe salvage boundary. If that boundary cannot produce the task goal, reselect.

## Output Contract

- `source_text`
- `source_opening_text`
- `source_hook_mechanism`
- `source_content_task`
- `speaker_position`
- `topic_fit`
- `duplicate_signal`
- `risk_inventory`
- `thickness_judgment`
- `material_class`: `formal_rewrite_base` or `topic_clue`
- `selection_rationale`
- `selection_weaknesses`
- `salvage_boundary`

## Hard Boundaries

- Do not produce draft or publish copy.
- Do not rewrite for safety or polish.
- Do not treat a selection failure as a challenge to rewrite harder.
