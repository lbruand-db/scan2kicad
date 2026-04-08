# KiCad Agents in Databricks Genie Code - Specification

**Version:** 1.0
**Date:** 2026-04-08
**Status:** Draft

---

## Table of Contents

1. [Overview](#1-overview)
2. [Genie Code Extension Mechanisms](#2-genie-code-extension-mechanisms)
3. [Approach A: KiCad Skills](#3-approach-a-kicad-skills)
4. [Approach B: KiCad MCP Server](#4-approach-b-kicad-mcp-server)
5. [Approach C: Combined Skills + MCP](#5-approach-c-combined-skills--mcp)
6. [kicad-tools Capabilities Reference](#6-kicad-tools-capabilities-reference)
7. [Architecture](#7-architecture)
8. [Implementation Plan](#8-implementation-plan)

---

## 1. Overview

This specification describes how to integrate [kicad-tools](https://github.com/rjwalters/kicad-tools) into **Databricks Genie Code** so that users can interact with KiCad schematics and PCBs through natural language in Agent mode.

Genie Code offers two extension mechanisms:

| Mechanism | What it provides | Docs |
|-----------|-----------------|------|
| **Skills** | Markdown-based guidance + scripts that Genie loads contextually | [docs.databricks.com/.../skills](https://docs.databricks.com/aws/en/genie-code/skills) |
| **MCP Servers** | Tool endpoints that Genie can call as structured function calls | [docs.databricks.com/.../mcp](https://docs.databricks.com/aws/en/genie-code/mcp) |

Both mechanisms require **Genie Code Agent mode** to be active.

---

## 2. Genie Code Extension Mechanisms

### 2.1 Skills

Skills are folders containing a `SKILL.md` file (with frontmatter) plus optional scripts and documentation. They live in one of two locations:

| Scope | Path | Visibility |
|-------|------|-----------|
| Workspace | `Workspace/.assistant/skills/{skill-name}/` | All workspace members |
| User | `/Users/{username}/.assistant/skills/{skill-name}/` | Creator only |

Genie loads skills automatically based on request relevance, or users can `@`-mention them explicitly. Skills provide **guidance and code patterns** — they tell the agent *how* to approach a task.

**SKILL.md format:**

```markdown
---
name: skill-name
description: What this skill does and when to use it
---

## Instructions
Step-by-step guidance...

## Examples
Sample inputs/outputs...
```

### 2.2 MCP Servers

MCP (Model Context Protocol) servers expose **callable tools** that Genie can invoke as structured function calls. Databricks supports five MCP server types:

| Type | Description |
|------|-------------|
| **Unity Catalog functions** | Execute predefined SQL/Python UDFs |
| **Vector search indexes** | Query indexed documents |
| **Genie spaces** | Analyze data via natural language |
| **UC connections** | External MCP servers (pre-authenticated) |
| **Databricks Apps** | Custom MCP servers deployed as apps |

**Constraints:**
- Maximum **20 tools** across all connected MCP servers
- Apps must be **stateless** (`stateless_http=True`)
- App MCP endpoint must be at `https://<server-url>/mcp`
- Users can selectively enable/disable individual tools in settings

### 2.3 Skills vs MCP: When to Use Which

| Use case | Skills | MCP |
|----------|--------|-----|
| Teach Genie *how* to reason about schematics | Yes | |
| Provide reusable code patterns | Yes | |
| Execute structured operations (BOM, DRC, etc.) | | Yes |
| Return structured JSON data | | Yes |
| Combine multiple steps with domain knowledge | Yes | |
| Enforce specific workflows | Yes | |

---

## 3. Approach A: KiCad Skills

### 3.1 Skill: `kicad-schematic-analysis`

Teaches Genie how to analyze schematics from the `main.kicad.open_schematics` Delta table.

**Path:** `Workspace/.assistant/skills/kicad-schematic-analysis/`

```
kicad-schematic-analysis/
├── SKILL.md
├── examples/
│   └── sample-queries.md
└── scripts/
    └── analyze_schematic.py
```

**SKILL.md:**

```markdown
---
name: kicad-schematic-analysis
description: >
  Analyze electronic schematics from the open-schematics dataset stored in
  main.kicad.open_schematics. Use this skill when the user asks about
  electronic components, circuit analysis, BOM generation, schematic
  comparison, or component frequency analysis.
---

## When to Use

Activate this skill when the user:
- Asks about components in a schematic
- Wants to generate a Bill of Materials (BOM)
- Asks about component usage frequency across projects
- Wants to compare schematics
- Asks about schematic metadata (project names, descriptions, types)

## Data Source

The schematics are stored in `main.kicad.open_schematics` with these columns:
- `schematic` (STRING): Raw .kicad_sch S-expression content
- `image` (BINARY): PNG rendering of the schematic
- `components_used` (ARRAY<STRING>): Component identifiers
- `json` (STRING): JSON representation of schematic structure
- `yaml` (STRING): YAML metadata
- `name` (STRING): Project name (e.g., "TiebeDeclercq/Uart-programmer")
- `description` (STRING): Project description
- `type` (STRING): File extension (.kicad_sch)

Derived views are also available:
- `main.kicad.schematic_components`: Exploded components (one row per component)
- `main.kicad.component_frequency`: Component usage counts

## Instructions

1. For component queries, prefer the `components_used` array column or
   the `schematic_components` view over parsing the raw schematic text.

2. For BOM generation, query the components and group by value:
   ```sql
   SELECT component, count(*) as qty
   FROM main.kicad.schematic_components
   WHERE name = '{project_name}'
   GROUP BY component
   ORDER BY component
   ```

3. For cross-project analysis (e.g., "most popular components"), use
   the `component_frequency` view.

4. When displaying schematics, decode the `image` column as PNG:
   ```python
   from IPython.display import display, Image
   import base64
   row = spark.table("main.kicad.open_schematics") \
       .filter(col("name") == project_name).first()
   display(Image(data=row["image"]))
   ```

5. For structural analysis (nets, connections, hierarchy), parse the
   `json` column which contains libSymbols and net information.

## Examples

**User:** "What components does the Uart-programmer project use?"
**Action:** Query components_used where name LIKE '%Uart-programmer%'

**User:** "What are the 10 most common components across all schematics?"
**Action:** Query component_frequency view with LIMIT 10

**User:** "Show me schematics that use an ATMEGA328P"
**Action:** Filter where array_contains(components_used, 'ATMEGA328P')

**User:** "Generate a BOM for project X"
**Action:** Explode and group components_used for that project
```

### 3.2 Skill: `kicad-rendering`

Teaches Genie how to render KiCad files visually.

**Path:** `Workspace/.assistant/skills/kicad-rendering/`

**SKILL.md:**

```markdown
---
name: kicad-rendering
description: >
  Render KiCad schematic (.kicad_sch) and PCB (.kicad_pcb) files as images
  in notebooks. Use this skill when the user wants to see, display, or
  visualize a schematic or PCB layout.
---

## When to Use

Activate when the user asks to:
- Display or show a schematic
- Render a PCB layout
- Create a gallery of schematics
- Visualize circuit designs

## Instructions

### Option 1: Pre-rendered images (fastest)

For schematics in the Delta table, use the `image` column directly:

```python
from IPython.display import display, Image
row = spark.table("main.kicad.open_schematics") \
    .filter(col("name") == project_name).first()
display(Image(data=row["image"]))
```

### Option 2: kicad-cli rendering (for modified/new schematics)

Requires cluster with kicad-cli init script.
See scripts/render_kicad.py for the rendering functions.

### Option 3: Gallery display

```python
import base64
from IPython.display import display, HTML

rows = spark.table("main.kicad.open_schematics").limit(n).collect()
html = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">'
for row in rows:
    b64 = base64.b64encode(row["image"]).decode()
    html += f'<div style="border:1px solid #ccc;padding:8px;">'
    html += f'<img src="data:image/png;base64,{b64}" style="width:100%;"/>'
    html += f'<p style="font-size:12px;"><b>{row["name"]}</b></p></div>'
html += '</div>'
display(HTML(html))
```
```

### 3.3 Skill: `kicad-component-extraction`

Teaches Genie how to use the Qwen3VL model serving endpoint for component extraction from images.

**Path:** `Workspace/.assistant/skills/kicad-component-extraction/`

**SKILL.md:**

```markdown
---
name: kicad-component-extraction
description: >
  Extract electronic component labels from schematic images using the
  qwen3vl-schematics model serving endpoint. Use this skill when the user
  wants AI-powered component recognition from schematic images, or wants
  to compare ground-truth components with model predictions.
---

## When to Use

Activate when the user asks to:
- Extract components from a schematic image using AI/ML
- Run the vision model on a schematic
- Compare model predictions against ground truth
- Analyze schematic images beyond what metadata provides

## Instructions

Query the model serving endpoint:

```python
import base64
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Get image from Delta table
row = spark.table("main.kicad.open_schematics") \
    .filter(col("name") == project_name).first()

response = w.serving_endpoints.query(
    name="qwen3vl-schematics",
    dataframe_records=[{
        "image": base64.b64encode(row["image"]).decode(),
        "name": row["name"],
        "type": row["type"],
    }],
)
print(response.predictions)
```

## Comparison with Ground Truth

To evaluate extraction quality:

```python
predicted = set(c.strip() for c in response.predictions[0].split(","))
truth = set(row["components_used"])

precision = len(predicted & truth) / len(predicted) if predicted else 0
recall = len(predicted & truth) / len(truth) if truth else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
```
```

---

## 4. Approach B: KiCad MCP Server

### 4.1 Overview

Deploy kicad-tools as an MCP server on a Databricks App, exposing its tools directly to Genie Code as callable functions.

### 4.2 kicad-tools MCP Tools

kicad-tools exposes these tools via MCP when started with `kct mcp serve`:

| Category | Tool | Description |
|----------|------|-------------|
| **Analysis** | `analyze_board` | Summarize board: dimensions, layers, nets, components |
| **Analysis** | `get_drc_violations` | Run Design Rule Check, return violations |
| **Analysis** | `measure_clearance` | Measure clearance between elements |
| **Export** | `export_gerbers` | Generate Gerber manufacturing files |
| **Export** | `export_bom` | Generate Bill of Materials |
| **Export** | `export_assembly` | Generate assembly files for a manufacturer |
| **Placement** | `placement_analyze` | Analyze current component placement quality |
| **Placement** | `placement_suggestions` | Suggest improved component placements |
| **Routing** | `route_net` | Route a specific net |
| **Routing** | `get_unrouted_nets` | List nets that still need routing |
| **Sessions** | `start_session` | Start a board editing session |
| **Sessions** | `query_move` | Preview a component move |
| **Sessions** | `apply_move` | Apply a component move |
| **Sessions** | `commit` | Commit session changes to the board file |
| **Sessions** | `rollback` | Discard session changes |

**Note:** Genie Code has a limit of **20 tools** across all MCP servers. The kicad-tools MCP server exposes 15 tools, leaving room for 5 tools from other servers.

### 4.3 Databricks App: kicad-tools MCP Server

Deploy kicad-tools as a stateless Databricks App that speaks MCP over HTTP.

**`app.yaml`:**

```yaml
command:
  - python
  - app.py
env:
  - name: DATABRICKS_HOST
    valueFrom: "{databricks_host}"
```

**`app.py`:**

```python
"""kicad-tools MCP server as a Databricks App."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import json
import tempfile
import os

app = FastAPI()

# CORS for Databricks workspace
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("DATABRICKS_HOST", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MCP Protocol Implementation ---
# The kicad-tools MCP server can be embedded directly.
# Alternatively, proxy to `kct mcp serve` running as a subprocess.

from kicad_tools.mcp.server import create_mcp_app

mcp_app = create_mcp_app()

# Mount the MCP app at /mcp (required by Databricks)
app.mount("/mcp", mcp_app)
```

**`requirements.txt`:**

```
fastapi
uvicorn
kicad-tools[mcp]
```

### 4.4 Register MCP Server in Genie Code

1. Open Genie Code settings (gear icon)
2. Under **MCP Servers**, click **Add Server**
3. Select **Databricks Apps**
4. Choose the deployed `kicad-tools-mcp` app
5. Click **Save**

Genie will discover all 15 tools and list them in the tool panel. Users can enable/disable individual tools.

### 4.5 Connecting to Delta Table Data

The MCP tools operate on file content. To bridge the Delta table with MCP tools, the skill or Genie workflow must:

1. Read the schematic/PCB content from the Delta table
2. Write it to a temporary file (or pass as string)
3. Call the MCP tool with the file path

This is handled naturally by Genie Code in Agent mode — it can chain SQL queries with MCP tool calls.

**Example conversation flow:**

```
User: "Run a DRC check on the Uart-programmer schematic"

Genie (internally):
  1. SQL: SELECT schematic FROM main.kicad.open_schematics
         WHERE name LIKE '%Uart-programmer%'
  2. Write content to temp file
  3. MCP call: analyze_board(file_path="/tmp/schematic.kicad_sch")
  4. MCP call: get_drc_violations(file_path="/tmp/schematic.kicad_sch")
  5. Format and return results
```

---

## 5. Approach C: Combined Skills + MCP

The most powerful setup combines both mechanisms:

- **Skills** provide domain knowledge, workflow guidance, and teach Genie *when* and *how* to use the MCP tools
- **MCP tools** provide the actual executable operations

### 5.1 Skill: `kicad-tools-guide`

A meta-skill that teaches Genie how to use the kicad-tools MCP tools effectively.

**Path:** `Workspace/.assistant/skills/kicad-tools-guide/`

**SKILL.md:**

```markdown
---
name: kicad-tools-guide
description: >
  Guide for using kicad-tools MCP server tools to analyze, validate, and
  manipulate KiCad schematic and PCB files. Use this skill when the user
  asks about DRC, BOM generation, net tracing, board analysis, component
  placement, routing, or manufacturing export (Gerbers).
---

## When to Use

Activate when the user wants to:
- Run DRC (Design Rule Check) on a PCB
- Generate a BOM (Bill of Materials)
- Analyze board dimensions, layers, or nets
- Check manufacturing clearances
- Export Gerber files for fabrication
- Optimize component placement
- Route or check unrouted nets
- Perform interactive board editing sessions

## Available MCP Tools

You have access to these tools from the kicad-tools MCP server:

### Analysis Tools
- `analyze_board`: Get board summary (dimensions, layers, nets, components)
- `get_drc_violations`: Run DRC with optional manufacturer rules
- `measure_clearance`: Check clearance between specific elements

### Export Tools
- `export_bom`: Generate BOM in CSV or JSON format
- `export_gerbers`: Generate Gerber manufacturing files
- `export_assembly`: Generate pick-and-place + assembly drawings

### Placement & Routing Tools
- `placement_analyze`: Score current placement quality
- `placement_suggestions`: Get AI-suggested placement improvements
- `route_net`: Route a specific net
- `get_unrouted_nets`: List nets still needing routes

### Session Tools (for multi-step editing)
- `start_session`: Begin an editing session on a board
- `query_move`: Preview what a component move would look like
- `apply_move`: Execute the move
- `commit`: Save all session changes
- `rollback`: Discard session changes

## Workflow: Analyzing a Schematic from the Delta Table

1. Query the schematic content from `main.kicad.open_schematics`
2. Save to a temporary file
3. Call the appropriate MCP tool
4. Present results to the user

```python
# Step 1: Get schematic from Delta
row = spark.sql("""
    SELECT schematic, name
    FROM main.kicad.open_schematics
    WHERE name LIKE '%{project}%'
    LIMIT 1
""").first()

# Step 2: Write to temp file
import tempfile, os
with tempfile.NamedTemporaryFile(suffix=".kicad_sch", delete=False, mode="w") as f:
    f.write(row["schematic"])
    temp_path = f.name

# Step 3: Call MCP tool (Genie handles this via the MCP server)
# The tool call is: analyze_board(file_path=temp_path)
```

## Workflow: DRC with Manufacturer Rules

When the user asks to check manufacturing constraints:
1. Ask which manufacturer (default to JLCPCB)
2. Call `get_drc_violations` with the manufacturer parameter
3. Summarize violations by severity
4. Suggest fixes for common issues

## Workflow: Interactive Board Editing

For multi-step PCB modifications:
1. `start_session` on the board file
2. Use `query_move` to preview changes (non-destructive)
3. Use `apply_move` to execute approved changes
4. `commit` when satisfied, or `rollback` to discard

Always preview with `query_move` before applying.

## Best Practices

- Always call `analyze_board` first to understand the board before other operations
- For DRC, specify the target manufacturer to get relevant rules
- Use sessions for any multi-step editing — never modify files directly
- Present DRC violations grouped by severity (error > warning > info)
- When exporting Gerbers, confirm the manufacturer with the user first
```

### 5.2 Complete Skill + MCP Setup

```
Workspace/.assistant/skills/
├── kicad-schematic-analysis/      # Skill: Delta table queries & analytics
│   ├── SKILL.md
│   └── scripts/
│       └── analyze_schematic.py
├── kicad-rendering/               # Skill: Display schematics in notebooks
│   ├── SKILL.md
│   └── scripts/
│       └── render_kicad.py
├── kicad-component-extraction/    # Skill: Qwen3VL model serving
│   └── SKILL.md
└── kicad-tools-guide/             # Skill: MCP tool usage guidance
    └── SKILL.md

MCP Servers:
└── kicad-tools-mcp (Databricks App)   # 15 tools for board analysis/manipulation
```

---

## 6. kicad-tools Capabilities Reference

### 6.1 Python API (for use in skill scripts)

```python
from kicad_tools import load_schematic, Schematic, Project
from kicad_tools.schema.pcb import PCB
from kicad_tools.validate import DRCChecker
from kicad_tools.router import Autorouter, DesignRules
from kicad_tools.optim import PlacementOptimizer
from kicad_tools.library import create_soic, create_qfp, SymbolLibrary
```

### 6.2 Schematic Operations

```python
doc = load_schematic("project.kicad_sch")
sch = Schematic(doc)

# List components
for symbol in sch.symbols:
    print(f"{symbol.reference}: {symbol.value} ({symbol.footprint})")

# List sheets (hierarchical schematics)
for sheet in sch.sheets:
    print(f"Sheet: {sheet.name}")
```

### 6.3 PCB Operations

```python
pcb = PCB.load("board.kicad_pcb")

# DRC with manufacturer rules
checker = DRCChecker(pcb, manufacturer="jlcpcb")
results = checker.check_all()
for v in results:
    print(f"{v.rule_id}: {v.message}")

# Placement optimization
optimizer = PlacementOptimizer.from_pcb(pcb)
optimizer.run(iterations=1000, dt=0.01)

# Autorouting
rules = DesignRules(grid_resolution=0.25, trace_width=0.2, clearance=0.15)
router = Autorouter(width=100, height=80, rules=rules)
result = router.route_all()
```

### 6.4 PCBReasoningAgent (LLM-driven layout)

```python
from kicad_tools import PCBReasoningAgent
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
agent = PCBReasoningAgent.from_pcb("board.kicad_pcb")

while not agent.is_complete():
    prompt = agent.get_prompt()
    response = w.serving_endpoints.query(
        name="databricks-claude-sonnet",
        messages=[{"role": "user", "content": prompt}],
    )
    command = response.choices[0].message.content
    result, diagnosis = agent.execute(command)

agent.save("board_optimized.kicad_pcb")
```

### 6.5 CLI Reference

| Command | Description | Key flags |
|---------|-------------|-----------|
| `kct symbols <file>` | List schematic symbols | `--format json` |
| `kct nets <file>` | List/trace nets | `--net <name>` |
| `kct bom <file>` | Generate BOM | `--format csv`, `--group` |
| `kct erc <file>` | Electrical Rules Check | `--strict` |
| `kct drc <file>` | Design Rules Check | `--mfr jlcpcb`, `--format json` |
| `kct check <file>` | Quick clearance/trace check | `--clearance 0.15`, `--trace-width 0.2` |
| `kct reason <file>` | LLM-driven PCB reasoning | `--interactive`, `--auto-route` |
| `kct mcp serve` | Start MCP server | |
| `kct calibrate` | GPU status | `--show-gpu` |

All commands support `--format json` for machine-parseable output.

---

## 7. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Databricks Workspace                            │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Genie Code (Agent Mode)                     │ │
│  │                                                                │ │
│  │  Skills loaded contextually:          MCP tools available:     │ │
│  │  ┌─────────────────────────┐    ┌──────────────────────────┐  │ │
│  │  │ kicad-schematic-analysis│    │ kicad-tools MCP Server   │  │ │
│  │  │ kicad-rendering         │    │ (Databricks App)         │  │ │
│  │  │ kicad-component-extract │    │                          │  │ │
│  │  │ kicad-tools-guide       │    │ • analyze_board          │  │ │
│  │  └────────────┬────────────┘    │ • get_drc_violations     │  │ │
│  │               │                 │ • export_bom             │  │ │
│  │               │                 │ • route_net              │  │ │
│  │               ▼                 │ • placement_suggestions  │  │ │
│  │  ┌─────────────────────────┐    │ • ... (15 tools total)   │  │ │
│  │  │ Genie generates code    │    └────────────┬─────────────┘  │ │
│  │  │ informed by skills,     │                 │                │ │
│  │  │ calls MCP tools,        │◄────────────────┘                │ │
│  │  │ queries Delta tables    │                                  │ │
│  │  └────────────┬────────────┘                                  │ │
│  └───────────────┼───────────────────────────────────────────────┘ │
│                  │                                                  │
│                  ▼                                                  │
│  ┌──────────────────────────────┐  ┌─────────────────────────────┐ │
│  │       Unity Catalog          │  │     Model Serving           │ │
│  │  main.kicad.open_schematics  │  │  qwen3vl-schematics        │ │
│  │  main.kicad.schematic_comps  │  │  (component extraction)    │ │
│  │  main.kicad.component_freq   │  └─────────────────────────────┘ │
│  └──────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Implementation Plan

### Phase 1: Skills Only (no infrastructure needed)

Deploy the four skills to the workspace. This requires no apps, no MCP servers — just markdown files in the workspace filesystem.

| Task | Effort |
|------|--------|
| Create `kicad-schematic-analysis` skill | Small |
| Create `kicad-rendering` skill | Small |
| Create `kicad-component-extraction` skill | Small |
| Test in Genie Code Agent mode | Small |

**Outcome:** Genie can query the Delta table, display schematics, and call the model serving endpoint — guided by skill instructions.

### Phase 2: MCP Server Deployment

Deploy kicad-tools as a Databricks App MCP server and add the `kicad-tools-guide` skill.

| Task | Effort |
|------|--------|
| Package kicad-tools as a Databricks App | Medium |
| Implement MCP HTTP transport (FastAPI wrapper) | Medium |
| Deploy and test MCP server | Small |
| Register MCP server in Genie Code | Small |
| Create `kicad-tools-guide` skill | Small |
| End-to-end testing (DRC, BOM, analysis flows) | Medium |

**Outcome:** Genie can call kicad-tools operations as structured tool calls — analyze boards, run DRC, generate BOMs, and perform interactive editing sessions.

### Phase 3: Advanced Workflows

| Task | Effort |
|------|--------|
| PCBReasoningAgent integration via notebook skill | Large |
| Multi-step board editing workflow with sessions | Medium |
| Gerber export + upload to UC Volumes | Small |
| Placement optimization skill | Medium |

**Outcome:** Full agentic PCB design workflows in Genie Code — from schematic analysis through to manufacturing export.