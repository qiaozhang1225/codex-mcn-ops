# Global Risk Lexicon

This file separates terms that should be replaced immediately from terms that should be observed through feedback. Risk cleanup is deliberately late in the creation workflow: `rewrite_draft` and `hook_enhancement` may record risk, but must not rewrite for risk.

## Ultra High Risk, Replace In `risk_cleanup`

- Strong result promises: 保证发财, 保证有效, 百分百有效, 立马见效, 一定成功, 必定成功
- Direct supernatural or wealth guarantees: 必能转运, 注定发财, 必定发财, 招来大财
- Extreme fate manipulation promises: 逆天改命, 必定改命
- Medical, legal, financial, or religious certainty claims that cannot be supported by the script.

These terms are replaced locally in `risk_cleanup`. The replacement should preserve the hook structure, authority posture, and emotional force.

Do not soften risk into explanatory cooling. Replace unsafe wording with publishable wording that carries similar force, instead of adding a disclaimer-style explanation.

## Source-carried Risk, Record And Defer

If a term appears in the source material, it is not automatically ultra high risk. Source-carried words usually explain why the source worked, especially in metaphysics, wealth, fate, and self-diagnosis content.

- Examples: 改命, 改运, 转运, 自带财运, 财运, 财气, 命运, 贵人, 磁场, 能量, 福报
- In `rewrite_draft`: keep the word if it belongs to the source hook or retention mechanism.
- In `hook_enhancement`: do not replace the hook with a safety-denial sentence.
- In `risk_cleanup`: replace only if the exact phrase becomes an ultra-high-risk promise. Otherwise record it as source-carried or edge risk and observe feedback.

## Edge Terms, Observe Instead Of Deleting By Default

- 财运, 财气, 好运, 招财, 旺财
- 福报, 因果, 气场, 开悟, 命运, 贵人
- 修行, 能量, 磁场

Edge terms can be useful in national-culture or metaphysics-adjacent accounts, but they should be grounded in behavior, perception, self-cultivation, or cultural interpretation.

## Cleanup Policy

- Ultra-high-risk terms are replaced before delivery and recorded in `risk_term_observations`.
- Source-carried risk terms are recorded but are not mechanically replaced.
- Edge terms stay in the copy when context is reasonable and are recorded for later feedback review. Do not delete useful propagation factors just because they are metaphysics-adjacent.
- Risk cleanup should preserve the working hook, authority frame, and concrete pain. If a risky phrase sits inside the opening, replace only the offending phrase and keep the opening mechanism.
- Feedback only creates learning proposals. Markdown is changed only after an explicit apply step.
