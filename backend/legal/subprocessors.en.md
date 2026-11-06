---
title: Sub-processors
version: 1
effective_from: 2026-12-01
status: draft
acceptance: notice
---
> **Draft for legal review.** Prepared by the product team from the repository's documentation. It is not legal advice and has not been reviewed by a lawyer. `TODO(lawyer)` marks what is unknown or needs legal wording. Nothing here is in force.

Yearclock uses the parties below to provide the service. Where Yearclock is the processor of your planning content, they are sub-processors under the data processing agreement.

| Party | Purpose | Data | Location and transfer basis |
| --- | --- | --- | --- |
| UpCloud | Hosting of the application, the databases, and the identity provider. | All data in the service. | `TODO(lawyer)` data centre location, agreement, and transfer basis (not stated in the repository). |
| Stripe | Subscription billing and payment. | Billing name and email, address, tax identifiers, payment method, invoices. Yearclock stores no card details. | `TODO(lawyer)` Stripe entity, location, and transfer basis. |
| Scaleway (Transactional Email) | Sending Yearclock and sign-in emails. | Recipient address and message content (never Event content, except the opt-in Summary of upcoming Events, which lists Event titles). | `TODO(lawyer)` region (the example configuration names `fr-par`, confirm the real one). |
| Scaleway (Object Storage) | Encrypted off-host backups of the databases. | The databases, encrypted before upload with a key only the operator holds. | `TODO(lawyer)` region, and the project of its own for backups. |

Not sub-processors: the identity provider (Authentik) is operated by Yearclock on its own host; the container registry (GitHub Container Registry) receives software images and no personal data; an AI agent that a person connects is that person's own choice (see the privacy notice).

## Changes to this list

`TODO(lawyer)` confirm the process. The intended process: Owners are told by email and in the app at least 30 days before a sub-processor is added or replaced; an Owner may object in that time by writing to the legal contact, and the parties then try to resolve it. What follows an unresolved objection is for the terms to say.
