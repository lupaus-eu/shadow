# Yearclock V1 acceptance trace

This matrix traces every numbered user story in the
[Yearclock V1 PRD](../../.scratch/yearclock-v1/PRD.md) to executable evidence,
supporting ticket 23's criterion that all PRD behavior is either demonstrated
or explicitly traced to an approved out-of-scope statement. Each row has one of
five statuses. **Demonstrated** means a committed test exercises the behavior.
**Partial** means some of the behavior is covered and the row says what is
missing. **Out of scope / decided** cites the PRD statement, ADR, or recorded
product decision that removes the story. **Needs human** means acceptance
depends on production accounts, the production environment, legal review, or
manual assistive-technology review. **Gap** means nothing covers the story and
no decision removes it. Evidence paths are abbreviated: `B:` is
`backend/tests/`, `E:` is `frontend/tests/browser/`, and `U:` is
`frontend/tests/unit/`. Every cited test name was checked against the source.
Backend tests run against real PostgreSQL through the HTTP API, with fake Stripe,
OIDC, and email adapters that follow the provider contracts. Browser specs
replace the API with `route.fulfill` stubs, so they show UI behavior only. A
story is marked Demonstrated only when the server-side rule is also covered by
a backend test or the story is purely about the UI. The trace was taken on
2026-09-23 at HEAD `a7479f4`. Rows 39, 52, 104, and T6 were then updated
with the ticket 23 tests (authorization matrix, operational limits, security
review, and i18n parity), committed with this file.
The Partial items were then closed with `backend/tests/test_acceptance_coverage.py`,
`backend/tests/test_recurrence_properties.py`, and
`frontend/tests/browser/acceptance-coverage.spec.ts`.

## Summary

| Status | User stories (121) | Testing decisions (12) |
| --- | ---: | ---: |
| Demonstrated | 112 | 11 |
| Partial | 0 | 1 |
| Out of scope / decided | 2 | 0 |
| Needs human | 7 | 0 |
| Gap | 0 | 0 |

## User stories

| # | Story (short) | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Visitor creates a customer User Account | Needs human | Registration happens in Authentik. Yearclock side: B:test_authentication.py::test_oidc_callback_creates_a_customer_profile_and_session. Real Authentik smoke test is pending (ticket 22, `production-readiness.md` §2). |
| 2 | Verify email address | Needs human | Yearclock refuses unverified email: B:test_authentication.py::test_profile_linkage_uses_issuer_and_subject_and_requires_verified_email. The Authentik verification flow is not smoke-tested (ticket 22). |
| 3 | Sign in with a passkey | Needs human | Authentik policy (ADR-0004, ADR-0010). Documented in `production-readiness.md` §2. Ticket 22 smoke test is unchecked. |
| 4 | Password sign-in requires a second factor | Needs human | Authentik MFA policy (ADR-0004). Ticket 22 smoke test is unchecked. |
| 5 | Authentik-managed recovery | Needs human | Authentik recovery email (ADR-0010). Ticket 22 smoke test is unchecked. |
| 6 | Every customer and platform view requires authentication | Demonstrated | B:test_acceptance_coverage.py::test_every_route_requires_a_session_except_the_guarded_public_ones sweeps all 74 session routes (401) and names the six public routes with their own guards; E:authentication.spec.ts and E:platform-console.spec.ts show the sign-in entry points. |
| 7 | One User Account in several Organizations | Demonstrated | B:test_organization_context.py::test_customer_lists_and_opens_only_their_organizations |
| 8 | Platform staff use a separate customer account | Demonstrated | B:test_authentication.py::test_platform_identity_cannot_enter_the_customer_account_class; B:test_platform_operations.py::test_enrolled_staff_sign_in_to_the_console_and_never_reach_customer_routes, ::test_unenrolled_and_customer_identities_cannot_open_the_console |
| 9 | Single Organization opens directly | Demonstrated | E:organization-context.spec.ts::"a customer with one membership enters it directly" |
| 10 | Organization selector for several Organizations | Demonstrated | E:organization-context.spec.ts::"a customer selects between organizations and tabs keep explicit context" |
| 11 | Organization identity in route and UI | Demonstrated | Same browser test (per-tab URLs); B:test_organization_context.py::test_customer_lists_and_opens_only_their_organizations (mismatched route 404) |
| 12 | Signup collects name, IANA zone, locale, billing, seats | Demonstrated | E:organization-activation.spec.ts::"customer purchases seats and sees activation only after Stripe payment"; B:test_organization_activation.py::test_authenticated_customer_starts_a_pending_subscription_checkout, ::test_signup_validates_seat_count_and_iana_time_zone |
| 13 | Hosted Stripe Checkout | Demonstrated | B:test_stripe_billing.py::test_subscription_checkout_uses_the_configured_monthly_seat_price; E:organization-activation.spec.ts (same test). Real test-mode verification is ticket 22. |
| 14 | EUR 30 per seat shown before tax, tax shown clearly | Demonstrated | E:organization-activation.spec.ts asserts "3 × €30.00 per seat = €90.00 per month before tax, billed in advance" and that tax is shown separately. Real Stripe tax rendering stays in the production checklist (ticket 22). |
| 15 | First month charged in advance | Demonstrated | B:test_stripe_billing.py::test_subscription_checkout_uses_the_configured_monthly_seat_price (`mode=subscription`); E:organization-activation.spec.ts ("billed in advance") |
| 16 | Activation only on a verified Stripe event | Demonstrated | B:test_organization_activation.py::test_verified_paid_event_activates_once_and_creates_localized_content, ::test_stripe_signature_verification_rejects_tampering |
| 17 | Abandoned Checkout grants no access | Demonstrated | B:test_organization_activation.py::test_unpaid_or_abandoned_checkout_never_grants_access |
| 18 | Blank Yearclock with one General Lane | Demonstrated | B:test_organization_activation.py::test_verified_paid_event_activates_once_and_creates_localized_content; B:test_organization_context.py::test_customer_lists_and_opens_only_their_organizations |
| 19 | Each Organization billed independently | Demonstrated | B:test_acceptance_coverage.py::test_billing_state_of_one_organization_never_touches_another (a failed renewal in one Organization leaves the other active with its own seats); B:test_organization_context.py::test_customer_lists_and_opens_only_their_organizations. |
| 20 | See purchased, occupied, reserved, available seats | Demonstrated | B:test_seat_capacity.py::test_owner_previews_and_confirms_payment_gated_seat_increase; E:seat-capacity.spec.ts::"an Owner previews and confirms a payment-gated seat increase" |
| 21 | Preview and confirm a prorated increase | Demonstrated | Same two tests; B:test_stripe_billing.py::test_seat_increase_uses_matching_preview_and_payment_gated_update |
| 22 | Added capacity usable only after payment | Demonstrated | B:test_seat_capacity.py::test_owner_previews_and_confirms_payment_gated_seat_increase |
| 23 | Seat reduction scheduled for renewal | Demonstrated | B:test_seat_capacity.py::test_decrease_is_scheduled_at_renewal_and_respects_used_capacity; B:test_stripe_billing.py::test_seat_decrease_uses_a_non_prorated_renewal_schedule |
| 24 | Reduction blocked below active plus reserved | Demonstrated | B:test_seat_capacity.py::test_decrease_is_scheduled_at_renewal_and_respects_used_capacity |
| 25 | Stripe Customer Portal for payment details and invoices | Demonstrated | B:test_subscription_lifecycle.py::test_only_owners_open_the_customer_portal, ::test_grace_read_only_and_recovery_follow_verified_payment_events; E:subscription-states.spec.ts::"an Owner opens the billing portal, also while read-only". Portal configuration (quantity disabled) is verified in ticket 22. |
| 26 | Cancel and keep access until period end | Demonstrated | B:test_subscription_lifecycle.py::test_cancellation_is_scheduled_reversible_and_never_deletes_content; E:subscription-states.spec.ts::"a scheduled cancellation states when the subscription ends" |
| 27 | Reverse a scheduled cancellation | Demonstrated | B:test_subscription_lifecycle.py::test_cancellation_is_scheduled_reversible_and_never_deletes_content |
| 28 | Cancellation leaves content intact | Demonstrated | Same test (titles retained after `subscription.deleted`) |
| 29 | Seven-day grace with warning after failed renewal | Demonstrated | B:test_subscription_lifecycle.py::test_grace_read_only_and_recovery_follow_verified_payment_events; B:test_subscription_access.py::test_failed_renewal_has_seven_day_grace_then_read_only; E:subscription-states.spec.ts::"a failed renewal shows the grace deadline while editing continues" |
| 30 | Read-only, not hidden, after grace | Demonstrated | Same backend tests; B:test_recoverable_deletion.py::test_read_only_state_blocks_deletion_and_restoration_but_not_viewing; E:subscription-states.spec.ts::"a read-only Organization keeps content visible and hides editing" |
| 31 | Successful payment restores access | Demonstrated | B:test_subscription_lifecycle.py::test_grace_read_only_and_recovery_follow_verified_payment_events |
| 32 | Activator becomes first Owner | Demonstrated | B:test_organization_activation.py::test_verified_paid_event_activates_once_and_creates_localized_content; E:organization-activation.spec.ts ("Owner seat: active") |
| 33 | Owner invites another Owner | Demonstrated | B:test_memberships.py::test_only_owners_can_grant_or_change_ownership |
| 34 | Always at least one accepted Owner | Demonstrated | B:test_memberships.py::test_last_owner_cannot_leave_or_be_removed, ::test_admin_manages_other_admins_but_not_owners; E:people-panel.spec.ts::"an Owner changes a role and removes a member, and the final Owner is protected" |
| 35 | Ownership only after acceptance | Demonstrated | B:test_memberships.py::test_only_owners_can_grant_or_change_ownership; B:test_invitations.py::test_invitation_reserves_capacity_and_authenticated_acceptance_converts_it |
| 36 | Consultant hands over by adding Owners and stepping back | Demonstrated | B:test_memberships.py::test_only_owners_can_grant_or_change_ownership (the new Owner demotes the original Owner); ::test_member_cannot_list_change_or_remove_memberships_but_can_leave |
| 37 | Owner has complete authority | Demonstrated | B:test_seat_capacity.py (both tests); B:test_subscription_lifecycle.py::test_only_owners_open_the_customer_portal; B:test_memberships.py::test_only_owners_can_grant_or_change_ownership; B:test_organization_deletion.py::test_only_owners_request_deletion_and_pending_deletion_closes_the_organization; B:test_yearclock_role_matrix.py::test_yearclock_roles_follow_the_matrix |
| 38 | Admin manages users and all Yearclocks | Demonstrated | B:test_memberships.py::test_admin_manages_other_admins_but_not_owners; B:test_yearclock_role_matrix.py::test_yearclock_roles_follow_the_matrix; E:yearclock-structure.spec.ts::"an Admin creates, orders, archives, and restores Yearclocks and orders Lanes" |
| 39 | Admin barred from billing, Owners, deletion | Demonstrated | B:test_authorization_matrix.py::test_authorization_matrix[read seats], [preview seat increase], [open billing portal], [check deletion]; ::test_admins_cannot_promote_themselves_or_anyone_to_owner; B:test_organization_deletion.py::test_only_owners_request_deletion_and_pending_deletion_closes_the_organization; E:organization-deletion.spec.ts::"Admins cannot delete the Organization". |
| 40 | Owner or Admin gives Editors and Viewers access to Yearclocks | Demonstrated | Delivered in two steps per the PRD Further Notes, ADR-0007, and ADR-0020: B:test_yearclock_access.py::test_editor_grant_limits_lane_changes_to_one_yearclock; B:test_yearclock_role_matrix.py::test_yearclock_roles_follow_the_matrix |
| 41 | Invitation single-use, expires after 7 days | Demonstrated | B:test_invitations.py::test_invitation_reserves_capacity_and_authenticated_acceptance_converts_it (duplicate 409), ::test_resend_revocation_and_expiry_release_reserved_capacity |
| 42 | Resend invalidates the prior token | Demonstrated | B:test_acceptance_coverage.py::test_a_resent_invitation_invalidates_the_old_link (old token refused, new token accepted). |
| 43 | Pending Invitation reserves a seat | Demonstrated | B:test_invitations.py::test_invitation_reserves_capacity_and_authenticated_acceptance_converts_it |
| 44 | No access before authenticating and accepting | Demonstrated | Same test (wrong account 404; membership only after acceptance) |
| 45 | Admin cannot invite when no seat is free | Demonstrated | B:test_acceptance_coverage.py::test_admins_cannot_invite_beyond_free_seats. |
| 46 | Strongest additive permission wins | Demonstrated | B:test_yearclock_role_matrix.py::test_yearclock_roles_follow_the_matrix (an Admin with a Viewer grant still edits) |
| 47 | No hidden deny overrides | Demonstrated | ADR-0007; PRD Out of Scope ("Explicit deny permissions"); B:test_yearclock_role_matrix.py::test_yearclock_roles_follow_the_matrix |
| 48 | Editor creates, edits, restores, removes Events | Demonstrated | B:test_acceptance_coverage.py::test_editors_edit_delete_and_restore_events; B:test_authorization_matrix.py::test_authorization_matrix[create Event]. |
| 49 | Viewer inspects without mutation controls | Demonstrated | B:test_yearclock_role_matrix.py::test_yearclock_roles_follow_the_matrix; E:yearclock-access.spec.ts::"an Editor gets mutation controls while a Viewer gets the same details read-only" |
| 50 | Removing a membership keeps the account and other memberships | Demonstrated | B:test_acceptance_coverage.py::test_removal_keeps_the_account_session_and_other_memberships. |
| 51 | Account deletion blocked for a sole Owner | Out of scope / decided | Product decision 2026-09-23 (user-approved; ticket 07 comments; PRD Further Notes): V1 exposes no account deletion. The future guard is recorded in `docs/architecture/lifecycle-defaults.md` ("Account deletion"). |
| 52 | Any number of Yearclocks within safety limits | Demonstrated | B:test_yearclock_structure.py::test_owner_manages_yearclock_and_lane_lifecycle; B:test_operational_limits.py::test_structure_ceilings_refuse_with_a_named_reason, ::test_event_and_series_ceilings_hold_under_concurrent_writes, ::test_a_dense_yearclock_lists_every_event_quickly; E:operational-limits.spec.ts. |
| 53 | Name, rename, order Yearclocks | Demonstrated | B:test_yearclock_structure.py::test_owner_manages_yearclock_and_lane_lifecycle, ::test_yearclock_order_requires_current_versions; E:yearclock-structure.spec.ts::"an Admin creates, orders, archives, and restores Yearclocks and orders Lanes" |
| 54 | Archive an inactive Yearclock | Demonstrated | Same tests |
| 55 | Deleted Yearclock recoverable for 30 days | Demonstrated | B:test_recoverable_deletion.py::test_a_deleted_yearclock_and_its_content_are_hidden_and_recoverable; E:yearclock-structure.spec.ts::"an Admin deletes a Yearclock and recovers it within 30 days" |
| 56 | Ordered Lanes as concentric rings | Demonstrated | B:test_yearclock_structure.py::test_owner_manages_yearclock_and_lane_lifecycle; U:geometry.test.ts::"the first Lane is the outermost band and bands tile the ring" |
| 57 | Every Event in exactly one Lane | Demonstrated | B:test_events.py::test_event_validation_matches_the_approved_limits (foreign Lane rejected) |
| 58 | Lane order sets ring order | Demonstrated | U:geometry.test.ts::"the first Lane is the outermost band and bands tile the ring"; E:yearclock-structure.spec.ts (Lane reorder) |
| 59 | Lane deletion blocked until its Events are moved | Demonstrated | B:test_yearclock_structure_changes.py::test_a_lane_with_events_is_removed_only_after_an_explicit_move; E:yearclock-classification.spec.ts::"a Lane with Events is deleted only after moving its Events" |
| 60 | Named, colored Categories | Demonstrated | B:test_yearclock_structure_changes.py::test_categories_are_versioned_audited_and_leave_events_uncategorized |
| 61 | At most one Category per Event | Demonstrated | Single `category_id` field; B:test_events.py::test_event_validation_matches_the_approved_limits |
| 62 | Confirm before deleting a Category | Demonstrated | B:test_yearclock_structure_changes.py::test_categories_are_versioned_audited_and_leave_events_uncategorized (unconfirmed 400); E:yearclock-classification.spec.ts::"deleting a Category asks for confirmation and states the consequence" |
| 63 | Lanes and Categories independent of permissions | Demonstrated | B:test_yearclock_access.py::test_editor_grant_limits_lane_changes_to_one_yearclock; ADR-0006; PRD Out of Scope ("Lane permissions, Categories as permissions") |
| 64 | Create an Event by selecting Lane and date | Demonstrated | E:yearclock-view.spec.ts::"an Editor creates an Event by selecting a Lane position on the circle" |
| 65 | All-day start, optional inclusive end | Demonstrated | B:test_events.py::test_event_validation_matches_the_approved_limits, ::test_planning_window_returns_overlapping_events_only; U:geometry.test.ts::"inclusive ranges cover their last day and clip to the window" |
| 66 | Title, optional description and URL | Demonstrated | B:test_events.py::test_event_validation_matches_the_approved_limits; E:yearclock-view.spec.ts::"the circular Yearclock draws point and range Events with an equivalent summary" |
| 67 | Plain-text description, line breaks, safe auto-links | Demonstrated | E:acceptance-coverage.spec.ts::"descriptions keep line breaks and show markup literally (story 67)" (HTML and Markdown stay literal; trailing punctuation is no longer part of an auto-link); B:test_events.py::test_event_validation_matches_the_approved_limits. |
| 68 | Event stays planning intent with no Task state | Out of scope / decided | ADR-0027 (Event-only V1); PRD Out of Scope ("Tasks, and Task-system integrations") |
| 69 | Category classifies across Lanes without permissions | Demonstrated | E:yearclock-classification.spec.ts::"a Category colours Events on every Lane and is always named" |
| 70 | Deleted standalone Event recoverable for 30 days | Demonstrated | B:test_events.py::test_event_changes_are_versioned_recoverable_and_audited; B:test_recoverable_deletion.py::test_the_purge_job_removes_only_expired_content_idempotently |
| 71 | Stale write rejected and latest data shown | Demonstrated | E:acceptance-coverage.spec.ts::"a stale save shows the latest version for review (story 71)"; B:test_events.py::test_event_changes_are_versioned_recoverable_and_audited. |
| 72 | Weekly Series, one weekday, interval | Demonstrated | B:test_recurrence.py::test_weekly_interval_keeps_one_weekday_and_stops_at_until |
| 73 | Monthly anchored day with interval | Demonstrated | B:test_recurrence.py::test_monthly_interval_and_count |
| 74 | Short month uses its last day, then returns to the anchor | Demonstrated | B:test_recurrence.py::test_monthly_anchor_falls_back_then_returns_to_anchor; B:test_series_editing.py::test_a_successor_keeps_the_monthly_anchor |
| 75 | Separate last-day-of-month rule | Demonstrated | B:test_recurrence.py::test_last_day_rule_and_february_twenty_ninth_yearly_skip; B:test_recurrence_jobs.py::test_the_series_api_returns_an_rrule_and_rejects_unsupported_rules |
| 76 | Yearly Series with month and day | Demonstrated | B:test_recurrence.py::test_last_day_rule_and_february_twenty_ninth_yearly_skip, ::test_supported_rules_have_an_rrule_and_unsupported_ones_are_rejected |
| 77 | February 29 skips non-leap years | Demonstrated | B:test_recurrence.py::test_last_day_rule_and_february_twenty_ninth_yearly_skip |
| 78 | Indefinite, until-date, or count end | Demonstrated | B:test_recurrence.py::test_weekly_interval_keeps_one_weekday_and_stops_at_until, ::test_monthly_interval_and_count; B:test_series_editing.py::test_restore_skip_and_end_keep_history (indefinite) |
| 79 | Only generated Occurrences count | Demonstrated | B:test_recurrence.py::test_yearly_occurrence_count_counts_generated_dates_not_skipped_years |
| 80 | "This occurrence only" field overrides | Demonstrated | B:test_series_editing.py::test_this_and_future_keeps_overrides_and_inherits_the_rest; E:yearclock-recurrence.spec.ts::"an Editor edits one Occurrence, this and future Occurrences, skips, and ends the Series" |
| 81 | Non-overridden fields keep inheriting | Demonstrated | B:test_series_editing.py::test_this_and_future_keeps_overrides_and_inherits_the_rest |
| 82 | "This and future" splits at the Series Date | Demonstrated | Same test; B:test_series_editing.py::test_splitting_at_the_first_occurrence_edits_the_segment_in_place |
| 83 | Moved Occurrence stays with its original segment | Demonstrated | B:test_series_editing.py::test_this_and_future_keeps_overrides_and_inherits_the_rest |
| 84 | Future exceptions keep overrides after a split | Demonstrated | Same test |
| 85 | Restore Series values | Demonstrated | B:test_series_editing.py::test_restore_skip_and_end_keep_history; E:yearclock-recurrence.spec.ts::"a Skipped Occurrence can be restored and a changed one restored to Series values" |
| 86 | Skip one Occurrence reversibly | Demonstrated | Same two tests |
| 87 | Ending a Series keeps history | Demonstrated | B:test_series_editing.py::test_restore_skip_and_end_keep_history; E:yearclock-recurrence.spec.ts (edit/skip/end test) |
| 88 | Distant Planning Window is complete | Demonstrated | B:test_acceptance_coverage.py::test_a_distant_planning_window_is_complete_without_the_worker (every weekly Occurrence of 2031 returned without a worker run); B:test_recurrence_jobs.py. |
| 89 | Current calendar year by default | Demonstrated | B:test_planning_window.py::test_default_window_is_current_calendar_year; U:geometry.test.ts::"a calendar-year window has 365 or 366 days" |
| 90 | Exactly 12 consecutive months | Demonstrated | B:test_planning_window.py::test_window_has_twelve_consecutive_months_across_year_boundary; U:geometry.test.ts::"an arbitrary starting month spans exactly 12 months across the year boundary" |
| 91 | Navigate the window backward and forward | Demonstrated | E:yearclock-view.spec.ts::"today, elapsed time, and month lengths follow the selected window", ::"the Planning Window crosses a month boundary with the month buttons" |
| 92 | Months on the outer scale, Lanes as rings | Demonstrated | E:yearclock-view.spec.ts::"the circular Yearclock draws point and range Events with an equivalent summary"; U:geometry.test.ts::"month segments follow unequal month lengths" |
| 93 | Elapsed, remaining, and today visible | Demonstrated | E:yearclock-view.spec.ts::"today, elapsed time, and month lengths follow the selected window"; U:geometry.test.ts::"today and elapsed time exist only inside the window" |
| 94 | Points, ranges, Categories, exceptions distinguishable without color | Demonstrated | E:yearclock-view.spec.ts::"the circular Yearclock draws point and range Events with an equivalent summary" (circle vs path, named Category); E:yearclock-accessibility.spec.ts::"a dense Series draws compact markers with one label and stays usable on a phone" (`rect.yc-exception`) |
| 95 | Categories add color across Lanes | Demonstrated | E:yearclock-classification.spec.ts::"a Category colours Events on every Lane and is always named" |
| 96 | Each Occurrence selectable | Demonstrated | E:yearclock-accessibility.spec.ts::"keyboard users reach every marker in chronological order and open details" |
| 97 | Dense weekly Series: compact markers, one label | Demonstrated | E:yearclock-accessibility.spec.ts::"a dense Series draws compact markers with one label and stays usable on a phone" |
| 98 | Exceptions emphasized | Demonstrated | Same test (`rect.yc-exception`) |
| 99 | Keyboard reach with visible focus | Demonstrated | E:yearclock-accessibility.spec.ts::"keyboard users reach every marker in chronological order and open details" (3px outline) |
| 100 | Synchronized semantic summary for screen readers | Needs human | Automated: E:yearclock-view.spec.ts::"the circular Yearclock draws point and range Events with an equivalent summary"; E:yearclock-accessibility.spec.ts::"the dense planner has no automatically detectable WCAG A/AA violations". A real screen-reader review is outstanding (ticket 23; `v1-acceptance.md`). |
| 101 | Full-screen sheet on mobile | Demonstrated | E:yearclock-view.spec.ts::"a small screen keeps the circle inside the viewport and opens details as a full-screen sheet" |
| 102 | Viewer sees the same details read-only | Demonstrated | E:yearclock-view.spec.ts::"a Viewer sees the same details without mutation controls"; E:yearclock-access.spec.ts (see 49) |
| 103 | Explicit Save and Cancel, no drag editing | Demonstrated | E:acceptance-coverage.spec.ts::"Cancel discards edits without sending anything (story 103)"; E:yearclock-view.spec.ts (Save). Drag editing is PRD Out of Scope. |
| 104 | Finnish or English interface | Demonstrated | E:acceptance-coverage.spec.ts::"the Finnish interface translates the product but never customer content (stories 104, 107)"; U:i18n.test.ts (same texts in both languages, English fallback); B:test_acceptance_coverage.py::test_invitation_and_email_commit_together_and_carry_no_secrets (Finnish Invitation email); E:authentication.spec.ts (language switch). A native-speaker wording review stays in the launch checklist. |
| 105 | Organization default locale and time zone | Demonstrated | B:test_organization_activation.py::test_signup_validates_seat_count_and_iana_time_zone; B:test_time_zone.py::test_organization_today_uses_the_organization_time_zone; B:test_recurrence_jobs.py::test_the_horizon_follows_the_organization_time_zone |
| 106 | User locale overrides the Organization default | Demonstrated | Locale override: see 104 (B:test_authentication.py::test_customer_can_change_the_shell_locale). The per-user display time zone was removed from V1 by product decision on 2026-09-23 (PRD Out of Scope, ADR-0015). |
| 107 | Customer content shown exactly as entered | Demonstrated | E:acceptance-coverage.spec.ts::"the Finnish interface translates the product but never customer content (stories 104, 107)". |
| 108 | Event dates stay all-day across time zones | Demonstrated | E:acceptance-coverage.spec.ts::"in America/Los_Angeles › Event dates stay the same all-day dates" and "in Pacific/Kiritimati › …"; U:geometry.test.ts. |
| 109 | Organization deletion is recoverable for 30 days | Demonstrated | B:test_organization_deletion.py::test_only_owners_request_deletion_and_pending_deletion_closes_the_organization, ::test_restore_inside_the_window_keeps_the_billing_state; E:organization-deletion.spec.ts::"an Owner confirms deletion explicitly and is returned to the Organization list", ::"an Owner restores a Pending Deletion Organization from the list" |
| 110 | Restore does not fabricate a subscription | Demonstrated | B:test_organization_deletion.py::test_restore_inside_the_window_keeps_the_billing_state |
| 111 | Purge content, keep Billing Records and minimal evidence | Needs human | Mechanism: B:test_organization_deletion.py::test_purge_removes_customer_content_and_keeps_minimal_evidence, ::test_a_restored_organization_is_not_purged_by_a_stale_job, ::test_audit_summaries_can_only_be_emptied_by_the_purge_scope. Statutory retention needs legal review (PRD Further Notes; ADR-0008). |
| 112 | Separate operator console | Demonstrated | B:test_platform_operations.py::test_enrolled_staff_sign_in_to_the_console_and_never_reach_customer_routes; E:platform-console.spec.ts::"a platform account opening the customer application is pointed to the console" |
| 113 | Lifecycle and subscription view without content | Demonstrated | B:test_platform_operations.py::test_admins_see_lifecycle_and_health_without_content; E:platform-console.spec.ts::"a Platform Admin sees health, Organizations, and replays a failed job" |
| 114 | Request Support Access with case, Organization, scope, duration | Demonstrated | B:test_support_access.py::test_read_grant_lets_the_agent_read_and_nothing_more, ::test_requests_need_a_support_agent_and_an_active_organization; E:support-access.spec.ts::"a Support Agent requests access and reads approved content" |
| 115 | Owner or Admin approves or rejects | Demonstrated | B:test_support_access.py::test_only_owners_and_admins_decide_and_agents_cannot_self_approve; E:support-access.spec.ts::"Owners approve a shorter Support Access grant and revoke it" |
| 116 | Read-only by default, write called out | Demonstrated | B:test_support_access.py::test_read_grant_lets_the_agent_read_and_nothing_more, ::test_write_grant_edits_events_and_revocation_fails_closed; E:support-access.spec.ts (approve test: "read and edit Events") |
| 117 | At most 24 hours and revocable | Demonstrated | B:test_support_access.py::test_requests_need_a_support_agent_and_an_active_organization (25 h → 422), ::test_write_grant_edits_events_and_revocation_fails_closed, ::test_expired_grants_fail_closed_and_are_audited_once |
| 118 | No self-approval or bypass | Demonstrated | B:test_support_access.py::test_only_owners_and_admins_decide_and_agents_cannot_self_approve, ::test_postgres_refuses_content_under_an_inactive_or_read_only_grant; B:test_platform_operations.py::test_admins_see_lifecycle_and_health_without_content |
| 119 | Support lifecycle fully audited | Demonstrated | B:test_support_access.py::test_read_grant_lets_the_agent_read_and_nothing_more, ::test_write_grant_edits_events_and_revocation_fails_closed, ::test_expired_grants_fail_closed_and_are_audited_once |
| 120 | Owner or Admin inspects audit activity | Demonstrated | B:test_audit_activity.py::test_owners_and_admins_browse_scoped_paginated_activity; E:activity-log.spec.ts::"Owners browse, filter, and page through Organization activity" |
| 121 | Failed email, webhook, purge, recurrence jobs inspectable and replayable | Demonstrated | Email, purge, and recurrence: B:test_platform_operations.py::test_failed_jobs_are_inspectable_and_replay_is_idempotent_and_audited; B:test_acceptance_coverage.py::test_a_failed_recurrence_job_can_be_replayed; E:platform-console.spec.ts. Webhooks rely on Stripe redelivery by decision of 2026-09-23 (ADR-0009): B:test_acceptance_coverage.py::test_a_failed_webhook_leaves_no_trace_so_stripe_redelivery_succeeds. |

## Testing decisions

| # | Testing decision (short) | Status | Evidence |
| --- | --- | --- | --- |
| T1 | API-level integration against real PostgreSQL | Demonstrated | `B:conftest.py` migrates a real PostgreSQL database; all `B:test_*` API tests use `TestClient` |
| T2 | Focused browser suite over the listed user flows | Partial | All listed flows, including Invitation acceptance (E:acceptance-coverage.spec.ts::"an invited person accepts the Invitation…", "a rejected Invitation explains why"). Specs stub the API; a full-stack run against real Authentik and Stripe test mode needs a human (ticket 22). |
| T3 | Recurrence unit and property-based tests | Demonstrated | B:test_recurrence_properties.py (Hypothesis: month length and anchors, leap days, weekly spacing, counts, inclusive until, determinism); B:test_recurrence.py; B:test_recurrence_jobs.py::test_concurrent_materialization_never_duplicates. |
| T4 | Deterministic SVG geometry tests | Demonstrated | U:geometry.test.ts (all 8 tests: angles, inclusive ranges, Lane radii, 12-month boundaries, today) |
| T5 | Accessibility tests (keyboard, focus, semantics, non-color, labels, axe) | Demonstrated | E:yearclock-accessibility.spec.ts (3 tests); axe scans in E:support-access.spec.ts, E:organization-deletion.spec.ts, E:platform-console.spec.ts. Manual assistive-technology review is story 100 (Needs human). |
| T6 | Authorization role matrix incl. platform roles and Support grants | Demonstrated | B:test_authorization_matrix.py (8 actors × 18 endpoints, self-promotion, RLS on 11 tables); B:test_yearclock_role_matrix.py; B:test_support_access.py. |
| T7 | Tenant isolation: guessed IDs, stale route, workers, direct queries | Demonstrated | B:test_acceptance_coverage.py::test_a_job_for_one_organization_cannot_see_another; B:test_authorization_matrix.py::test_rls_hides_every_tenant_table_across_organizations; B:test_organization_context.py::test_guessed_routes_and_unscoped_queries_cannot_cross_organizations. |
| T8 | Billing adapter: signatures, duplicates, ordering, seats, failure, grace, cancel, recovery | Demonstrated | B:test_organization_activation.py::test_stripe_signature_verification_rejects_tampering; B:test_subscription_lifecycle.py (all 5); B:test_seat_capacity.py (both); B:test_stripe_billing.py (all 3). These use a contract-faithful fake; Stripe test-mode verification is ticket 22. |
| T9 | Email: outbox in originating transaction, idempotent claims, retry, no credentials | Demonstrated | B:test_acceptance_coverage.py::test_invitation_and_email_commit_together_and_carry_no_secrets; B:test_work_queue.py; B:test_email_delivery.py. |
| T10 | Destructive lifecycle: restore windows, ownership, seat release, purge, Billing Record separation | Demonstrated | B:test_acceptance_coverage.py::test_removing_a_member_through_the_api_frees_a_seat; B:test_organization_deletion.py; B:test_recoverable_deletion.py; B:test_memberships.py::test_last_owner_cannot_leave_or_be_removed. |
| T11 | Tests assert user-visible and API/database outcomes | Demonstrated | Browser specs use role and label queries; backend tests assert HTTP and SQL outcomes |
| T12 | Establish high-level seams first | Demonstrated | Backend API, browser, and geometry unit suites exist as described in T1, T2, and T4 |

## Follow-up

Every Partial item, with its next step. There are no Gap items. Needs human
items (stories 1–5, 100, 111) are tracked in ticket 22,
`docs/runbooks/production-readiness.md`, and `docs/runbooks/v1-acceptance.md`.

- **T2**: Run the main journeys once against the local stack with real Authentik and Stripe test mode, and record the result.
