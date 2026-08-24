---
name: run-100-skills
description: Build, run, screenshot, and drive the 100-skills dashboard (100-skills/index.html) — the browsable "使える最高のスキル100" web page. Use when asked to run, open, preview, or screenshot the 100-skills dashboard, verify its search / category filtering works, or smoke-test the page after editing index.html.
---

The 100-skills dashboard is a **single self-contained static HTML file**
(`index.html`, ~2700 lines) — no build step, no dev server, no external
requests. It renders 100 skill cards, 10 category filter chips, and a
search box; the only JavaScript is an inline filter that shows/hides
cards and updates the header counter. You drive it headless with the
Playwright-based **`driver.mjs`** in this skill directory: it opens the
file in Chromium, exercises search + category filtering, asserts the
visible-card counts, and writes screenshots.

All paths below are relative to `100-skills/` (the directory this skill
lives under). The driver is at
`.claude/skills/run-100-skills/driver.mjs`.

## Prerequisites

In this container everything was **already installed** — nothing to
`apt-get`. The driver relies on:

- **Node** (`/opt/node22/bin/node`, v22).
- **Playwright**, installed globally at
  `/opt/node22/lib/node_modules/playwright` (v1.56).
- **Chromium**, preinstalled under `/opt/pw-browsers` (Playwright finds
  it via `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`).

The driver loads Playwright through a `createRequire` rooted at the
global module dir, so **no local `node_modules` and no `npm install` is
needed**. On a machine that lacks these, install once with
`npm i -g playwright && npx playwright install chromium` and point
`NODE_PATH` at the global module dir.

## Run (agent path)

From `100-skills/`, run the smoke test — it opens the page, checks the
default 100-card view, runs a search, filters a category, verifies the
counts and that nothing threw, and writes three screenshots:

```bash
node .claude/skills/run-100-skills/driver.mjs smoke
```

Expected tail: `SMOKE PASSED`. Screenshots land in **`/tmp/shots/`**
(`smoke-1-default.png`, `smoke-2-search-SEO.png`, `smoke-3-cat-08.png`).
**Look at them** — the default view should show a full grid of 100
cards under the trophy header; the category shot should show only that
category's 10 cards with its chip highlighted.

Other commands (each writes one screenshot to `/tmp/shots/`):

| command | what it does |
|---|---|
| `driver.mjs smoke` | full assertion run + 3 screenshots (default entry point) |
| `driver.mjs shot` | screenshot the default all-100 view |
| `driver.mjs search <term>` | type `<term>` into the search box, screenshot (e.g. `search SEO`, `search Claude`) |
| `driver.mjs cat <NN>` | click category chip `NN` (`01`..`10`), screenshot (e.g. `cat 08` = 財務・会計・税務) |

Override the screenshot dir with `SHOTS_DIR=/path`, or point at a
different HTML file with `HTML_PATH=/path/to/index.html`.

## Run (human path)

It's a plain static file — a human just opens it in a browser:

```bash
xdg-open index.html      # or drag index.html into any browser
```

Useless headless (no display), which is why the driver exists.

## Test

There is no test suite. `driver.mjs smoke` is the check: it fails
(non-zero exit) if the card count is wrong, the counter drifts from the
visible cards, or the page logs a console error.

## Gotchas

- **No dev server needed.** The page uses no `fetch`/`XHR` and no
  external scripts, so `file://` works — don't stand up an HTTP server.
- **ESM `import` ignores `NODE_PATH`.** Playwright is global, not in a
  local `node_modules`, so a bare `import { chromium } from 'playwright'`
  fails with `ERR_MODULE_NOT_FOUND`. The driver resolves it via
  `createRequire(...).require('/opt/node22/lib/node_modules/playwright')`
  instead — keep that indirection if you edit the driver.
- **Chromium needs `--no-sandbox`** in this container (running as root);
  the driver already passes it.
- **Filtering is client-side and instant**, but the driver waits ~150ms
  after `fill`/`click` before reading counts so the inline handler has
  run. Card visibility is `.card:not(.hide)`, and the header counter is
  `#count-n` — both are asserted together to catch drift.

## Troubleshooting

- **`ERR_MODULE_NOT_FOUND: Cannot find package 'playwright'`**: the
  global module dir moved. Set `NODE_PATH=/opt/node22/lib/node_modules`
  (or wherever `npm root -g` points) and re-run.
- **`Executable doesn't exist at .../chromium`**: `PLAYWRIGHT_BROWSERS_PATH`
  isn't set to `/opt/pw-browsers`. Export it, or run
  `npx playwright install chromium`.
