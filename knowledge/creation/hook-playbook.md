# Hook Playbook

`hook_enhancement` protects and, only when necessary, sharpens the source's proven reason to stop.

## Core Decision

Judge the hook by its job, not by a preferred hook type or sentence pattern:

- who it attracts;
- what emotion or conflict makes the viewer continue;
- what promise it creates for the body;
- what speaker position makes it credible.

If the existing hook already performs that job, keep it or make only a surface-level oral adjustment.

## Preservation And Translation

- Do not replace a strong hook for novelty, politeness, duplication anxiety, or early risk cleanup.
- Treat the source's first complete sentence as protected by default. A shorter paraphrase that keeps only the conclusion but drops the original subject, conflict, specificity, or rhythm is a replacement, not a minimal edit.
- Compare the actual enhanced body and selected hook with the recorded source opening. A submitted `passed` flag never overrides a weaker or missing opening.
- When the target IP can credibly use the source speaker position, prefer literal or near-literal preservation.
- When the speaker position is incompatible, use `perspective_translation` and record the reason.
- Translation must pass strength parity: conflict, specificity, intended-audience entry, emotional force, and reason to continue remain comparable.
- If those qualities cannot survive translation, return to material selection instead of accepting a weaker opening.

## Discomfort And Objection

A hook may work because the intended viewer disagrees with it. That resistance is not automatically a flaw.

Preserve deliberate provocation when it is relevant and supportable. The body must then handle the core objection without retracting the content task or turning the script into a different argument.

When the stopping power comes from a clear stance, judge preservation by attitude parity as well as semantic similarity. Replacing “what I firmly believe” with a warning, information gap, or neutral consequence changes the hook mechanism even if the topic stays the same.

## Five-Affliction Attention Lens

Use `贪、瞋、痴、慢、疑` as a creator-side attention-analysis lens, not as a claim that content should cultivate Buddhist afflictions and not as the only Buddhist classification of the poisons or root afflictions.

- `贪` — a desired gain or avoided loss: money, opportunity, health, relationship, status, relief, or a promised useful answer;
- `瞋` — an objection, violation, anger, or urge to refute: “I disagree”, “that is unfair”, or “I want to see how this can be defended”;
- `痴` — a mistaken model or seductive shortcut waiting to be exposed: “I always thought X, but the mechanism is Y”. Never satisfy this driver by fabricating mystique or false certainty;
- `慢` — identity and status comparison: ordinary person versus expert, loser versus winner, informed versus uninformed, or a challenge to the viewer's self-image;
- `疑` — a bounded information gap: credible authority plus an unresolved claim, counterintuitive result, hidden cause, or unanswered question.

For short-form hooks, map the source opening before rewriting. A strong candidate normally activates at least three distinct drivers organically. Counting alone is not enough: every activated driver must point to the same body contract, and the body must resolve the desire, objection, comparison, misconception, or question that the opening creates.

Do not stack unrelated money words, threats, superiority claims, mystery language, or questions merely to reach three. Do not invent credentials, cases, certainty, or guaranteed outcomes. If the source already activates three or more drivers with a compatible speaker position, preserve the opening literally or near-literally. Hook enhancement may sharpen a missing driver only when it already exists in the source mechanism and the body can fulfil it.

Record the result as `driver_map`, `active_driver_count`, and `body_contract`. Compare the enhanced opening with the source: losing a strong driver is mechanism loss even when the topic and conclusion remain similar.

## Stage Boundary

- Hook enhancement may correct ASR, rhythm, reference, speaker compatibility, or small duplication.
- It must not change body logic, add a new explanatory angle, or perform risk cleanup.
- Risk inside the hook is recorded for `risk_cleanup`; only the unsafe span may later change.
- Provocative universal-sounding life advice is not automatically unsafe. Preserve it when it is an opinionated stance rather than a regulated, diagnostic, financial, medical, legal, or guaranteed-outcome claim; let the body process the objection without retracting the hook.

Record `hook_diff_type` as `unchanged`, `punctuation_asr`, `minimal_dedup`, `perspective_translation`, or `replaced`. `replaced` requires a documented incompatibility and should otherwise fail.
