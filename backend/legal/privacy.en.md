---
title: Privacy notice
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Draft for legal review.** Prepared by the product team from the repository's documentation. It is not legal advice and has not been reviewed by a lawyer. `TODO(lawyer)` marks what is unknown or needs legal wording. Nothing here is in force.

This notice tells the people who use Shadow which personal data Shadow itself controls and why. For the planning content that a customer enters, Shadow acts for the customer as processor (see the data processing agreement), and the customer informs its own people.

## Who is responsible
The controller is the provider named on the provider information page. Contact for privacy matters: `TODO(lawyer)` the legal contact address. `TODO(lawyer)` whether a data protection officer is required (the product team's screening note concludes none is needed unless counsel disagrees).

## What we process, why, and for how long

| Data | Why | How long |
| --- | --- | --- |
| Identity from the sign-in provider (issuer, subject, email, display name, language) | To identify you and show your name to your colleagues | While you have an account `TODO(lawyer)` |
| Session and login state (a hashed token, expiry, the identity token until sign-out) | To keep you signed in securely | The session lifetime (8 hours by default); login state 10 minutes |
| Membership and role in an Organization, Groups, and recently opened Shadows | To control access and show you your recent Shadows and what changed since your last visit | Until the membership, Group, Shadow, or Organization is removed |
| Invitations (email address and role) | To invite you | Seven days, then they expire |
| Billing name and billing email of an Organization | To invoice the customer through Stripe | While the Organization exists, and as a billing record after it is purged `TODO(lawyer)` accounting-law period |
| Audit log (who did what, when; a minimal change summary) | Accountability and security | `TODO(lawyer)` period; summaries are emptied when the Organization is purged |
| Notifications, notification settings, and the opt-in Summary of upcoming Events | To tell you about changes to your own access and role, and, if you turn it on, to email you upcoming Events (this email lists Event titles) | Notifications 90 days |
| Queued email (recipient, subject, text) | Reliable delivery | `TODO(lawyer)` period (not defined yet) |
| Acceptance records (who accepted which legal document version, when) | To prove what was agreed | Kept as contract evidence `TODO(lawyer)` period |

Shadow stores no passwords, passkeys, MFA secrets, or payment card details. It does not use analytics or advertising and does not sell personal data.

`TODO(lawyer)` the legal basis for each purpose (contract, legitimate interest, legal obligation) in the form the law requires.

## Who receives data
The sub-processors listed on the sub-processors page (hosting, email, billing, backups) receive data only to provide the service. Platform staff can see an Organization only through Support Access that its Owners approve. If you connect an AI agent to Shadow, that agent's provider is your own choice and processes what the agent reads; Shadow stores no agent conversations.

## Transfers outside the EU and EEA
`TODO(lawyer)` list any transfer and its safeguard (see the sub-processors page).

## Your rights
You may ask for access to, correction of, or erasure of your data, restriction or objection to processing, and portability, and you may complain to the Data Protection Ombudsman (tietosuojavaltuutettu). Write to the legal contact. If your data is planning content in a customer's Organization, we pass your request to that customer.
