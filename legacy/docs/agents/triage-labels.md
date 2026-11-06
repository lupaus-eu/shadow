# Triage Labels

| Local status | Use | Meaning | Allowed next state |
| --- | --- | --- | --- |
| `needs-triage` | PRD, domain model, technical design, ticket | Work has not yet been evaluated or bounded. | PRD/domain model/technical design: `needs-info`, `ready-for-human`, `wontfix`; ticket: the same or `ready-for-agent` |
| `needs-info` | PRD, domain model, technical design, ticket | Work awaits a user or maintainer decision. | PRD/domain model/technical design: `ready-for-human`, `accepted`, `wontfix`; ticket: `ready-for-human`, `ready-for-agent`, `wontfix` |
| `ready-for-human` | PRD, domain model, technical design, ticket | The next necessary action is human approval, a business decision, or an environment action. | PRD/domain model/technical design: `accepted`, `wontfix`; ticket: `ready-for-agent`, `wontfix` |
| `accepted` | PRD, domain model, technical design | The user has accepted the artefact; an accepted PRD may lead to domain modeling or technical design, and an accepted design may lead to tickets. | `needs-info` only for a material new decision |
| `ready-for-agent` | Ticket | Scope, acceptance criteria, and blockers are clear enough to implement. | `claimed`, `needs-info`, `ready-for-human` |
| `claimed` | Ticket | An agent is implementing the ticket. | `implemented`, `resolved`, `needs-info`, `ready-for-human` |
| `implemented` | Ticket | Implementation, applicable checks, and documentation effects are complete and recorded. | `ready-for-human` only when a separate human confirmation is needed |
| `resolved` | Ticket | An investigation, decision, wayfinding, or documentation ticket has been answered without product implementation. | `ready-for-human` only when a separate human confirmation is needed |
| `wontfix` | PRD, domain model, technical design, ticket | Work will not be implemented. | None |

PRDs, optional domain models, and technical designs end at `accepted` with
user approval. Only tickets are claimed, implemented, or resolved.
`implemented` does not mean that the whole feature is complete: the feature is
complete only when all tickets are `implemented` or `resolved` and the PRD's
documentation effects are complete.
