# LikeC4 Models

ADR-015 hyväksyy LikeC4:n AI via MCP -ominaisuuden C4-mallin työkaluksi.
Muut diagrammit pysyvät PlantUML:nä (`docs/architecture/diagrams/README.md`).

LikeC4 is not a project dependency. It runs through `npx`, pinned to
`likec4@1.60.0`.

---

# Models

```text
docs/architecture/diagrams/likec4/
└── shadow-ai-mcp/
    ├── specification.c4   element kinds, deployment node kinds, tags
    ├── model.c4           people, systems, containers, components, relations
    ├── deployment.c4      production and development environments
    └── views.c4           all views
```

Views of `shadow-ai-mcp` and their committed exports:

| View | Type | Export |
| --- | --- | --- |
| `index` | C4 L1 system context | `docs/architecture/diagrams/generated/likec4-index.png` |
| `shadowContainers` | C4 L2 containers | `docs/architecture/diagrams/generated/likec4-shadowContainers.png` |
| `backendComponents` | C4 L3 backend components | `docs/architecture/diagrams/generated/likec4-backendComponents.png` |
| `productionMcp` | Deployment, production | `docs/architecture/diagrams/generated/likec4-productionMcp.png` |
| `developmentMcp` | Deployment, development | `docs/architecture/diagrams/generated/likec4-developmentMcp.png` |
| `connectFlow` | Dynamic: connect an AI client | `docs/architecture/diagrams/generated/likec4-connectFlow.png` |
| `generateFlow` | Dynamic: generate and apply a change set | `docs/architecture/diagrams/generated/likec4-generateFlow.png` |
| `reviewInChatFlow` | Dynamic: apply a change set from the AI client (TASK-069O) | `docs/architecture/diagrams/generated/likec4-reviewInChatFlow.png` |

Elements are tagged `#new` (accepted, not implemented yet) or `#existing`
(implemented). TASK-069P retagged every ADR-015 element `#existing`, so no
element is `#new` now; a future `#new` element is styled green in its own
definition until its task retags it.

Deployment views in `likec4@1.60.0` ignore `include ... with { title }`, so a
merged deployment edge would show `[...]`. Such edges get one labelled
deployment relation tagged `#edgeLabel` in `deployment.c4`, and the deployment
view excludes the other relations between those instances
(`where not tag is #edgeLabel`).

---

# Commands

Run from the repository root.

One-time setup for PNG export (headless Chromium for LikeC4's bundled
Playwright):

```bash
npx -y likec4@1.60.0 --version
npx -y -p likec4@1.60.0 playwright install --only-shell chromium
```

Validate the model:

```bash
npx -y likec4@1.60.0 validate docs/architecture/diagrams/likec4/shadow-ai-mcp
```

Export every view as `docs/architecture/diagrams/generated/likec4-<view>.png`. LikeC4 names
exports `<view>.png`, so export to a temporary directory and add the prefix.
`--description` renders each view's title and description (implementation
and production status) above the diagram, so embedded PNGs carry that
context:

```bash
OUT=$(mktemp -d)
npx -y likec4@1.60.0 export png --flat --description -o "$OUT" docs/architecture/diagrams/likec4/shadow-ai-mcp
for f in "$OUT"/*.png; do cp "$f" "docs/architecture/diagrams/generated/likec4-$(basename "$f")"; done
```

Browse the views interactively:

```bash
npx -y likec4@1.60.0 start docs/architecture/diagrams/likec4/shadow-ai-mcp
```

---

# Rules

- Edit the `.c4` sources; never edit the exported PNGs by hand.
- After changing a source, run `validate`, re-export every view and commit the
  sources and PNGs together.
- Keep the model in sync with ADR-015, `docs/architecture/domains/AI.md` and
  `docs/architecture/overview.md`. When a TASK-069 implementation differs from the model,
  update the model in that task.
- When a `#new` element is implemented, its task retags it `#existing`
  (TASK-069P did so for the whole ADR-015 model).
