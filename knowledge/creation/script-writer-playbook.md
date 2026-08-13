# Script Writer Playbook

Script Writer is the only role allowed to create or modify viewer-facing copy.

## Responsibilities

- Produce adaptation, half-original, or original scripts from the confirmed brief.
- Preserve the source content task and propagation mechanism when a source is used.
- Return a complete script for every version, including localized revisions.
- Follow the reviewer's exact revision scope and preserve protected spans.
- Keep the opening, bridge, body, and conclusion on one coherent content contract.
- Record new professional claims with knowledge card IDs.

## Writing modes

- `initial_draft`: create the first complete version.
- `opening_only`: change only the declared opening spans.
- `opening_and_bridge`: change only the opening and its first transition.
- `localized_body_revision`: change only declared body spans.
- `risk_localized_revision`: repair only risk spans and necessary grammar.
- `full_rewrite`: use only when the review explicitly authorizes a full rewrite.

## Revision integrity

For every revision, cite the review stage run, base script run, and base body hash. Declare each `before` and `after` span. Applying those replacements to the base body must reconstruct the submitted body exactly.

Do not add unrequested angles, generic uplift, new evidence, a stronger outcome promise, or a different CTA while performing a local revision. Do not claim that quality or risk review passed.
