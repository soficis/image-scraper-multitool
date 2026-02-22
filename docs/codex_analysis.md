# Codex Adherence Audit — image-scraper-multitool

**Date:** February 22, 2026  
**Audited against:** `codex_agents.md`  
**Scope reviewed:**

- `image_scraper_multitool.py` (1,614 lines)
- `image_scraper_gui.py` (1,155 lines)
- `README.md`
- `requirements.txt`
- Repo structure/tooling

---

## 1) Executive Summary

Original audit status: **Not compliant** with `codex_agents.md`.

There are **critical blockers** (P0) that must be fixed before calling the codebase aligned:

1. **CLI entrypoint is effectively broken/dead** (`image_scraper_multitool.py:1599-1614`).
2. **Accidental AI scratch comments and dead code shipped in production file** (`image_scraper_multitool.py:1600-1614`).
3. **No test suite or one-command quality gates** (violates “Plan → Build → Prove” and DoD sections).

The codebase was then remediated via the phase plan below.

## Implementation Status (Completed on February 22, 2026)

All planned phases have now been implemented end-to-end:

- ✅ Phase 1 — Runtime entrypoints/contracts stabilized
- ✅ Phase 2 — Tests + one-command quality gate added
- ✅ Phase 3 — Pure logic extracted into domain/app layers
- ✅ Phase 4 — Engine adapters split with shared downloader
- ✅ Phase 5 — GUI refactored into thin presentation flow with separate scrape/HEIC job state
- ✅ Phase 6 — Typed error model introduced and broad silent fallbacks removed
- ✅ Phase 7 — Queue hotspot measured and optimized (`deque`), docs synced

See `docs/performance.md` for benchmark details.

---

## 2) Compliance Scorecard (against codex_agents.md)

| Area | Status | Notes |
|---|---|---|
| Correctness | ❌ | Broken CLI entrypoint, ignored inputs, inconsistent behavior paths |
| Clarity | ❌ | Two large monolith files, oversized functions, mixed concerns |
| Solo maintainability | ❌ | Hard to reason/change safely; no package structure; high coupling |
| Security & reliability | ⚠️ | Broad exception swallowing, weak boundary validation, no regression tests |
| Performance | ⚠️ | Expensive scraping loops and queue patterns not measured |
| No dead code | ❌ | Dead comments, duplicate keys, unused imports |
| No legacy/fallback clutter | ⚠️ | Multiple fallback branches and selector cascades mixed into main flow |
| Prove with tests | ❌ | No tests found |
| One-command build/test/lint/typecheck | ❌ | No unified commands/tooling gates |

---

## 3) Detailed Findings

## P0 — Must fix first

### P0-1: CLI entrypoint is non-functional
- **Evidence:** `image_scraper_multitool.py:1599-1614` ends in comment block + `pass`.
- **Why this violates codex_agents:** correctness first, no dead code, least astonishment.
- **Impact:** Running module directly does not execute `main()`; shipped behavior is ambiguous and broken.
- **Required change:** restore canonical entrypoint:
  - `if __name__ == "__main__": raise SystemExit(main())`

### P0-2: Accidental scratch commentary committed to runtime file
- **Evidence:** `image_scraper_multitool.py:1600-1613` contains internal planning text.
- **Why this violates codex_agents:** delete dead code immediately; keep professional, maintainable source.
- **Impact:** Major trust/maintainability hit; indicates missing code-quality gate.
- **Required change:** remove the entire block and replace with real entrypoint.

### P0-3: No verification safety net (tests + quality gates)
- **Evidence:** repo has no `tests/` and no configured lint/type/test command harness.
- **Why this violates codex_agents:** “Plan → Build → Prove”, DoD, no overridden safeties.
- **Impact:** regressions can’t be detected; refactors are high risk.
- **Required change:** add minimal deterministic test suite + one-command checks.

## P1 — High priority structural/correctness issues

### P1-1: User-provided chromedriver path is ignored
- **Evidence:** `scrape_with_google(..., chromedriver_path: Path, ...)` receives param (`:635`) but forcibly overrides it (`:648-653`).
- **Impact:** API contract lies; GUI/CLI option is misleading.
- **Required change:** choose one behavior and apply consistently:
  - either honor explicit path strictly,
  - or remove path argument/option entirely (breaking change allowed/preferred).

### P1-2: Monolithic architecture with mixed responsibilities
- **Evidence:**
  - `image_scraper_multitool.py` is 1,614 lines.
  - `scrape_with_google` spans ~455 lines (`628-1082`).
  - `GenericPageScraper.scrape` spans ~287 lines (`1269-1555`).
  - GUI `_build_layout` spans ~440 lines (`242-681`).
- **Impact:** high cognitive load; brittle edits; difficult testing.
- **Required change:** split by domain/use-case/adapter/UI boundaries.

### P1-3: Exception handling is too broad and often suppressive
- **Evidence:** many `except Exception` and silent `pass` blocks across scraper loops.
- **Impact:** hidden failures, nondeterministic outcomes, poor debuggability.
- **Required change:** replace with narrow exception types + contextual errors + explicit handling strategy.

### P1-4: Shared thread/stop state across independent workflows in GUI
- **Evidence:** scraping and HEIC conversion reuse the same `self.worker` + `self.stop_event` (`_on_start` vs `_on_convert_heic`, around `722-737` and `1065-1100`).
- **Impact:** operations can interfere; stop semantics are ambiguous.
- **Required change:** separate controllers/state for scrape job vs HEIC conversion job.

## P2 — Cleanup and consistency issues

### P2-1: Duplicate dict key in GUI state initialization
- **Evidence:** `"resize_width"` declared twice in `_init_variables` (`229-230`).
- **Impact:** dead/overwritten code; avoidable confusion.
- **Required change:** keep one entry.

### P2-2: Redundant duplicate assignment
- **Evidence:** `_choose_output_dir` sets `output_dir` twice (`690` and `692`).
- **Impact:** small but noisy dead logic.
- **Required change:** remove duplicate write.

### P2-3: Unused imports in core module
- **Evidence:** `importlib`, `shutil`, `sys`, `tempfile`, `zipfile`, `platform`, `subprocess` imported but not used.
- **Impact:** clutter, misleading intent.
- **Required change:** remove all unused imports.

### P2-4: README/behavior drift risk
- **Evidence:** README claims broad CLI capabilities while runtime entrypoint is broken and contracts are inconsistent.
- **Impact:** user surprise/support burden.
- **Required change:** update README only after behavior is stabilized.

---

## 4) Target Architecture (Codex-aligned)

Use a small Python package layout with clean boundaries:

```text
src/image_scraper/
  domain/
    models.py
    rules.py
  app/
    scrape_images.py
    convert_heic.py
  adapters/
    bing.py
    google.py
    custom_page.py
    heic_converter.py
    filesystem.py
  cli/
    main.py
  ui/
    tkinter_app.py
tests/
```

Principles:
- Pure logic in `domain`/`app`.
- Network/Selenium/Pillow/Tk in `adapters` and `ui`.
- Thin CLI entrypoint.
- Strong typed options objects; no silent ignored args.

---

## 5) Phase-by-Phase Roadmap (implementation slices)

## Phase 1 — Stabilize runtime entrypoints and contracts (P0)
**Goal:** Restore deterministic executable behavior and remove dead artifacts.

**Slice:**
- Fix `__main__` entrypoint.
- Delete scratch comment block.
- Decide and enforce chromedriver contract (honor path or delete option).
- Remove duplicate GUI key/assignment.
- Remove unused imports.

**Done when:**
- CLI starts reliably.
- No dead/commented scratch code in runtime modules.
- Public options match actual behavior.

## Phase 2 — Add minimum safety net (tests + quality commands)
**Goal:** Make refactors safe.

**Slice:**
- Add `tests/` with deterministic unit tests for:
  - filename sanitization,
  - slugify,
  - extension detection,
  - argument parsing defaults/validation.
- Add one-command quality workflow (format/lint/typecheck/tests).

**Done when:**
- One command runs all gates successfully.
- Core utility regressions are covered.

## Phase 3 — Extract pure domain/app logic
**Goal:** Reduce cognitive load and enforce functional-core boundary.

**Slice:**
- Introduce typed config/result models.
- Move pure helpers (naming, extension, resolution checks) into domain modules.
- Keep I/O behavior unchanged.

**Done when:**
- Shared logic is centrally testable without Selenium/network.

## Phase 4 — Split engine adapters (Bing/Google/Custom)
**Goal:** Break monolith into composable adapters.

**Slice:**
- Create separate adapter modules per engine.
- Define one orchestrator use-case that calls adapters.
- Remove duplicated download/save logic via a small shared file-saving adapter.

**Done when:**
- Each engine has a focused implementation file.
- Orchestration has no engine-specific branching explosion.

## Phase 5 — Refactor GUI into thin presentation layer
**Goal:** Keep UI declarative; move behavior to app layer.

**Slice:**
- Split huge `_build_layout` and worker logic into UI components/controllers.
- Separate scrape and HEIC job lifecycle state.
- Keep Tk-specific code only in UI module.

**Done when:**
- GUI no longer owns business logic.
- Start/stop semantics are clear and isolated by job type.

## Phase 6 — Error model hardening and observability
**Goal:** predictable failure behavior.

**Slice:**
- Replace broad catches with typed exceptions.
- Standardize error payloads (operation + key input + cause).
- Ensure logs are informative and non-secret.

**Done when:**
- Failures are actionable and traceable.
- No silent exception swallowing.

## Phase 7 — Performance pass + docs sync
**Goal:** optimize known hotspots and lock in maintainability.

**Slice:**
- Measure key bottlenecks (Google scrape loop, custom crawl queue, image processing).
- Apply targeted fixes only where measured.
- Update README and developer docs to match final behavior.

**Done when:**
- Measured bottlenecks improved.
- Docs reflect real capabilities.

---

## 6) Master Prompts to Start Each Phase

Copy/paste these one at a time.

### Master Prompt — Phase 1
> Implement **Phase 1** from `docs/codex_analysis.md` exactly. Make only Phase 1 changes. Use breaking changes where they reduce complexity. Remove dead code and fix all call sites. After changes, run available checks and summarize what was fixed.

### Master Prompt — Phase 2
> Implement **Phase 2** from `docs/codex_analysis.md`. Add a minimal deterministic test suite and a one-command quality workflow (format/lint/typecheck/tests). Do not add speculative features. Show the exact command(s) and results.

### Master Prompt — Phase 3
> Implement **Phase 3** from `docs/codex_analysis.md`. Extract pure domain/app logic into clear modules with typed models. Keep behavior stable while reducing complexity. Update tests for moved logic.

### Master Prompt — Phase 4
> Implement **Phase 4** from `docs/codex_analysis.md`. Split engine adapters and centralize shared download/save behavior. Remove duplication and update all imports/call sites. Prove no regressions with tests.

### Master Prompt — Phase 5
> Implement **Phase 5** from `docs/codex_analysis.md`. Refactor the GUI into a thin presentation layer with separate job-state controllers for scraping vs HEIC conversion. Keep UI behavior consistent while simplifying internals.

### Master Prompt — Phase 6
> Implement **Phase 6** from `docs/codex_analysis.md`. Replace broad exception handling with typed errors and explicit context. Ensure no silent failures. Update tests to cover error paths.

### Master Prompt — Phase 7
> Implement **Phase 7** from `docs/codex_analysis.md`. First measure performance hotspots, then optimize the biggest one(s) only. Update README/docs to match final behavior. Include before/after metrics.

---

## 7) Recommended Immediate Next Step

Start with **Phase 1** now. It is small, high-impact, and removes the biggest correctness/maintainability blockers before deeper refactoring.
