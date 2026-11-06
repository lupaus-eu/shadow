---
title: Switching and data return
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Draft for legal review.** Prepared by the product team from the repository's documentation. It is not legal advice and has not been reviewed by a lawyer. `TODO(lawyer)` marks what is unknown or needs legal wording. Nothing here is in force.

You can take your data out at any time and move to another provider. This page describes how. `TODO(lawyer)` align it with the switching terms the EU Data Act requires for cloud services (maximum notice period, transition period, charges, and the information duties) before it is published.

## What you can export

| What | Who | Format |
| --- | --- | --- |
| **Organization Export**: all content of an Organization plus its members' names, emails, and roles | Owners | JSON file (it cannot be imported back) |
| **Export and import of all your data**: Shadows, Lanes, Categories, Labels, Events, and recurring Series of every Organization you administer | Owners and Admins | One CSV file (`shadow-data/1`), which the same page can import again; people, access rights, deleted Events, history, and billing data are left out |
| **Events to a spreadsheet** | Anyone who may read a Shadow | Excel or CSV, for one Shadow |
| Print or image of a Shadow | Anyone who may read it | Print layout or image file |

Exports are recorded in the Audit Log by count and format, never by content.

## When your subscription ends

When a subscription is cancelled it ends at the end of the paid period. After that the Organization is read-only: nothing is deleted, the Organization Export still works, and an Owner can subscribe again. If an Owner deletes the Organization, it can be restored for 30 days; after that its content is purged and cannot be recovered. A backup copy may remain for the backup retention period (24 hourly, 30 daily, and 6 monthly snapshots).

## Notice, transition, and charges

`TODO(lawyer)` the notice period for switching, the transition period, whether and how switching charges apply, and how a request to switch is made and answered.
