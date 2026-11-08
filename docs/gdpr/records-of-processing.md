# Records of processing (GDPR Article 30)

Owner: Platform Operator (the named person is `TODO(operator)`)  
Review by: 2027-05-05, then every six months and after any change to the data the product keeps  
Status: draft for counsel. An engineering record, not legal advice. It holds no personal data and no incident details.

The inventory of what is processed is in [README.md](README.md); this record arranges it as Article 30 requires.
`TODO(lawyer)` confirm the form. The small-business exemption does not help because the processing is not occasional.

## As controller (Article 30(1))

| Item | Entry |
| --- | --- |
| Controller | The Platform Operator, named on the provider information page `TODO(operator)` |
| Contact and data protection officer | The legal contact (`LEGAL_CONTACT_EMAIL`); no officer (see [dpia-and-dpo-note.md](dpia-and-dpo-note.md)) |
| Purposes | Identifying and signing in people; authorization; invitations; audit and security; notifications and the opt-in Summary; billing identity; proof of acceptance of legal documents; support |
| Categories of data subjects | Members and invitees of customer Organizations; billing contacts; Platform staff |
| Categories of data | Account identity (issuer, subject, email, display name, language); sessions; membership, roles, Groups, recent Yearclocks; invitation address and role; billing name and email; audit entries; agent call records (person, agent program, tool, outcome; no content; successful reads deleted after 90 days); notifications and settings; queued email; acceptance records (with an e-mail snapshot) |
| Recipients | Sub-processors (hosting, email, billing, backups) as listed on the sub-processors page; none else |
| Transfers outside the EU and EEA | `TODO(lawyer)` per sub-processor; none are known from the repository |
| Retention | [Retention and deletion in README.md](README.md#retention-and-deletion) |
| Security measures | The security page (`backend/legal/security.en.md`) and [`docs/architecture/security-review.md`](../architecture/security-review.md) |

## As processor (Article 30(2))

| Item | Entry |
| --- | --- |
| Processor and contact | As above |
| Controllers on whose behalf | Each customer Organization |
| Categories of processing | Storing, displaying, exporting, and deleting the planning content a customer's people enter; agent access (MCP) at the person's own request |
| Transfers outside the EU and EEA | `TODO(lawyer)` as above |
| Security measures | As above |
| Sub-processors | Hetzner (hosting), Stripe (billing, as a separate controller or processor `TODO(lawyer)`), Scaleway (email and encrypted backups) |
