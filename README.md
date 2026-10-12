# Paylane Support Agent

A proof-of-concept AI support agent for Paylane refunds, cards, and transfer queries.
The model manages the conversation, deterministic code owns verification, refund eligibility, and high-risk escalation.
Given the time budget of 4-6h, I focused on what matters the most - agent execution respects policy, deterministic checks and a tool dispatcher for agent reliability, correct behaviour and no user promises.

Evaluation notes:
- `llama3:8b` (served locally) missed required tool calls frequently and was not suitable for this workflow.
- `gpt-4o-mini` sometimes narrated actions instead of making the required tool call.
- `gpt-4o` completed all 17 cases in three consecutive evaluation runs. It is the submitted baseline.
- GPT-5.6 Terra was considered as a cost/performance alternative, but is not used as the submission baseline.

I also considered adding a separate TypeSafe classifier such as Jev, both to
grade evaluations and to detect high-risk requests at runtime. For this brief,
the evaluation is deliberately well-scoped: each expected tool call, outcome,
and privacy property can be checked deterministically from the trace. Those
checks are free, repeatable, and more reliable than asking another model to
grade the agent.

At runtime, a second model would add a probabilistic dependency, extra latency,
cost, credentials, service-failure modes, and threshold tuning. It could be a
useful conservative signal in production, but it should never be the authority
that permits a refund. The submitted design instead keeps the model responsible
for conversation and tool selection, while deterministic code makes the refund
and escalation decisions required by the brief.


## How to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Deterministic safety tests; no API key required
pytest tests/ -v

# Interactive demo and real-model evaluations
export OPENAI_API_KEY=sk-...
python chat.py
python -m evals.runner
```

## Architecture

```text
PaylaneAgent/
├── paylane/
│   ├── agent.py       Conversation loop, verification gate, and policy enforcement
│   ├── policy.py      Refund eligibility rules
│   ├── tools.py       Mock customer, transaction, refund, and ticket APIs
│   └── llm.py         OpenAI adapter and deterministic FakeLLM
├── evals/
│   ├── cases.py       12 core cases plus 5 adversarial real-model cases
│   └── runner.py      Evaluates calls, outcomes, leaks, and writes transcripts
├── tests/
│   └── test_guard.py  29 deterministic policy and security tests
├── transcripts/       Evaluation artifacts
├── docs/failure_log.md
├── customer_mail.txt  Policy questions for Paylane Support
└── chat.py            Interactive CLI
```

### Why this architecture holds up

- **Deterministic refund guard:** a model cannot override verification, ownership, amount, age, settlement state, duplicate-refund protection, or human review. The guard rechecks live transaction data immediately before money moves.
- **Monotonic human-only state machine:** high-risk requests and verified refunds that require human review create exactly one ticket. Later turns cannot return the case to automated account handling or refunding.
- **Privacy boundary at the tool layer:** verification is computed in code, not inferred by the model. Unknown accounts and incorrect credentials return the same model-facing result, preventing account enumeration.
- **Independent evaluation oracle:** expected outcomes are hand-written in `evals/cases.py`, rather than derived from production policy code, so a policy regression can still fail evaluation.

## Key decisions

- **Code, not prompts, is the safety boundary.** Every refund request rereads live transaction data and rechecks verification, ownership, status, age, amount, duplicate-refund state, and human-review state.
- **The model receives computed facts, not arithmetic homework.** Transaction age and `auto_approvable` are calculated in code before the model decides what to say or which safe action to take.
- **Verification is deterministic and privacy-preserving.** Tool output is identical for an unknown email and a wrong card ending: `{"verified": false}`. The model cannot use it to enumerate accounts.
- **Required handoffs bypass the model.** Legal action, fraud, account closure, transfer requests, frozen cards, and verified old/over-limit/pending refunds create one ticket and enter a human-only session state.
- **Handoff remains conversational, not operational.** After a ticket exists, the model can answer follow-up questions using only the stored reason and the latest redacted message. It receives no tools or account history, so it cannot reopen automated handling.
- **Tone guidance is not a brittle phrase blacklist.** I considered failing replies that say “soon” or “shortly,” but left them as normal customer-service language. The prompt still forbids invented specific timeframes and unsupported outcomes; hard checks focus on actions, policy, and privacy.
- **The mock supports full refunds only.** Partial refunds are rejected rather than pretending a binary `settled`/`refunded` record can track a remaining balance. (the mock API has no partialRefund value)

## Ambiguities handled conservatively

The brief leaves several product decisions open. The agent chooses the safer path and records the question for the Head of Support in [`customer_mail.txt`](customer_mail.txt):

- Pending transactions are escalated rather than refunded.
- **Temporary conservative fraud route:** all suspected fraud is escalated because a customer message is not an authoritative fraud-amount source. This is stricter than the brief's over-$500 rule and must be confirmed or changed with Paylane's Head of Support before launch.
- Frozen cards always go to a human, and the agent does not invent a freeze reason absent from the API.
- Exactly $75 is eligible; a transaction exactly 30 days old is not.
- Verification retry limits and any rolling per-customer refund cap are requested policy decisions, not silently invented thresholds.

### Known API-spec blocker: explaining a frozen card

The brief says the agent may explain why a card is frozen. The supplied
`get_customer` response provides only `status: frozen`; it contains no
customer-safe freeze reason. The agent therefore confirms the card is frozen,
does not invent a reason, and escalates the case rather than making an
unsupported explanation.

Before launch, this needs agreement with Paylane's Head of Support: either add
an approved customer-safe `freeze_reason` to the API, or define approved
generic wording and confirm that it satisfies the support policy. Until then,
the frozen-card explanation capability is intentionally unavailable.

### Known prototype limitation: one active case per chat

When a verified refund needs human review, this prototype creates the ticket in
code and ends automated account actions for the rest of that chat. This is two
separate protections:

1. **Create the ticket deterministically.** Without this, a model could tell a
   customer that Support will follow up without ever calling
   `escalate_to_human`; no case would actually reach Support. (I have noticed this even when testing with models
   like gpt-5.6-terra, despite the promt being very clear)
3. **Lock actions after the ticket exists.** Without this, a later pushback
   message could make the model retry `issue_refund`, fetch more account data,
   or give contradictory answers. The refund guard would still stop money from
   moving, but the customer experience would be unreliable.

The model can still explain the handoff in a tool-free mode, but it cannot
reopen the refund or start another automated request. That is the safest design
available with the supplied four tools: it avoids a false handoff or a reopened
decision without inventing an unsupported case-management workflow. 

I would rather talk about this with the client and come to a conclusion based on their 
needs than risk the agent lying to the user and call my solution "perfect UX".

The trade-off is that an unrelated eligible request—for example, refunding T100
after T101 was escalated—must start in a new chat. Before production, I would
confirm the desired case boundary with Support. If customers must handle several
requests in one chat, the system needs request-level case IDs and isolated state
per request; legal, fraud, and account-security cases may still require an
account-wide lock.

## Failures found and fixed

The first two were found in real-model evaluation. The latter four came from
adversarial review of the tool and session boundaries. In each case, the
deterministic guard meant a model mistake was an observable behaviour bug—not a
financial or privacy incident (even when the model made mistakes the money moves were prevented by the harness)

- **Exactly 30 days old — do not ask the model to do policy arithmetic.** The
  model treated a transaction at the boundary as refundable when it inferred
  its age from a date string. That would produce inconsistent customer outcomes
  around a hard cutoff. The guard had already prevented the refund, it now
  calculates `age_days` in code and makes day 30 human-only.
- **Narrated escalation — a promise is not a handoff.** `gpt-4o-mini` could say
  that a specialist would follow up without creating an escalation. The risk
  was a customer expecting help while no ticket existed. A verified old,
  over-limit, or pending transaction now creates the ticket in code as soon as
  it is looked up; the model explains the outcome in a tool-free handoff mode.
  The submitted `gpt-4o` baseline completes all 17 cases in three consecutive
  runs.
- **Partial-refund state mismatch — refuse what the ledger cannot represent.**
  The mock API has only a binary `refunded` state. A partial refund could have
  marked the entire transaction refunded, obscuring the remaining balance and
  future refund eligibility. The guard accepts full refunds only until a
  balance-aware refund ledger exists. (supplied by the client)
- **Account enumeration and stale identity — fail closed.** An unknown email
  and an incorrect card ending originally produced distinguishable results, and
  a failed lookup could leave an earlier verified identity in session state.
  That could leak account existence or blur customer boundaries. Both failures
  now return the same opaque result, and every verification attempt clears the
  prior verified session before checking credentials.
- **Frozen-card bypass — state must outrank a model instruction.** A verified
  frozen customer could still reach an otherwise eligible refund if the model
  ignored the prompt. That would violate the card restriction even though the
  model had seen the status. A verified frozen lookup now creates the ticket
  and enters human-only state before another tool call can run.
- **Non-finite refund amount — validate numbers before comparing them.** A tool
  argument such as `NaN` does not behave like an ordinary number in comparisons.
  Relying on threshold checks alone could create surprising policy paths. The
  guard now rejects non-finite requested and transaction amounts before every
  refund decision.

## Before production

- Replace email-plus-card-last-four verification with authenticated sessions or approved step-up verification.
- Use a durable payment ledger with atomic, idempotent refund operations and provider refund-state handling.
- Move escalation to a durable, retryable service with idempotency and customer-safe outage handling.
- Keep PII out of model context and logs where possible; implement retention, access control, and audit requirements.
- Confirm the open policy questions, then add monitoring, red-team evaluation, rate limits, concurrency tests, and a controlled rollout plan.

## How answers to my questions would change the design

- **Frozen card refunds:** I currently escalate any verified frozen-card case and
  do not refund it. If Support allows an otherwise eligible refund on a frozen
  card, I would remove that refund block while retaining escalation for unfreeze
  requests, then add a frozen-but-eligible refund evaluation.

- **Pending transactions:** I currently escalate pending transactions. If they
  may be refunded, I would allow `pending` in the eligibility guard, remove its
  human-review trigger, and add a pending auto-refund case. The mock can model
  that outcome, but production requires confirmation that the payment provider
  can safely refund a pending transaction.

- **Fraud at $500 or less:** I currently escalate every suspected fraud report.
  If smaller fraud claims should follow the normal refund policy, I would verify
  the customer, inspect the authoritative transaction amount, escalate only
  above $500, and add $500 / $500.01 boundary cases.

- **Verification contract:** I currently treat matching email and card-last-four
  values as verification for the chat session. If that is not the intended
  contract, the supplied tools cannot safely support auto-refunds; Paylane would
  need a verification endpoint or every refund would need human review.

- **Frozen-card reason:** I currently do not invent a reason because the mock
  returns only `status: frozen`. If Paylane supplies an approved `freeze_reason`,
  I would reveal it only after verification and keep the unfreeze escalation.
