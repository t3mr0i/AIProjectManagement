# Project Hub UI guidelines: Linear as the north star

Linear is the quality bar for density, calm and speed. We implement it **inside Plane**, with `@makeplane/propel` primitives, `@plane/blocks` composites and Plane's existing tokens and Tailwind classes. There is no second design system and no copied Linear assets. References were collected via Mobbin (links below).

## References (Mobbin, Linear web)

- **Issue list grouped by status:** [1](https://mobbin.com/screens/46088879-314c-405c-88b5-eb7820c05efb), [2](https://mobbin.com/screens/610d34b6-6ad8-45ab-80fb-2107b31ed01e), [dark](https://mobbin.com/screens/e142df2a-3527-499c-8f81-1b715947ac0c), [bulk select](https://mobbin.com/screens/3f36e39e-2b9e-4145-bee2-f43a3cf21f7b)
- **Issue detail with properties sidebar:** [1](https://mobbin.com/screens/f00cc4fb-4083-43fc-a0fb-703a6c4ef771), [activity](https://mobbin.com/screens/2e6c00de-40a7-455d-875f-0d8cb27c8270), [inline sub-issue create](https://mobbin.com/screens/953e88d0-de6c-4eaf-9921-cd0c55bb8412)
- **Inbox, two-pane:** [list + empty detail](https://mobbin.com/screens/18c6955a-c42f-4cc1-9aa2-0276456720fb), [list + issue](https://mobbin.com/screens/beb9d6b3-ec34-46d7-9332-320fcb32a338), [empty](https://mobbin.com/screens/5e4be052-1838-45d0-b850-fd7306cd4bff)
- **Project overview, milestones and progress:** [1](https://mobbin.com/screens/e2106805-ecc7-40a4-a35c-e2c315b24954), [update + activity](https://mobbin.com/screens/43a3307a-6591-4ef2-95d8-197ea0720939), [milestones](https://mobbin.com/screens/4609e1db-a9f7-459d-9e7f-87e52dfb2418)
- **Roadmap / timeline:** [1](https://mobbin.com/screens/64119b7d-8337-4873-8794-1ead1cba2618)
- **Settings, grouped rows:** [project statuses](https://mobbin.com/screens/dd23cdb6-3c73-41dc-9b0e-7eddf870a7c6)

## Rules

**Chrome**

- The page header is the breadcrumb bar (about 44px) with actions on the right.
- List and board screens have **no extra H1** that repeats the breadcrumb.
- View switches (for example "All / Active / Backlog", "Timeline / Table") are small pill tabs directly under the header. Filter and display controls are icon buttons on the right of the same row.

**Density and type**

- Base text is 13px (`text-13`/`text-sm` in Plane tokens) and metadata is 12px in muted color. Use one font weight for titles (medium); never bold whole rows.
- Use the 4/8px spacing grid.
- List rows are about 36px high and on a single line. Nothing wraps inside a row; truncate with an ellipsis.

**List rows**

- The order is `[priority icon] [identifier, muted] [status/phase icon] [title]` and then, right-aligned: chips (colored dot + label), project/package chip, date, assignee avatar.
- Hover shows a subtle background. The focused row (keyboard, #9831 list navigation) has a visible ring or background.
- The whole row is the link to the same native issue.

**Groups**

- The group header is a subtle filled bar (layer-2 background) with a collapse chevron, the status/phase icon, the name, a muted count and `+` on the right. It is sticky while scrolling.
- **Empty groups are hidden** by default. If they are shown, use one muted line, never a boxed "Nothing in this section".

**Detail pages**

- The main column holds the title, description, sub-items and activity. The right sidebar holds stacked cards with collapsible headers: Properties, Labels, Project, and for us **Work package** (phase, delivery, approval state, primary action).
- Secondary actions go in the header icon row. Do not use large bordered callout boxes in the content flow.

**Activity**

- A compact timeline uses 16px avatars or icons, one line per event, a muted relative time, and the actor name in normal weight.
- Grouping (per package and day) uses the same group-bar style as lists. Expandable raw details are inline and quiet.

**Two-pane (Messages, notifications)**

- A list of about 320px is on the left with a selected-row background. The detail pane is on the right.
- When nothing is selected, the detail pane shows a centered empty state (outline icon + one muted line).

**Empty states**

- Use a centered outline icon, one short line and at most one quiet action.
- No dashed boxes, no "No active work." cards inside sections.

**Chips and badges**

- A chip is a small rounded pill, 20px high, with a color dot, 12px text and a neutral border or background.
- Phase badges (Drafts/Ready/Build/Review/Ship/Done) use an icon plus text, never color alone (WCAG).

**Settings**

- Settings use a centered column of about 640px, a section title with a one-line muted description, and grouped rows inside rounded cards with subtle header bars.
- Tables are compact, and destructive actions are quiet text buttons that ask for confirmation.

**Roadmap**

- The month/week scale sits on top with a "Today" pill marker, and the project list is on the left with status, priority and lead icons.
- Bars are rounded and 20px high. Undated items are one compact list row each, not a chip wall.

**Motion and feedback**

- Transitions last 100–150ms, with no bouncy animations.
- Optimistic UI is only for harmless fields. Approvals and merges show server state (PRD §11.4).

**Keyboard**

- Every list supports j/k or arrow-key navigation and Enter to open (from upstream #9831).
- Primary actions have a shortcut hint in their tooltip.

## Definition of done per screen

For each screen: a screenshot compared side by side with its Linear reference, all the states (loading, empty, error, permission, stale, conflict), keyboard reachability, the dark theme checked, `check:types`, `build`, oxlint and oxfmt.
