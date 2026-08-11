# Global Rewrite Playbook

This file defines the cross-IP methodology for `rewrite_draft`. IP positioning, audience, vocabulary, topic boundaries, and business posture belong in the IP playbook.

## Stage Responsibility

`rewrite_draft` produces the first complete oral adaptation.

It must:

- preserve the source's proven reason for attention;
- preserve the source's primary content task and reusable value;
- adapt speaker position, evidence, and expression to the target IP;
- form one coherent oral argument within the task's length guardrail;
- defer hook polishing to `hook_enhancement`;
- defer all platform-risk replacement to `risk_cleanup`.

It must not become a summary, a new topic inspired by the source, a safety rewrite, or publish packaging.

## Priority

When inputs conflict, use this order:

1. confirmed task goal and target audience;
2. target IP persona and hard boundaries;
3. source content task, retention mechanism, speaker position, and must-keep value;
4. material understanding and stage feedback;
5. length, CTA, and surface polish.

Do not silently erase the source's strongest viral element. If it is incompatible with the task or IP, mark the material for reselection instead of disguising the loss as adaptation.

## Content Task And Mechanism

Before writing, separate three things:

- **Topic:** what the source talks about.
- **Content task:** what the source does for the viewer, such as warning, diagnosing, teaching, validating, provoking, building trust, or stimulating desire.
- **Mechanism:** why the viewer continues, such as conflict, identity, authority, loss, curiosity, recognition, scarcity, or proof.

A successful rewrite preserves the content task and mechanism, not merely the topic or information points. The wording and structure may change only as much as IP fit and oral clarity require.

## Source Discomfort And Objection

Viewer discomfort, disagreement, or resistance can be part of a proven retention mechanism. Do not automatically soften a hook because it may offend, challenge, or unsettle the audience.

Judge instead:

- whether the discomfort attracts the intended viewer;
- whether it creates a clear reason to continue;
- whether the body can address the core objection honestly;
- whether the claim remains compatible with platform and IP boundaries.

When a hook deliberately creates an objection, the body must process that objection. It may clarify the claim, explain the underlying mechanism, or give a way forward, but it must not quietly replace the original content task.

A strong attitude can itself be the source's reusable value and retention mechanism. Separate the stance from any risky execution detail: preserve the stance in `rewrite_draft`, then use explanation, conditions, or scene boundaries to make its intended meaning clear. Do not replace an opinionated claim with a neutral procedure merely because the procedure is easier to defend.

## Speaker Compatibility

Protect wording only after identifying who can credibly say it.

- When source and target IP share a credible speaker position, keep the opening literally or near-literally in `rewrite_draft`.
- When the source depends on an identity or first-person experience the target IP cannot claim, use `perspective_translation`.
- Perspective translation must preserve the original psychological entry point, conflict, viewer position, and information-release job.
- First-person evidence may remain as a quote, case, or dialogue when the target IP can credibly introduce and interpret it.

Record why perspective changed. Unexplained replacement is presumed to have lost source value.

## Adaptation Boundary

Use minimum necessary mutation:

- correct ASR errors and awkward oral phrasing;
- remove repetition that does not contribute to retention;
- translate incompatible identity, values, or context;
- add only what is needed to support the source claim, bridge logic, establish target-IP credibility, or fulfil a promise already made.

Do not add a generic lesson, forced uplift, unrelated theory, or standardized CTA merely to make the script feel complete.

If the source is too thin, off-audience, repetitive within the current batch, or only salvageable by replacing its core mechanism, return to material selection.

`rewrite_draft` accepts only a confirmed `formal_rewrite_base`. A `topic_clue` must trigger reselection even when its metrics or topic are attractive.

Do not confuse reorganization with reconstruction:

- reorganization compresses, reorders, bridges, or translates value already earned by the source;
- reconstruction supplies a new main claim, new evidence chain, or new conclusion because the source cannot support the target length.

When the current IP playbook is still immature or the task explicitly requires low originality, reconstruction is out of scope. Preserve the recorded `salvage_boundary`; if the script cannot be completed inside it, return the material instead of filling the gap with generic IP theory or a preferred script structure.

## Internal Logic

The script needs one main claim and a continuous reasoning path. It does not need a universal sequence of hook, case, list, advice, and CTA.

Each component is optional unless the source or task requires it. What matters is that:

- the opening creates a contract the body actually fulfils;
- evidence supports the claim it is attached to;
- clarification answers a real objection created by the script;
- advice follows from the explanation rather than appearing as a generic add-on;
- the ending completes the current content task instead of switching to another one.

Record this as `internal_logic_alignment`.

## Oral Integrity

Expression integrity comes before length control.

- Keep subjects, actions, and objects clear.
- Keep perspective and pronouns stable.
- Prefer concrete actions and recognizable situations over abstract noun chains.
- Preserve useful emotional pressure without making sentences cramped.
- Read adjacent sentences aloud; wording that is logically guessable but hard to say fails.

Length is a guardrail set by the task or IP, not a target to hit by force. Rich material may use the upper part of the range. Thin material should be reselected rather than expanded with outside claims.

## CTA And Conversion

CTA is optional.

Use interaction only when it naturally continues the content value or the IP's current business goal. Choose the minimum necessary action and information request. Do not stack actions, expose unnecessary private information, or let conversion replace retention.

Publish-platform preferences belong in the IP or publish-format layer, not in the core rewrite structure.

## Stage Boundaries

- `rewrite_draft`: protect source task, mechanism, opening, value, and logic. Record risk; do not solve it.
- `hook_enhancement`: make the smallest useful opening adjustment. Do not change the content task or body logic.
- `risk_cleanup`: replace only the unsafe span. Do not use safety as permission for a second rewrite.
- `publish_format`: package the cleaned body without editing it.

## Quality Gates

Hard gates:

- source content task and retention mechanism are preserved;
- source opening is exact or near-literal unless speaker incompatibility is recorded;
- the script fits the target audience and confirmed IP;
- the body fulfils the opening's promise and handles any deliberate core objection;
- added content is earned by the source claim or task goal;
- risk replacement is deferred;
- viewer-facing copy contains no internal workflow language;
- the oral script stays inside the applicable length guardrail without sacrificing clarity.

Soft signals:

- the intended viewer recognizes the relevance early;
- authority is demonstrated through judgment or evidence, not merely claimed;
- concrete evidence carries abstract explanation when useful;
- emotional force remains comparable to the source;
- the ending feels like the natural completion of the same argument.

## Output Contract

Return:

- `draft_text`;
- `char_count`;
- `hook_preservation`;
- `opening_preservation_mode`;
- `kept_source_elements`;
- `ip_adaptation_notes`;
- `conversion_goal_alignment`;
- `deferred_risk_terms`;
- quality checks including `internal_logic_alignment`.
