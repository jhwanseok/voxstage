# Design patterns used, and why

For each pattern: where it is, why it was chosen, what was rejected, and which decision
record holds the full reasoning. Code is written with AI assistance; **choices are made by
the repo owner (jhwanseok)**. Where a choice is unclear it goes to the open-questions list
at the bottom and is decided by the owner before code depends on it.

| Pattern | Where | Why | Rejected alternative | Record |
|---|---|---|---|---|
| Strategy | `DialogueManager` and its rule / hybrid / LLM / agent implementations | One contract so stages can be swapped and compared on identical input; stages are added beside old ones, never overwriting them | One manager with a `stage` flag and branches inside | [0002](decisions/0002-dialogue-manager-contract.md) |
| Tagged union of value objects | `TurnInput = Utterance \| Dtmf \| ButtonPress` (`voxstage/turn.py`) | Inputs are data; frozen, loggable, handled with `match` | Class hierarchy with polymorphic methods | [0001](decisions/0001-turn-input-model.md) |
| Immutable state, copy on change | `DialogueState.evolve` | Replay from the log, no hidden state, safe comparison across managers | Manager object holding mutable state | [0002](decisions/0002-dialogue-manager-contract.md) |
| Interpreter | S1 rule engine running `flows/*.yaml` (planned) | Keeps domains as data so the core never imports domain code; fair, realistic rule baseline | Hand-written per-domain state machine | [0003](decisions/0003-rule-engine-representation.md) |
| Adapter | `voxstage/vendors/*` wrapping faster-whisper, MeloTTS, Gemini | Vendors differ; the pipeline sees only `ASR`, `LLM`, `TTS` | Calling vendor SDKs from the pipeline | not yet recorded |
| Simple factory | `voxstage.vendors.build(kind, name, **opts)` | Pick a vendor by name from a CLI flag | Registry with plugin discovery (more machinery than needed now) | not yet recorded |
| Actions as data | `HandOff`, `EndCall` returned in `DMResult.actions` | A manager says *what should happen*; something else decides how | Managers performing side effects directly | [0002](decisions/0002-dialogue-manager-contract.md) |

## Considered and not used

- **State pattern for dialogue flow**: would put flow logic in Python classes, against the
  domains-as-data rule.
- **Singleton / global session store**: hides state; conflicts with replayability.
- **Observer for events**: the event log is an append-only record read after the fact, not
  something components subscribe to.

## Open questions for the owner

1. **Streaming through the manager** (before S3): string reply vs streaming `respond`.
   Affects the T3 / T3b latency segments. See ADR 0002.
2. **Who executes actions and tool calls**: a separate executor component, or the pipeline.
   Decide when the "answer from API results" capability starts.
3. **Adapter and factory records**: those two choices predate this log. Write their records
   if you want them on the same footing as the others.
