# ORS Explorer Thesis Graph Pack

This is the canonical architecture pack for explaining ORS Explorer, the current UI name of the TriExtract artifact, in a thesis, demo, or handover.
The intent is to keep one clear figure set with one main message per figure instead of maintaining overlapping versions of the same story.

Use `thesis_graphs.drawio` as the editable source and this file as the speaking guide for what each figure is meant to communicate.
The pack is written so that a reader can understand the artifact even if they never open the codebase.

User-facing page labels are `Configure`, `Extract`, and `Export`, even though the file names remain `start.html`, `extract.html`, and `finalize.html`.

At the highest level, the four figures should communicate one consistent story:

1. ORS Explorer starts from an ontology and an optional/default base graph.
2. It can take an extra extraction instruction and retrieves relevant graph context before calling the chat model.
3. The model produces a reviewable patch and merged preview, not a direct graph mutation.
4. Only approved rows enter the working graph, and the export path is centered on the session delta.

## How To Use This Pack

| Figure | Best use | Core claim |
| --- | --- | --- |
| Figure 1. Artifact Overview | Intro, demo, artifact presentation | ORS Explorer is a human-in-the-loop artifact connecting UI, state, extraction, and export. |
| Figure 2. Retrieval-Informed Proposal Generation | Method, design rationale, AI explanation | The chat model is constrained by ontology, prompt metadata, and retrieved graph context; embeddings are used only for retrieval. |
| Figure 3. State And Data Objects | Architecture, implementation transparency | The system is built around explicit JSON state transitions rather than opaque model output. |
| Figure 4. Review, Approval, And Deployment Loop | Evaluation, control, deployment discussion | Graph growth happens through iterative review and append, with export separated from extraction. |

## Recommended Reading Order

If someone sees the pack for the first time, the easiest sequence is:

1. Figure 1 for the artifact overview
2. Figure 2 for the AI and retrieval explanation
3. Figure 3 for the important JSON objects and state transitions
4. Figure 4 for the human review and deployment logic

This order works well because it moves from user-facing behavior to implementation logic, then to deployment control.

## Diagram Conventions

Use these conventions consistently across the draw.io file and the thesis text:

- Rounded rectangles represent pages, processing steps, or logical components.
- Cylinders represent stored files or persistent JSON-like state objects.
- Double-bracket boxes represent external systems such as OpenAI or Wikibase.
- Arrows represent the main direction of information or control flow.

Keep these labels stable across figures:

- `proposal` means a generated result waiting for approval
- `current_kb_json` means the working graph after approvals
- `delta_kb_json` means the net session contribution
- `patch_kb_json` means the rows actually applied on approval
- `QuickStatements` means deployment output, not the working graph itself

## Core Terms

| Term | Meaning in the implementation | Why it matters in the thesis |
| --- | --- | --- |
| `mode` | Session mode: `create_new` or `extend_existing` | Explains whether the artifact starts from an empty graph or a server-side default base graph |
| `base_kb_json` | The session seed graph, usually loaded from `query.json` or an uploaded base graph | Defines the starting state of the artifact instance |
| `current_kb_json` | The mutable working graph after one or more approvals | Represents the artifact's evolving internal state |
| `delta_kb_json` | `rows_delta(base_kb_json, current_kb_json)` | Represents the net contribution produced during one session |
| `removed_kb_json` | Rows removed relative to the base graph | Explains why the JSON export can represent deletions even though QuickStatements cannot |
| `change_kb_json` | `{added_rows, deleted_rows}` convenience object returned by the state API | Makes the state and export payload easier to interpret |
| `proposal` | A generated extraction result stored before approval | Supports the human-in-the-loop review step |
| `patch_kb_json` | The rows actually applied on approval | Separates reviewable patch state from the full merged preview |
| `proposed_kb_json` | The merged preview graph shown to the reviewer before approval | Explains why the UI can show a full preview while approval still applies only a patch |
| `reasoning_report` | Structured explanation of why the proposal rows were suggested | Makes the review step intelligible and supports traceability |
| `user_extraction_instruction` | Optional user guidance included in prompt construction | Shows that the artifact accepts controlled runtime steering without bypassing ontology constraints |
| Two-step QuickStatements | Export mode where unresolved placeholders are created first and then bound in Step 2 | Handles Wikibase Cloud import constraints |

## Figure 1. Artifact Overview

Use when:
Introducing the artifact at a high level in a results, demo, or overview chapter.

Main message:
ORS Explorer combines user interaction, session state, ontology-constrained extraction, and Wikibase deployment in one review-centered workflow.

Suggested caption:
High-level overview of the ORS Explorer artifact, showing how user interaction, backend orchestration, AI-assisted extraction, and Wikibase export fit together.

```mermaid
flowchart LR
    U[User]

    subgraph UI[Presentation Layer]
        C[Configure Page<br/>upload ontology and base graph]
        E[Extract Page<br/>submit text, add instruction,<br/>review proposal, apply]
        X[Export Page<br/>review JSON and QuickStatements]
        G[Graph Preview<br/>interactive KG visualization]
    end

    subgraph APP[Application Layer]
        API[FastAPI API<br/>route orchestration]
        ST[Session State<br/>mode, base/current/delta,<br/>warnings, history]
        EX[Extraction Pipeline<br/>retrieval, prompting, validation]
        IDX[SQLite FTS Index<br/>retrieval over current graph]
        QS[Export Generator<br/>QuickStatements + Step 2 binding]
    end

    ONT[(user_data_editable/ontology.json)]
    Q[(user_data_editable/query.json)]
    OAI[[OpenAI API<br/>embeddings + chat]]
    WB[[Wikibase Cloud]]

    U --> C
    U --> E
    U --> X

    C --> API
    E --> API
    X --> API

    E --> G
    X --> G

    Q --> ST
    ST --> IDX
    IDX --> EX
    ONT --> EX
    EX --> OAI

    API --> ST
    API --> EX
    API --> QS
    ST --> QS
    QS --> WB
```

What to say:

- The artifact has three visible stages: configure, extract, and export.
- The user never writes directly to Wikibase; ORS Explorer always inserts a review step first.
- Session state is the backbone of the artifact because approved rows become the context for later rounds.
- This figure is intentionally broad; it should explain the shape of the artifact, not every intermediate data object.

Implementation anchors:

- `app.py`
- `backend/api.py`
- `backend/state.py`
- `backend/extractor/pipeline.py`
- `backend/quickstatements.py`

## Figure 2. Retrieval-Informed Proposal Generation

Use when:
Explaining how the AI component is constrained and why this is more than a raw LLM wrapper.

Main message:
Embeddings are used only to retrieve and rerank relevant graph context, while the chat model performs the actual structured extraction.

Suggested caption:
Retrieval-informed proposal generation in ORS Explorer, separating graph-context selection from ontology-constrained chat extraction.

```mermaid
flowchart LR
    T[Source Text] --> N[Normalize Input Text]
    I[Additional Instruction] --> PAY[Prompt Payload]
    KG[(current_kb_json)] --> L[Lexical Match + SQLite FTS]
    N --> L
    L --> C[Candidate KB Rows]

    N --> EQ[Embed Query Text]
    C --> ER[Embed Candidate Rows]
    EQ --> SIM[Cosine Similarity Rerank]
    ER --> SIM

    SIM --> P[Top-K Preview Rows]
    SIM --> EC[Entity Catalog<br/>reuse existing ids]
    SIM --> SC[Source Candidates]
    KG --> SR[Structured Reference Examples]
    KG --> IL[Relevant Item Labels]

    ONT[(Compact Ontology Cache)] --> PAY
    DP[Disallowed Extractor<br/>Properties] --> PAY
    N --> PAY
    P --> PAY
    EC --> PAY
    SC --> PAY
    SR --> PAY
    IL --> PAY
    SP[SYSTEM_PROMPT] --> CHAT[Chat Completion]
    PAY --> CHAT

    CHAT --> OUT[LLM JSON<br/>proposed_rows + changes]
    OUT --> CLEAN[Validate + Normalize Output]
    CLEAN --> POST[Entity Reuse + Source Fill + Merge]
    KG --> POST
    POST --> PROP[Proposal Package<br/>patch_kb_json + proposed_kb_json + reasoning_report + warnings]
```

What to say:

- The model does not receive raw text alone; it receives ontology constraints, a blocked-property list, retrieved graph context, and an optional `user_extraction_instruction`.
- The embedding model helps choose context rows but does not generate triples directly.
- Existing entities, source candidates, and structured-reference patterns are surfaced before generation so reuse is encouraged earlier, not only patched afterward.
- Validation, required-row checks, and merge still happen after generation, so the model is constrained both before and after the chat call.

Implementation anchors:

- `backend/extractor/context.py`
- `backend/extractor/pipeline.py`
- `backend/extractor/postprocess.py`
- `backend/core/prompt.py`
- `backend/core/config.py`

## Figure 3. State And Data Objects

Use when:
Explaining the implementation through its main JSON objects and how data moves through the system.

Main message:
ORS Explorer is a pipeline of explicit state objects and transformations, not a black-box LLM call.

Suggested caption:
Main state objects and transformations in ORS Explorer, from uploaded ontology and source text to session diff objects and importable QuickStatements.

```mermaid
flowchart LR
    ONT[(ontology.json)] --> OI[ONTOLOGY index<br/>compact prompt cache]
    Q[(query.json or uploaded base graph)] --> BASE[base_kb_json]
    BASE --> CUR[current_kb_json]

    TXT[Input Text] --> PAY[build_prompt_payload]
    INST[user_extraction_instruction] --> PAY
    OI --> PAY
    CUR --> PREV[preview rows + entity catalog + source candidates]
    PREV --> PAY

    PAY --> LLM[LLM JSON output]
    LLM --> PROW[proposal_rows_only]
    LLM --> CHG[changes]
    PROW --> PATCH[patch_kb_json]
    PROW --> MERGED[proposed_kb_json]
    CHG --> REASON[reasoning_report + warnings]

    PATCH --> UI[Review UI]
    MERGED --> UI
    REASON --> UI
    CUR --> APP[approve patch<br/>remove replaced rows + dedupe]
    UI --> APP
    APP --> CUR2[current_kb_json updated]

    BASE --> DELTA[delta_kb_json]
    CUR2 --> DELTA
    BASE --> REM[removed_kb_json]
    CUR2 --> REM
    DELTA --> CHANGE[change_kb_json<br/>added_rows]
    REM --> CHANGE
    CHANGE --> JSON[State payload + JSON export]
    DELTA --> QS[QuickStatements output]
```

What to say:

- `current_kb_json` is the evolving working graph used as future retrieval context.
- `delta_kb_json` is the net session contribution and is the main export object for QuickStatements.
- `patch_kb_json` is not the whole graph; it is the reviewable patch that approval applies to session state.
- The state API wraps these objects with metadata such as `mode`, `warnings`, and `token_usage_total`, but the core architecture is still driven by explicit graph-diff objects.

Implementation anchors:

- `backend/state.py`
- `backend/api.py`
- `backend/extractor/pipeline.py`
- `website/js/finalize.js`

## Figure 4. Review, Approval, And Deployment Loop

Use when:
Explaining why the artifact is human-in-the-loop and how deployment is controlled.

Main message:
Only approved rows enter the working graph, and final deployment is handled as a separate export stage.

Suggested caption:
Iterative graph construction and deployment in ORS Explorer, showing the propose-review-append loop and the QuickStatements export path.

```mermaid
flowchart LR
    MODE[Start Session<br/>create_new or extend_existing] --> CUR[(current_kb_json)]
    CUR --> TXT[Submit Source Text<br/>+ optional instruction]
    TXT --> GEN[Generate Proposal]
    GEN --> REV[Human Review<br/>inspect reasoning and edit patch JSON]
    REV --> APP[Approve Patch]
    APP --> DD[Remove replaced rows<br/>dedupe + increment kb_revision]
    DD --> CUR

    CUR --> EXP[Open Export Page]
    EXP --> D[rows_delta(base,current)]
    D --> JSON[JSON export<br/>added_rows / deleted_rows]
    D --> CHECK{Unresolved placeholders left?}
    CHECK -->|No| S[Single-step QuickStatements]
    CHECK -->|Yes| S1[Step 1<br/>CREATE new items]
    S1 --> MAP[Enter created QIDs]
    MAP --> S2[Step 2<br/>generate final statements]
    S --> WB[Import into Wikibase]
    S2 --> WB
```

What to say:

- The graph changes only after explicit approval.
- `kb_revision` prevents stale proposals from being merged over newer session state.
- In the shipped UI, clicking Export from the Extract page will first approve the currently edited patch if one is still pending.
- Final JSON export and QuickStatements are related but not identical outputs; deleted rows appear only in the JSON export path.
- QuickStatements is always delta-based and becomes a two-step flow only when unresolved placeholder subjects remain.

Implementation anchors:

- `backend/api.py`
- `backend/state.py`
- `backend/quickstatements.py`
- `website/js/extract.js`
- `website/js/finalize.js`

## Figure Selection Advice

If you show only one figure:
Use Figure 1.

If the examiner asks how the AI part works:
Use Figure 2.

If they ask about internal data structures or implementation transparency:
Use Figure 3.

If they ask how the graph is built iteratively and why the process is controlled:
Use Figure 4.

## Presentation Notes

- Keep the words "proposal", "approval", and "delta" consistent across the thesis. Those three terms explain most of the artifact logic.
- Emphasize that the artifact is stateful across rounds. This is one of the main differences from a one-shot extraction demo.
- When discussing AI, stress that retrieval and prompt construction constrain the model before generation, not only after the fact.
- When discussing deployment, stress that QuickStatements generation is downstream from review, not part of generation itself.

## What The Figures Intentionally Omit

For readability, the graphs do not try to show every implementation detail.
That is deliberate.

The pack omits or compresses:

- full token-usage accounting and other minor metadata fields
- per-warning list formatting in the UI
- browser storage details such as `localStorage`
- styling and graph-rendering details from the frontend
- helper functions that support retrieval, normalization, and formatting

These details matter in the code, but including them in the figures would make the thesis graphics harder to read.

## Completeness Checklist

Before treating the draw.io file as final, check that the figures still make these points clearly:

- The ontology and optional base graph are shown as separate inputs.
- Retrieval happens before the chat completion call.
- Embeddings are presented as retrieval support, not as the extraction mechanism itself.
- The optional `user_extraction_instruction` is shown as prompt metadata, not as a way to bypass ontology constraints.
- Model output is presented as a proposal, not as an automatic graph write.
- Approval is shown before mutation of `current_kb_json`.
- `delta_kb_json` is shown as the main export object, not the same thing as a single proposal patch.
- QuickStatements is shown as a deployment path downstream from review.
- Two-step QuickStatements is shown only as a conditional path when unresolved placeholders remain.
