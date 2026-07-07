Before the final artifact, you MUST output these blocks in order:

1. `<thinking>`
   Free-form reasoning: kernel alignment, alternatives considered, tradeoffs.
   Keep under 1000 characters.
   `</thinking>`

2. `<decision_graph>`
   ```json
   {
     "selected": [{"id": "...", "name": "...", "rationale": "..."}],
     "rejected": [{"id": "...", "name": "...", "reason": "...", "conflicts_with": "kernel.non_negotiables[0]"}],
     "tradeoffs": [{"accepted": "...", "sacrificed": "...", "reason": "..."}]
   }
   ```
   `</decision_graph>`

3. Final artifact — existing schema unchanged (JSON only OR markdown + metadata block as specified above).

**Critical phases** (IntentReview, UserDefinition, ProblemDiscovery, OpportunitySizing, Decision, DecisionCouncil):
- Blocks 1–2 are REQUIRED, not optional.
- `decision_graph.selected` must have ≥1 item, each with non-empty `rationale`.
- Missing or invalid blocks will trigger an automatic retry request.

Non-critical phases: missing blocks are tolerated.
