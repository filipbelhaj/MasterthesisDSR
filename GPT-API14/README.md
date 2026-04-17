# ORS Explorer

ORS Explorer  is a powerful, human-in-the-loop tool designed to help you build and expand your knowledge graphs. It's perfect for extracting structured information from legal or other complex texts and integrating it into Wikibase-style data.

**What it does:**
You provide source text, and ORS Explorer intelligently retrieves relevant existing knowledge from your graph. It then uses an advanced AI model to propose new, ontology-compliant facts (statement rows). You, the user, remain in control: you review these proposals, make any necessary edits, and then approve them. Only approved changes become part of your working knowledge graph. Finally, you can export your new knowledge in a delta-oriented JSON format or as QuickStatements for easy import into Wikibase.

**Your Workflow:**

## Typical Workflow

1.  **Configure:** Start by setting up your session.
    *   **Ontology:** Upload your `ontology.json` file. This file defines the structure of your knowledge graph (the types of entities and properties you can use). The tool uses this to ensure the AI's proposals are valid.
    *   **Existing Knowledge (Optional):** You can upload an existing `query.json` file to load your current knowledge graph. This allows you to extend your existing graph rather than starting from scratch. If `user_data_editable/query.json` already exists on the server, new sessions will automatically build upon it.

2.  **Extract:** This is where the magic happens.
    *   Paste your source text into the input area.
    *   Optionally, add specific instructions to guide the AI's extraction process.
    *   Click "Generate Proposal." The AI will analyze your text and propose new facts.
    *   **Review:** Carefully examine the proposed changes (in JSON format) and the AI's reasoning report. You can edit the proposed JSON directly if needed.
    *   **Approve:** Once you're satisfied, click "Append Proposal to Knowledge Graph." This adds the approved facts to your session's working graph.
    *   Repeat this process: extract more facts, review, and approve, building your graph incrementally.

3.  **Export:** Get your new knowledge ready for Wikibase.
    *   Go to the "Export" page. Here, you'll see a summary of all the new and changed facts from your session.
    *   **JSON Export:** Download a JSON file containing all added and deleted rows.
    *   **QuickStatements:** Generate QuickStatements commands. This is the format Wikibase uses for bulk imports.
        *   **Two-Step Process (if needed):** If the AI proposes entirely new entities that don't yet have Wikibase IDs, the tool will guide you through a two-step QuickStatements process. First, you'll create the new items in Wikibase to get their IDs, then you'll use those IDs to generate the final statements.

## What ORS Explorer Does For You

ORS Explorer is designed for **incremental graph building**, putting you in control at every step. The AI's output is always a **proposal**, never a direct change to your graph. You review and approve each step.

**Key Benefits:**

*   **Ontology-Constrained Extraction:** The AI understands and respects the structure of your knowledge graph, ensuring valid and consistent output.
*   **Intelligent Context Retrieval:** The tool automatically finds relevant existing information in your graph to help the AI make better proposals and avoid creating duplicate entities.
*   **Human-in-the-Loop Control:** You always have the final say. Review the AI's proposals, edit them if necessary, and approve only what you want to add.
*   **Duplicate Avoidance:** The system actively encourages the AI to reuse existing entities from your graph, helping to maintain a clean and consistent knowledge graph.
*   **Automated Source Linking:** When clear, the tool can automatically link new facts back to their source text.
*   **Session Management:** Your work is organized into sessions, allowing you to build your graph iteratively.
*   **Flexible Export:** Easily get your new knowledge in JSON or QuickStatements format for Wikibase.

## How It Works (Simplified)

1.  **Your Session:** When you start, you either begin with an empty graph or load an existing one (your "Base Graph"). As you approve proposals, your graph grows (your "Current Graph"). The tool keeps track of the differences (the "Delta Rows") between your starting graph and your current graph.
2.  **AI Context:** Before the AI generates proposals, the tool gathers all relevant information from your current graph and the ontology. This includes existing entity names, structured patterns, and related facts. This context helps the AI understand your graph's existing structure and make accurate, non-duplicative suggestions.
3.  **AI Proposal:** The AI then generates a set of proposed facts and a detailed explanation of its reasoning.
4.  **Your Approval:** You review these proposals. If you approve, the new facts are added to your session's working graph. This process also helps prevent stale proposals from being applied if your graph has changed since the proposal was generated.
5.  **Exporting Changes:** When you're ready, the tool generates export files based on the changes you've approved during your session.

## Core Concepts

| Term | Meaning |
| --- | --- |
| `ontology.json` | Ontology export that defines valid items, properties, and labels |
| `query.json` | Optional base graph export used to seed or replace the default session base |
| **Session:** | Your current workspace, where you incrementally build your knowledge graph. |
| **Base Graph:** | The state of your knowledge graph when you started the session. |
| **Current Graph:** | The evolving state of your knowledge graph as you approve proposals. |
| **Delta Rows:** | The net additions you've made to your graph during the session. |
| **Proposal:** | The AI's suggested changes, awaiting your review and approval. |
| **Approval:** | Your action to accept the AI's proposed changes and add them to your working graph. |
| **QuickStatements:** | A special format for importing data into Wikibase. |
| **Placeholder Subject (`NEW:entity_n`):** | A temporary ID for a brand-new entity proposed by the AI that doesn't yet exist in Wikibase. These require a two-step QuickStatements process. |

## Important Notes

*   **Temporary Work:** Your session's work (proposals and graph changes) is stored in the tool's memory. Restarting the tool or uploading a new ontology/query file will clear your current session's progress.
*   **Server Connection Required:** The tool's user interface must be accessed through the FastAPI server (e.g., `http://127.0.0.1:8000/`), not directly as a local file (`file://`).
*   **Human Oversight is Key:** While the AI is powerful and constrained, your review and approval are always essential to ensure the accuracy and quality of your knowledge graph.
*   **Deletion Export:** If you delete rows, they will be included in the JSON export but not in the QuickStatements output (as QuickStatements is primarily for adding/modifying, not deleting).
