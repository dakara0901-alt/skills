# AGENTS.md

## Cursor Cloud specific instructions

This repository is Anthropic's **Agent Skills library** — a collection of self-contained
skills under `skills/` (each a `SKILL.md` plus bundled scripts/assets), the spec (`spec/`),
and a skill template (`template/`). It is **not a deployable app**: there is no root
`package.json`, no unified dev server, no build step, and no automated test suite. There is
also no linter configured. "Running the product" means invoking a skill's bundled scripts
and inspecting their output.

The update script installs the two declared Python manifests
(`skills/slack-gif-creator/requirements.txt` and `skills/mcp-builder/scripts/requirements.txt`)
into the user site via `pip3 install --user`. `PyYAML` (used by `skill-creator`) is already
present in the base image.

### Running skills — non-obvious gotchas

- **`slack-gif-creator`**: its scripts import from a local `core` package (e.g.
  `from core.gif_builder import GIFBuilder`). There is no `__init__.py` / it is not installed,
  so you must run from the skill directory **with `PYTHONPATH` set to the skill root**:
  `cd skills/slack-gif-creator && PYTHONPATH=. python3 your_script.py`.
- **`web-artifacts-builder`**: scaffold with `bash scripts/init-artifact.sh <name>`, then bundle
  with `bash scripts/bundle-artifact.sh` (run from the project root) to produce a self-contained
  `bundle.html`. Two gotchas:
  - The current `create-vite` `react-ts` template writes
    `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />` into `index.html`, and
    `init-artifact.sh`'s `sed` cleanup only strips the older `vite.svg` icon line. Parcel then
    fails with `Failed to resolve '/favicon.svg'`. Remove that `<link rel="icon" ...>` line (or
    add a `favicon.svg`) before bundling.
  - `pnpm` prints an "Ignored build scripts" warning during install; bundling still succeeds, so
    do not run the interactive `pnpm approve-builds`.
- **`skill-creator`**: `python3 scripts/quick_validate.py <path-to-skill>` validates a skill's
  `SKILL.md` structure/frontmatter (pure Python, uses preinstalled PyYAML).

### System tooling not preinstalled

The document skills (`docx`, `pptx`, `xlsx`, `pdf`) rely on system binaries that are **not**
installed in this environment: LibreOffice (`soffice`), `pandoc`, and Poppler (`pdftoppm`,
`pdftotext`). Basic Python-only operations work, but conversion / visual QA / formula recalc
(e.g. `scripts/office/soffice.py`, `scripts/recalc.py`) require installing those tools first.
