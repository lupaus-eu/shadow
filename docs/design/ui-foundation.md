# UI foundation

The visual and interaction rules behind every Yearclock screen. Code:
`frontend/src/theme.css` (tokens), `frontend/src/ui/` (components),
`frontend/src/shell/` (layouts). The direction was set in the interface
redesign (`.scratch/yearclock-v2-ui-redesign/`), and its mockup is at
https://claude.ai/artifact/FbMrocC5cWGVwEZkdR4fGh.

## Principles

- **Consistency over novelty.** A few fixed values, used the same way on every
  page, make the product look finished. Add a token or a component only when
  an existing one cannot express the need.
- **Compact, not cramped.**
  - Body text is 14 px; secondary text and controls are 13 px.
  - Controls are 34–36 px high, and at least 44 px on touch screens
    (`pointer-coarse`).
- **The circle is the product.** Chrome stays neutral: greys plus one accent.
  Colour carries meaning on the circle (Categories, Labels), so the interface
  never competes with it.
- **Accessible by construction.**
  - Real buttons, links, and labels.
  - A visible focus ring everywhere.
  - Status and alerts in live regions.
  - WCAG 2.1 AA contrast.

## Tokens

Tokens are named by meaning, never by hue, so a dark theme is a second set of
values for the same names. Use the Tailwind utilities they generate
(`bg-surface`, `text-ink-muted`, `border-line`, `bg-accent`…); never
hard-code a hex value in a component.

| Token | Value | Use |
| --- | --- | --- |
| `canvas` | `#F4F6F7` | Page background behind cards |
| `surface` | `#FFFFFF` | Cards, panels, inputs, the top bar |
| `surface-subtle` | `#F8FAFB` | Table headers, hover on secondary buttons |
| `surface-sunken` | `#E9EDF0` | Segmented control track, disabled fields |
| `line` | `#DDE2E6` | Card and divider borders |
| `line-strong` | `#8A96A0` | Form control borders (3:1 against surface) |
| `ink` | `#17212B` | Text |
| `ink-muted` | `#56636E` | Secondary text, captions, table headers |
| `accent` / `accent-hover` / `accent-soft` | `#0F766E` / `#0B5F59` / `#E3F2EF` | Primary actions, links, current navigation, focus ring |
| `danger` / `danger-soft` | `#B42318` / `#FEF1F0` | Destructive actions and errors |
| `warning-ink` / `warning-soft` / `warning-line` | `#6B4E00` / `#FFF4D6` / `#F1D48A` | Billing and change notices |
| `success-ink` / `success-soft` | `#0B5F3A` / `#E7F6EE` | Confirmations |
| `info-ink` / `info-soft` | `#1D4F86` / `#EAF2FB` | Neutral information |
| `sidebar`, `sidebar-raised`, `sidebar-line`, `sidebar-ink`, `sidebar-muted` | `#111C24`, `#1A2731`, `#26343F`, `#C9D3DA`, `#8C9AA5` | The navigation sidebar |
| `focus-on-dark` | `#5EEAD4` | The focus ring inside the sidebar and the navigation drawer |
| `circle-ring`, `circle-scale`, `circle-label` | `#BCC5CC`, `#9AA5AD`, `#3B4650` | The circle's rings and Lane outlines, scale lines, and text |

Category and Label colours stay in their own palette (`LABEL_COLORS`) and are
never replaced by interface tokens.

### Contrast (WCAG 2.1)

| Pair | Colours | Ratio |
| --- | --- | --- |
| ink on surface | `#17212B` on `#FFFFFF` | 16.29:1 |
| ink on canvas | `#17212B` on `#F4F6F7` | 15.03:1 |
| ink-muted on surface | `#56636E` on `#FFFFFF` | 6.17:1 |
| ink-muted on canvas | `#56636E` on `#F4F6F7` | 5.69:1 |
| white on accent | `#FFFFFF` on `#0F766E` | 5.47:1 |
| white on accent-hover | `#FFFFFF` on `#0B5F59` | 7.51:1 |
| accent on surface (links, focus ring) | `#0F766E` on `#FFFFFF` | 5.47:1 |
| accent on canvas (focus ring) | `#0F766E` on `#F4F6F7` | 5.05:1 |
| focus-on-dark on sidebar (focus ring in the sidebar) | `#5EEAD4` on `#111C24` | 11.68:1 |
| accent on accent-soft | `#0F766E` on `#E3F2EF` | 4.75:1 |
| sidebar-ink on sidebar | `#C9D3DA` on `#111C24` | 11.37:1 |
| sidebar-muted on sidebar | `#8C9AA5` on `#111C24` | 5.99:1 |
| white on danger | `#FFFFFF` on `#B42318` | 6.57:1 |
| danger on danger-soft | `#B42318` on `#FEF1F0` | 5.97:1 |
| warning-ink on warning-soft | `#6B4E00` on `#FFF4D6` | 7.06:1 |
| success-ink on success-soft | `#0B5F3A` on `#E7F6EE` | 6.94:1 |
| control border (line-strong) on surface | `#8A96A0` on `#FFFFFF` | 3.02:1 |

A new colour pair needs a row here before it ships.

### Type, spacing, shape

- **Font:** Inter Variable, served by Yearclock
  (`@fontsource-variable/inter`), so CSP keeps `font-src 'self'`. System
  sans-serif is the fallback.
- **Type scale:**
  - page title 20 px semibold;
  - top-bar title 17 px semibold;
  - section title 15 px semibold;
  - card title 14 px semibold;
  - body 14 px;
  - controls, tables, and secondary text 13 px;
  - captions and badges 12 px.
  - Headings use `tracking-tight`, and numbers in tables use `tabular-nums`.
- **Spacing:** on the 4 px grid; use 8, 12, 16, 20, or 24 px.
  - Page padding is 24 px (16 px on phones).
  - Card padding is 20 px.
  - The gap between cards is 16 px.
- **Radius:** controls 8 px, cards 12 px, badges fully round.
- **Shadow:** `shadow-card` for cards only. `shadow-overlay` for dialogs,
  drawers, menus, and toasts.

## Components (`frontend/src/ui/`)

- **Button:**
  - Variants:
    - `primary`: one per view, the main action;
    - `secondary`: the default;
    - `ghost`: toolbars and rows;
    - `ghost-danger`: a destructive row action (Delete, Remove, Revoke) that
      a confirmation or an undo path follows;
    - `danger`: only for destructive confirmation.
  - Sizes `md` (34 px) and `sm` (32 px); no target is under 32 px, and 44 px on touch screens.
  - Put an icon before the label when it helps scanning.
  - `IconButton` requires `label`, which becomes the accessible name and the
    tooltip.
- **Field:**
  - Controls fill their container unless given a `w-*` width.
  - Every form control sits in a `Field`, which wires the label, hint, and
    error to the control by id (`aria-describedby`, `aria-invalid`).
  - Use `hideLabel` only where a visible label is redundant, such as a search
    field with an icon; the label stays for screen readers.
- **TextInput, TextArea, Select:** 36 px, `line-strong` border, `danger`
  border when invalid.
- **Choice:** a checkbox or radio whose whole row is the target.
- **SegmentedControl:** one choice among two to six options, such as the
  window length. It is a radio group with arrow keys, and only the checked
  option is in the tab order.
- **Card:** the default container, placed on `canvas`.
- **Badge:** a short status (tones: neutral, accent, success, warning,
  danger, info). It is never the only carrier of meaning, so pair it with
  text.
- **Alert:** a message box. Pass `role="alert"` for errors that need
  attention and `role="status"` for polite information.
- **EmptyState:** says what is missing and what to do, with one action.
- **PageHeader:** title, one-line description, actions on the right.
- **Table:** in a bordered card, with the caption for screen readers and row
  actions at the end.

### Overlays (`frontend/src/ui/Overlay.tsx`, Radix primitives)

- **Confirmation (`useConfirm`)** replaces browser `confirm` everywhere:

  ```ts
  if (await confirm({ title, confirmLabel, destructive }))
  ```

  - `title` is the question with its consequence, for example "Delete the
    Label “Draft”? It is removed from 3 Events in all Yearclocks."
  - `confirmLabel` names the action ("Delete", "Merge", "Give edit
    access"), never "OK".
  - `destructive` makes the action button red.
  - Focus starts on **Cancel**. Escape cancels, and focus returns to the
    button that asked.
- **Dialog:** a centred modal for short tasks, with a title, optional
  description, body, and footer.
- **Drawer:** a side sheet from the right (full width on phones) for forms
  beside content, such as Event editing. Both trap focus, close on Escape and
  on their close button, and return focus.
- **Menu:** a list of actions behind a button (row actions, the user menu),
  with arrow keys and type-ahead.
- **Popover:** content anchored to a trigger, such as the change list.
- **Tabs:** arrows move between tabs, and the panel follows.
- **Toasts (`useToast`):**
  - Short success messages in the bottom-right "Notifications" region, a
    polite live region (`role="status"`).
  - At most three show at a time. Each stays 6 seconds, pauses on hover or
    focus, and has **Dismiss**.
  - Errors are never toasts: they stay next to their action.
  - The region is one live element, not Radix Toast, whose extra announcer
    would duplicate each message for assistive technology and tests.
- `OverlayProvider` supplies these, with localized labels for Cancel, Close,
  Dismiss, and Notifications. It wraps the signed-in app.

## Layouts (`frontend/src/shell/`)

- `SignedOutLayout` is a centred card on `canvas` with the logo above it. It
  is used for sign-in, session states, onboarding, and invitations.
- `AppShell` frames every other signed-in page:
  - a 260 px `sidebar` column: logo, Organization switcher (name and role,
    a menu with the other Organizations, **All organizations**, and **Create
    another organization**), **Overview**, the Yearclocks, and
    **Administration** by role; the system status sits at the bottom. Group
    titles are small uppercase `sidebar-muted` text; the current page is
    `sidebar-raised` with white semibold text;
  - a 56 px top bar on `surface` with the page title (the only `h1`) and the
    account menu (initials; who is signed in, language as radio items, sign
    out);
  - the page in `main`, at most 72rem wide except the planner and the model
    Structure canvas, which use the full width (`AppShell wide`);
  - below `lg` (1024 px) the sidebar moves into a left drawer opened from the
    menu button; it closes when a link is chosen;
  - **Skip to content** is the first focus stop.
- The operator console uses the same frame (`ShellFrame`) with a **Platform**
  badge (warning tone) next to the logo, its own sidebar, the signed-in
  account and roles at the bottom of the sidebar, and **Sign out** in the top
  bar.

## Full-width canvas pages

The model **Structure** tab (`frontend/src/models/ModelCanvas.tsx`) is the only
page of the model that is full width; Types, Metrics, Simulations and Analysis
keep the reading column. `OrganizationLayout` turns `wide` on for that route.

- The canvas area ends at the bottom of the window (`window.innerHeight` minus
  its measured top, minimum 320 px), so the page does not scroll while drawing;
  the SVG `viewBox` is the container size (one unit is one pixel).
- Side panels sit beside the canvas: **Nodes** left (220 px), **Details** right
  (280 px, add node, selection, changes). Each collapses to a 40 px rail with
  one icon button (label **Collapse/Expand the ... panel**, `aria-expanded`,
  `aria-controls`). The collapsed state is the per-person
  `localStorage` key `shadow.canvas.panels`, read and written in try/catch
  (`models/panel-state.ts`); the page works without it.
- Below 768 px the panels become a bottom sheet: a 48 px handle button
  (**Show/Hide panels**, `aria-expanded`) fixed to the bottom, with the details
  and the node list in a scrolling sheet of at most 55 % of the height.

## The Authentik sign-in pages (ADR-0039)

The pages Authentik serves for sign-in, enrolment, recovery, and consent use this same stylesheet; there is
no second one. The build publishes it as `/theme.css`; the brand's custom CSS imports it (layered, so it cannot
override Authentik) and `authentik/blueprints/yearclock-brand.css` maps the tokens onto the Patternfly and
Authentik variables those pages read, each with a fallback equal to the token's value. The pages have the
canvas color and no background image, and stay light. Rules:

- Rename or change a token in `theme.css` and the bridge follows it; `tests/unit/authentik-brand.test.ts` fails
  if the bridge reads a token that no longer exists or a fallback that no longer matches.
- Style these pages only through tokens and the bridge; do not add a second stylesheet or inline Authentik CSS elsewhere.
- Authentik's user and admin interfaces keep Authentik's own styling (but the light theme).

## Native controls (`.ui-native`)

- Parts still built from native controls (the structure managers on
  Yearclock settings, the Label picker, History) sit inside `.ui-native`. A
  components-layer rule in `theme.css` gives their inputs, selects, buttons,
  fieldsets, and lists the same sizes, borders, and colours as `src/ui`.
- New work uses `src/ui`; `.ui-native` only bridges the old markup.

## Phones and visual baselines

- At 390 px wide nothing scrolls sideways; wide controls (the Length
  segmented control) scroll inside themselves.
- On touch screens (`pointer: coarse`) every control is at least 44 px high:
  `src/ui` uses `pointer-coarse:` variants, `.ui-native` has a coarse-pointer
  rule, and a card link covers its whole card.
- `tests/browser/visual.spec.ts` keeps screenshots of the Organization
  overview, the planner, the Event drawer, the People page, and the planner on
  a phone, with a fixed date and fixtures. Update them only on purpose and
  review the images in the change.
- `src/theme.css` is the only stylesheet (`styles.css` is gone). The circle's
  SVG classes live in its components layer on the `circle-ring`,
  `circle-scale`, and `circle-label` tokens plus the semantic ones, so a dark
  theme redefines variables only. Class names such as `yc-summary` or
  `yc-filters` that tests select by stay on the elements without CSS.

## Do and don't

- Do use one primary button per view. Don't make every action primary.
- Do write the consequence in a confirmation. Don't ask "Are you sure?"
- Do keep errors next to their action. Don't show an error only as a toast.
- Do use tokens. Don't add a hex value or a one-off font size.
- Do keep interface text in `i18n.ts` in both languages. Don't hard-code
  copy.

## Branding

The product is **Yearclock**; the company is **Lupaus Palvelut Oy**, shown as **LUPAUS**. The tab icon
(`frontend/public/favicon.svg`) is the Yearclock mark (the accent square with the clock). The company wordmark
(`lupaus-on-light.svg`, `lupaus-on-dark.svg`, LUPAUS outlined in Bruno Ace, SIL OFL, with a stroke to match the
original logo's weight) appears only small, as "Yearclock · LUPAUS" (`MadeBy`) in the sign-in layout, the sidebar footer,
and the public legal pages, and as a text line in emails. The wordmark colours are `#6d5883` and `#9ee8e7`, sampled from
the supplied logo. The SVGs are a redraw: replace them with the designer's own files when they exist.

## Public legal pages

`/legal` (index) and `/legal/:key` live outside the signed-in shell and need no session. They use their own frame: the
logo, a language switch (English and Finnish, remembered like the application language), and one reading column of
at most `3xl` on a card. The text is Markdown rendered without raw HTML; tables scroll sideways on a phone. A `draft`
text shows a warning banner and a Draft badge in the index. The signed-out layout and the shell sidebar footer link to
the index ("Terms and privacy"); invitation and notification emails link to `/legal/privacy`.

The sign-up form shows one checkbox per published required document (a fieldset, all required); the Owner's
"Legal documents" block in the Organization settings and a warning banner on Billing and seats (only while a version is
due and its date has passed) use the standard section card and alert.
