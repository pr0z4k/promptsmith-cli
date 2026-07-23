# ADR 0001: Backend lifecycle and refinement orchestration

- **Status:** Accepted
- **Date:** 2026-07-23
- **Scope:** PromptSmith v1.0 architecture audit, Pass 3

## Context

PromptSmith supports deterministic, local-LLM, and hybrid refinement. Before this decision:

- `HybridBackend` imported the private `_apply_rules` helper from `core.models`.
- `PromptRefiner` selected backend classes, constructed them, executed them, handled fallback, derived telemetry, and interpreted errors in one method.
- A new backend instance could be created for every refinement call.
- Local LLM cleanup depended partly on object destruction and garbage collection.
- Constructor and runtime exception text could cross orchestration boundaries through logs or warnings.
- The abstract backend interface did not formally include lifecycle or error state.

This made backend boundaries difficult to test and made model ownership ambiguous.

## Decision

### Shared backend contract

Every refinement backend implements the `ModelBackend` contract:

- `refine(prompt, profile) -> Optional[str]`
- `last_error: Optional[str]`
- `unload() -> None`

Profiles passed to backends use the shared `RefinementProfile` typed contract.

### Explicit deterministic backend

Deterministic refinement is represented by `RuleBasedBackend`. Hybrid refinement composes a deterministic backend and an LLM backend instead of importing private rule helpers.

### Dependency injection for composition

`HybridBackend` accepts backend instances through its constructor. Production defaults remain unchanged, while tests and future orchestration code can supply controlled implementations.

### Refiner owns backend instances

`PromptRefiner` owns and caches backend instances by registered backend name. It reuses them across refinement calls and releases them through an idempotent `unload()` operation.

This establishes one clear owner for heavyweight native model resources.

### Registry owns trusted construction

`BackendRegistry` remains the only trusted class registry and construction boundary. Configuration selects a registered identifier, never an import path or module name.

Construction failures are converted into sanitized `BackendError` messages. Raw constructor details remain attached only as exception causes for diagnostic tooling and are not shown to users.

### Deterministic fallback remains guaranteed

When a configured backend is unavailable or returns no result, `PromptRefiner` uses its owned deterministic backend. The warning contract describes the fallback without exposing raw backend exceptions.

## Consequences

### Positive

- Local models can remain loaded across repeated refinements.
- Native resources have an explicit owner and cleanup path.
- Hybrid behavior can be tested without loading llama.cpp.
- Backend construction, execution, and fallback boundaries are clearer.
- Future backends must provide a consistent lifecycle and error contract.
- Raw exception details no longer need to cross the orchestration boundary.

### Tradeoffs

- A `PromptRefiner` instance retains backend resources until explicitly unloaded or destroyed.
- Applications embedding PromptSmith must call `unload()` during orderly shutdown.
- Runtime changes to backend configuration may require discarding or rebuilding the owning refiner.

## Deferred work

The Textual application module currently combines startup configuration, filesystem preparation, backend registration, service construction, UI definitions, modal screens, and event orchestration in one large module. Pass 3 does not attempt a wholesale rewrite.

A future bounded extraction should introduce:

1. an application bootstrap module for logging, paths, and trusted backend registration;
2. an application-services container for managers, analyzer, refiner, and history;
3. separate screen/modal modules;
4. explicit shutdown wiring that calls `PromptRefiner.unload()`;
5. tests proving that importing UI modules has no filesystem or registry side effects.

This extraction should preserve current behavior and be delivered incrementally rather than as a single UI rewrite.
