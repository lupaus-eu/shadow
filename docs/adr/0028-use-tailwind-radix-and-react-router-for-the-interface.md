---
status: accepted
---

# Use Tailwind CSS, Radix primitives, and React Router for the interface

## Context

The first Yearclock interface grew from one hand-written stylesheet and
browser-default controls. It had no application shell, no design tokens, and
browser `confirm` windows. The interface redesign
(`.scratch/yearclock-v2-ui-redesign/`) needs three things:
- consistent styling that is cheap to keep consistent;
- accessible overlays (dialogs, drawers, menus, tabs, toasts) with correct
  focus handling;
- nested routes for a sidebar shell and administration pages.

## Decision

- **Tailwind CSS v4** (`@tailwindcss/vite`):
  - Semantic tokens are declared with `@theme` in `frontend/src/theme.css`
    and exposed as CSS custom properties. A dark theme later is a second set
    of values.
  - Tailwind's preflight reset is not imported while the old stylesheet
    remains. It sits in a lower `legacy` layer, so new components win and
    unconverted pages keep their look.
- **Radix primitives** for dialogs, alert dialogs, menus, tabs, popovers,
  and toasts. They carry no styling of their own, and Yearclock styles them
  with its tokens.
- **React Router v7** in declarative mode for nested layouts and real
  addresses. The existing data clients stay as they are.
- **lucide-react** for icons, and **Inter** served from the build, so CSP
  keeps `font-src 'self'` and no external font service is used.

## Consequences

- Styling lives next to markup as utility classes, following
  `docs/design/ui-foundation.md`. Shared patterns are components in
  `frontend/src/ui/`, not copied class lists.
- Radix handles focus trapping, Escape, and focus return, which a
  hand-built dialog would get wrong. The axe scans still run on every view.
- Runtime dependencies grow by Tailwind (build time only), Radix packages,
  React Router, lucide-react, clsx, and the Inter font package, all
  MIT-licensed.
- Replacing browser `confirm` changes how browser tests handle
  confirmations. They drive the dialog instead of `page.on("dialog")`.
