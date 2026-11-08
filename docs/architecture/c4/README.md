# C4 model (LikeC4)

The Shadow architecture as a [LikeC4](https://likec4.dev) model, following
the C4 levels.

| File | Contents |
| --- | --- |
| `specification.c4` | Element kinds (person, software system, external system, container, SPA, database, component), tags, and deployment node kinds |
| `model.c4` | People, the Shadow and Authentik systems with their containers and components, external systems, and all relationships |
| `deployment.c4` | The local Docker Compose stack and the production Compose host |
| `views.c4` | The views listed below |

## Views

| Level | View | Shows |
| --- | --- | --- |
| 1 · System context | `index` | Owners and Admins, Members, Platform Operators, Shadow, Authentik, Stripe, Scaleway, AI agents |
| 2 · Containers | `containers` | Edge proxy, web application, API, background worker, migration job, Shadow database, and the systems around them |
| 2 · Containers | `identity` | Authentik's server, worker, and database next to Shadow |
| 3 · Components | `webAppComponents` | Sign-in shell, Organization workspace, Model workspace, operator console, API clients, localization |
| 3 · Components | `apiComponents` | Authentication, Organizations, billing, the access rule, models and versions, metrics, forecasts and simulations, analysis, import and export, MCP, Support Access, audit, persistence |
| 3 · Components | `workerComponents` | Scheduler, job runner, email delivery |
| Dynamic | `signIn`, `invitation`, `billingWebhook`, `canvasEdit`, `agentAnalysis` | Key flows step by step |
| Deployment | `localDeployment`, `productionDeployment` | Where each container runs |

C4 level 4 (code) is not modelled. The source and the database model
([`../dbml/`](../dbml/README.md)) cover it.

## Working with the model

- `make c4` serves the views at <http://localhost:8176>, with the port
  recorded in [`../docker.md`](../docker.md).
- `make models` validates the model and the DBML schema.
- Both commands use the pinned CLI `npx likec4@1.59.4`, which needs Node 22
  or later.
- Update the model in the same change whenever a change adds or removes a
  container, an external integration, a major API component, or a
  relationship between them. The component technology lines name the
  modules, so renames show up in review.
- The model follows [`../stack.md`](../stack.md), [`../docker.md`](../docker.md),
  [`../workers.md`](../workers.md), and the ADRs. When they disagree, fix the
  model.
