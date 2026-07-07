# Token Savings Profile

Applied optimizations (see `PM_TOKEN_SAVINGS` notes in `.env.example`).

## Rejected (kept by design)

| # | Item | Why kept |
|---|---|---|
| 4 | Investor QA off / conditional | Market viability second opinion on Opus is intentional before Council |
| 7 | `PM_COGNITIVE_MEMORY=0` | Decision graph + thinking timeline for Decisions UI / downstream injection |

## Upstream L1–3 vs Intent Review (#2 — read before changing)

**Intent Review (Layer 0.5)** and **Upstream (Layers 1–3)** overlap in *topic* but differ in *input and output*:

| | Intent Review | Upstream L1–3 |
|---|---|---|
| Input | `founder_kernel.json` only | `signals/` + kernel + prior JSON artifacts |
| Output | Gate verdict + critique JSON | `user_model.json`, `problem_statement.json`, `opportunity_model.json` |
| Model | Strong (Opus class) | Cheap (Mini class) |
| Purpose | **Stop bad builds** before spend | **Structured discovery** artifacts for workspace / trace |

**When upstream is worth keeping (`PM_UPSTREAM_MODE=on`, default):**

- You maintain `workspace/signals/` (interviews, notes, metrics)
- You want durable JSON under `current/user/` and `current/opportunity/`
- Idea Loop should consume structured discovery, not only `raw_ideas.md`

**When to set `PM_UPSTREAM_MODE=off`:**

- Kernel + `raw_ideas.md` are enough; no signals folder
- Intent gate already caught major user/problem issues; you accept skipping artifact generation to save ~3 Mini calls (~6k tokens)
- You will add intent→upstream seeding later (not implemented — would reuse intent analyses as upstream hints without 3 full phases)

**Default:** unchanged behavior — upstream runs when `OPENROUTER_MODEL_USER_DEF` is set and `PM_UPSTREAM_MODE` is not `off`.

## Applied optimizations

1. **Idea Loop 3-call** — `draft → critique → final` (removed 2nd critique round; Product/Strategic QA cover re-validation)
2. **Idea gen temperature 1.0** — less verbose drafts (was 2.0)
3. **Consistency digest** — guardrail reads compact digest, not full documents
4. **Intent KO batch only** — Opus outputs English; `ko_summary` removed from intent prompt
5. **Patch direct LLM** — single structured patch call instead of CrewAI multi-turn
6. **Synthesis retry** — error-only retry message (no full assistant replay)
