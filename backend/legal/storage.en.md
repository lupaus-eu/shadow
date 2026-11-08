---
title: Browser storage notice
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Draft for legal review.** Prepared by the product team from the repository's documentation. It is not legal advice and has not been reviewed by a lawyer. `TODO(lawyer)` marks what is unknown or needs legal wording. Nothing here is in force.

Shadow stores only what it needs to run the service and what you choose yourself. It uses no analytics, advertising, or tracking storage, so it shows no consent banner. `TODO(lawyer)` confirm that this fits section 205 of the Finnish Act on Electronic Communications Services and the Data Protection Ombudsman's current guidance.

This list is kept equal to the code by automated tests (`backend/legal/browser-storage.json`).

## Cookies

| Name | Purpose | Lifetime |
| --- | --- | --- |
| `shadow_session` | Keeps you signed in (an opaque session identifier). | Up to 8 hours; removed when you sign out. |
| `shadow_oidc_flow` | Protects the sign-in round trip against forgery. | 10 minutes; removed when sign-in completes. |

## Settings kept in your browser

| Key | Purpose | Lifetime |
| --- | --- | --- |
| `shadow.locale` | Remembers your language. | Until you clear site data. |
| `shadow.canvas.panels` | Remembers which canvas panels you collapsed. | Until you clear site data. |
| `shadow.canvas.typeCollapse` | Remembers which node type groups of the canvas list you collapsed. | Until you clear site data. |
| `shadow.had-session` (session storage) | Lets the sign-in page say that your session ended. | Until you close the tab. |
| `shadow.signed-out` (session storage) | Lets the sign-in page confirm your sign-out once. | Removed after one use. |

## Sign-in pages

Sign-in runs on the identity provider's own address, which sets its own session and forgery-protection cookies there (`TODO(lawyer)` confirm the names and lifetimes against the running version).
