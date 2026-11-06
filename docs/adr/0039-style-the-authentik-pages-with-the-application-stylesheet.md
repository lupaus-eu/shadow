---
status: accepted
---

# Style the Authentik sign-in pages with the application's stylesheet

## Context

People meet Authentik's pages (sign-in, enrolment, recovery, consent) as part of Yearclock, but they
look like authentik: its logo-and-photograph layout, its blue, its fonts. The web application has one
stylesheet (`frontend/src/theme.css`, `docs/design/ui-foundation.md`) whose tokens carry the product's
colors, type, radius, and shadow. Authentik takes custom CSS per brand (`branding_custom_css`, applied to
every page of the brand) and reads Patternfly custom properties that cross its web components' shadow
roots. It sets no Content-Security-Policy, so a stylesheet may be loaded from another address.
The application's stylesheet is a hashed file, its fonts are named with absolute `/assets/...` paths,
and fonts loaded from another origin need CORS headers.

## Decision

- **The Authentik pages import the application's own stylesheet.** The brand's custom CSS starts with
  `@import url(<stylesheet>) layer(yearclock-app)`; layered, it can never override Authentik's rules, so
  Tailwind's utilities cannot disturb Authentik's markup, and it supplies the tokens. A bridge file,
  `authentik/blueprints/yearclock-brand.css`, follows it: it maps the tokens onto the Patternfly and
  Authentik variables the pages read, with a fallback value on every variable so the pages still look
  right if the stylesheet cannot be loaded.
- **A stable address.** The build publishes the one built stylesheet a second time as `/theme.css`
  (a Vite plugin copies it; the build fails if there is not exactly one stylesheet). The frontend
  server serves it with `Cache-Control: no-cache` so it follows every release, and serves `/assets/*`
  (hashed, immutable, public) with `Access-Control-Allow-Origin: *` so the identity origin can load the
  fonts. The address is `AUTHENTIK_THEME_CSS_URL`: production derives it from `FRONTEND_URL`
  (`<FRONTEND_URL>/theme.css`); the local stack points at the Vite dev server
  (`http://localhost:8173/src/theme.css?direct`, which has no fonts, so local pages use the system font).
- **Scope.** The bridge applies only to pages that hold a flow (`:root:has(ak-flow-executor)`), not to
  Authentik's user and admin interfaces.
- **No background image.** The bridge sets `--ak-global--background-image: none` and the page uses
  the application's canvas color. The brand's default flow background is set to a 68-byte static image,
  because the page always asks for one and would otherwise fetch the 1 MB default photograph.
- **Light theme only.** The brand attribute `settings.theme.base: light` fixes Authentik's theme, as the
  application has one light theme (a dark theme would redefine the tokens, `ui-foundation.md`). This also
  applies to Authentik's own interfaces.
- A blueprint, `authentik/blueprints/yearclock-brand.yaml`, applies it to the default brand and the bridge
  file is read with `!File`, so it is versioned like the other Authentik configuration.
- Logo and title are not changed by this decision.

## Consequences

- Changing a token in `theme.css` changes the sign-in pages at the next release, without touching Authentik.
  A unit test checks that every token the bridge uses exists in `theme.css` and that each fallback equals
  the token's value.
- The sign-in pages depend on the application's origin being reachable for their look (not for working):
  if it is down they fall back to the bridge's fallback values and Authentik's own fonts.
- The identity origin loads files from the application origin; both belong to the operator.
- Authentik's admin and user interfaces become light-only and keep Authentik's own styling otherwise.
- A new Authentik version can rename the Patternfly variables or part names the bridge uses; the upgrade
  runbook gets a visual check of the sign-in pages.
- Refines ADR-0010 and ADR-0036. Does not change ADR-0038.
