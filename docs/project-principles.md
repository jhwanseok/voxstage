# Project Principles

## Goal

Build a staged, observable voicebot engine as a reference implementation for production-oriented Voice AI (AICC).

The engine evolves one swappable stage at a time, so each step can be measured, compared with the previous one, and written up:

- Intelligence axis: S1 rule-based → S2 NLU / FAQ / DST → S3 LLM → S4 agent
- Transport axis: S0 batch pipeline → S5 streaming STT / TTS

Experiments run on synthetic domain packs (bank first, then shopping mall, then a third), never on real customer data.

## Design Principles

- Systems over demos.
- Reproducibility over maximum performance.
- Documentation is engineering.
- Engineering decisions should leave evidence.
- Keep components replaceable.
- Observe first: every stage emits events, and every number is derived from the event log.
- Compare, don't overwrite: new stages are added next to old ones, so the stage comparison stays reproducible.
- Domains are data: the core never imports domain code. Adding a domain must leave the core diff at zero.
- Public basis: every design decision (ADR) cites at least one independent public source, or is validated by this repo's own experiment, or is not adopted.

## Core Capabilities

- End-to-End AI System Architecture
- Production Reliability
- AI Evaluation (text mode and audio mode, stage comparison table)
- AI Application Engineering
- Observability (latency breakdown, shadow cost, failure taxonomy)

## Non-Goals (v0.1)

- Streaming (S5): interfaces are designed for it from the start, but the implementation comes after S1–S4
- GPU optimization
- Kubernetes deployment
- Multi-agent orchestration (S4 is a single agent loop)
- A production-ready product: this is a reference and learning implementation
- Anything derived from an employer's code, data, models, or internal structure
