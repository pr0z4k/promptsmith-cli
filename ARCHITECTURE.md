# PromptSmith-cli Architecture

## Vision

PromptSmith-cli implements the **Intent Compiler** pattern:

```
Human Thought -> Analyzer -> Challenge -> Readiness -> Recommendations -> Preparation -> Output
```

Transforming ambiguous human intent into precise, structured AI instructions before any LLM inference occurs.

## Core Components

### 1. Configuration Management
- **ConfigManager**: Centralized configuration storage with dot-notation access
- **YAMLConfigStore**: Abstract base class for YAML-backed configuration,
  loading from an optional `user_dir` in addition to the base
  `config_dir` - entries in `user_dir` override same-named entries from
  `config_dir`, and new writes (`add_config`) always target `user_dir`
  when set, never the built-in directory. Used by both `ProfileManager`
  and `TemplateManager` to give user-space profiles/templates
  (`~/.promptsmith/profiles/`, `~/.promptsmith/templates/`) precedence
  over the bundled defaults without ever mutating them in place.

### 2. Profile System
- **ProfileManager**: Manages persona profiles with validation
- **ProfileSchema**: Hand-rolled `isinstance()`-based validation - checks
  required fields, type-checks optional ones, and fills in sensible
  defaults (`domain`, `tone`, `format`, `constraints`, `version`,
  `backend`). Wired in as the actual live validation via
  `YAMLConfigStore`'s `config_schema` parameter; `pydantic` was
  previously a declared but entirely unused dependency (imported
  defensively in a try/except, never referenced) and has been removed
  rather than migrated to, since the hand-rolled validation here has
  already been exercised through this project's full bug-finding history.
- **Built-in Profiles**: 35 domain profiles shipped inside the package
  (`src/promptsmith/data/profiles/`), spanning software engineering
  (AEM, React, NextJS, cloud, microservices), architecture, business,
  and content roles, plus `vibe-coding` for general AI-assisted work

### 3. Template System
- **TemplateManager**: Manages prompt templates with validation
- **TemplateSchema**: Hand-rolled `isinstance()`-based validation (same
  note as above) - also now the actual live validation path, not dead
  code sitting unused alongside a separate, simpler duplicate check.
- **Built-in Templates**: 22 templates shipped inside the package
  (`src/promptsmith/data/templates/`) - component/app skeletons, cloud
  infrastructure, business documents, and process artifacts

### 4. Intent Compiler Pipeline
- **IntentCompiler**: A single `compile()` entry point that runs
  analysis -> readiness -> recommendations -> profile selection ->
  preparation -> re-analysis as one coherent pipeline, matching the vision
  above. **Currently not called by the app** - `cli/app.py`'s
  `action_analyze()`/`action_refine()` call `PromptAnalyzer`/`PromptRefiner`
  directly and duplicate this orchestration by hand, missing out on
  re-analysis-after-refinement and the unified compilation score. This
  remains a real architectural gap, flagged again by an external review -
  but a maintainability concern, not a correctness one: the direct-call
  path is what's actually been tested against every real bug found in
  this project. Deliberately left as-is rather than wired in or removed;
  worth a real decision eventually, just not an urgent one.
- **PromptAnalyzer**: Deterministic analysis of prompts for quality and readiness
  - Type detection (coding, AEM, NextJS, React, architecture, etc.) -
    word-boundary matched to avoid short patterns matching inside
    unrelated words
  - Smell detection with explanations and severity
  - Missing elements detection
  - **Challenge detection**: rule-based clarifying questions (not
    LLM-generated) surfacing genuine gaps - vague scope, missing success
    criteria, missing audience, vague quantities, unstated integration
    constraints. Informational only, applies identically regardless of
    profile/template/backend since it runs before a backend is selected.
  - Actionable recommendations
  - Readiness assessment
- **CompilationStep**: Represents individual pipeline stages
- **IntentCompilationResult**: Complete result with analysis, refined prompt, and metadata

### 5. Prompt Refinement
- **PromptRefiner**: Core component that orchestrates refinement
- **ModelBackend**: Abstract base class for refinement backends
- **RuleBasedBackend**: Deterministic rule-based refinement
- **LLMBasedBackend**: LLM-powered refinement via `create_chat_completion()`
  with proper role-structured messages and a validated `chat_format`
  (checked against the installed llama-cpp-python's actual registry before
  use, since a hardcoded guess isn't reliably registered across versions)
- **HybridBackend**: Runs `RuleBasedBackend` first for guaranteed
  completeness, then asks the LLM to polish that text into clearer prose;
  falls back to the pure rule-based result if the LLM is unavailable or
  the polish looks truncated/degenerate

### 6. Plugin System
- **BackendRegistry**: Registry for backend plugins
- **PluginManager**: Manages plugin discovery and loading

### 7. Utility Modules
- **SystemUtils**: System-level utilities (RAM, paths)
- **PathUtils**: Path resolution utilities
- **Filesystem**: Filesystem operations

## Data Flow

### Original Flow (Preserved)
1. User provides raw prompt
2. System loads appropriate profile and template
3. PromptRefiner orchestrates refinement:
   - Template expansion
   - Backend processing (LLM or rule-based)
   - Rule-based fallback
4. Refined prompt returned to user

### New Intent Compiler Flow
1. **Analysis**: User provides raw prompt
   - PromptAnalyzer detects type (AEM, NextJS, React, coding, etc.)
   - Identifies missing elements (Context, Audience, Output Format, Constraints, Purpose)
   - Detects smells (ambiguous terms like "modern", "best", "optimize")
   - Generates actionable recommendations
   - Calculates readiness score (0-100)
   - Recommends optimal profile

2. **Readiness Assessment**: Determines if prompt is ready for AI
   - Score >= 80
   - No high-severity smells
   - No critical missing elements
   - Minimum word count met

3. **Recommendation**: Provides guidance
   - Suggests profile based on detected type
   - Offers actionable improvements
   - Prioritizes recommendations

4. **Preparation**: Refines the prompt
   - Applies selected profile constraints
   - Expands templates if selected
   - Applies rule-based improvements
   - Returns structured, AI-ready prompt

5. **Output**: Delivers result
   - Refined prompt
   - Compilation metadata
   - Step-by-step analysis

## Key Design Decisions

1. **Plugin Architecture**: Backends are pluggable components
2. **Validation**: Strict schema validation for all data
3. **Separation of Concerns**: Clear boundaries between components
4. **Configuration**: Centralized, flexible configuration system
5. **Error Handling**: Graceful degradation when components fail
6. **Local-First**: All analysis is deterministic, offline, and requires no LLM
7. **Domain-Aware**: AEM, React, NextJS, cloud, and business profiles and
   patterns ship built-in and are fully user-extensible

## Intent Compiler Architecture

### Principles
- **Think before inference**: Analyze prompts before spending AI compute
- **Clarity beats verbosity**: Better prompts over longer prompts
- **Deterministic analysis**: All analysis is predictable and repeatable
- **Local-first**: No token usage for analysis
- **Reduce ambiguity**: Clarify intent before AI processing
- **Every feature improves intent**: Not just adds functionality

### Pipeline Stages

```
┌─────────────────────────────────────────────────────────────┐
│                    Intent Compiler Pipeline                      │
├─────────────────────────────────────────────────────────────┤
│  1. Human Thought (Input)                                      │
│           ↓                                                    │
│  2. Analysis                                                   │
│     ├── Type Detection (AEM, NextJS, React, coding, etc.)    │
│     ├── Missing Elements (Context, Audience, Format, etc.)     │
│     ├── Smell Detection (ambiguous terms with severity)       │
│     ├── Challenge Detection (rule-based clarifying questions, │
│     │   informational only - scope, success criteria,         │
│     │   audience, quantity, integration constraints)          │
│     └── Recommendations (actionable, prioritized)              │
│           ↓                                                    │
│  3. Readiness Assessment                                       │
│     ├── Score Calculation (0-100)                             │
│     ├── Binary Ready/Not Ready                                │
│     └── Readiness Reasoning                                    │
│           ↓                                                    │
│  4. Profile & Template Selection                               │
│     ├── Auto-recommended based on analysis                     │
│     └── User override supported                                │
│           ↓                                                    │
│  5. Preparation (Refinement)                                   │
│     ├── Profile constraints applied                           │
│     ├── Template expansion                                     │
│     └── Rule-based improvements                               │
│           ↓                                                    │
│  6. Output (AI-Ready Prompt)                                   │
└─────────────────────────────────────────────────────────────┘
```

### Domain Extensions

Web-platform work (AEM, React, NextJS) gets first-class treatment:

- **Profiles**: AEM Developer, React AEM Developer, NextJS AEM Developer, Customer Portal Architect
- **Type Detection**: AEM, NextJS, React, React-AEM, NextJS-AEM patterns
- **Templates**: AEM component, NextJS app skeleton, React AEM integration
- **Recommendations**: AEM best practices, NextJS conventions, React patterns

The same mechanism extends to any domain - drop a profile/template YAML
into the user directory and the analyzer's recommendations pick it up.

### Scoring Algorithm

The prompt quality score (0-100) is calculated as:

```
Base Score: 100
- Missing Elements: -10 per missing (max -40)
- High Severity Smells: -7 per smell (max -30)
- Medium Severity Smells: -3 per smell (max -15)
- Too Short: -2 per word deficit (max -20)
+ All Elements Present: +10
+ No High Severity Smells: +5
```

Readiness threshold: Score >= 80 AND no high-severity smells AND no critical missing elements

### Readiness Criteria

A prompt is **READY FOR AI** when:
- Score >= 80/100
- No high-severity smells ("best", "optimize", "better", etc.)
- No critical missing elements (Context, Audience/Role)
- Minimum word count for type is met

## Packaging, Data Layout, and Versioning (v0.6)

### Single-source version

`pyproject.toml` is the only place the version is written. It flows to:

- `promptsmith._version.__version__` - read back at runtime through
  `importlib.metadata`, with `display_version()` formatting PEP 440 for
  humans (`0.6.0b1` -> `0.6 Beta`)
- the **About screen** and the `--version` / `-V` flag
- **build artifact names** - both build scripts read it via
  `tools/get_version.py`
- **frozen builds** - the scripts pass `--copy-metadata promptsmith-cli`
  so the bundled app reads the same metadata, verified by each script's
  post-build smoke test

### Built-in data lives inside the package

Built-in profiles and templates moved from the repository root into
`src/promptsmith/data/`, declared as `package-data`. Resolution order in
`path_utils.get_asset_path()`:

1. `<root>/<asset>` when it exists - frozen builds, where the build
   script places `profiles/`, `templates/`, `models/` as visible,
   editable siblings of the executable
2. the package's own `data/` directory - source checkouts and wheel
   installs
3. `<root>/<asset>` regardless - preserves the always-return-a-path
   contract (e.g. `models/` before any model has been downloaded)

`get_project_root()` no longer raises when there is no `pyproject.toml`
above the code (the installed-wheel case); it falls back to
`~/.promptsmith` so config and exports still have a writable, persistent
home. This closed the long-standing known limitation where a plain wheel
install couldn't locate its built-ins.

### UI identity

The public build renders black background with green shades (classic
green-phosphor terminal) as the visual cue distinguishing it from the
internal orange-themed builds. The About screen shows the product name,
live version, project URL (https://codeberg.org/prozak/promptsmith-cli),
MIT license, and a Get Support button opening the issue tracker.
