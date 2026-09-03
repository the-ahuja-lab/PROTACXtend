# WEBSITE_CHANGELOG.md

Log of website changes with the scientific-coherence overhaul.

## v2.7 — end-of-page tone pass: navy/cyan ending → single deep-violet family (2026-09-03)

- CTA band (page end): replaced the navy→royal-blue gradient + cyan gradient heading with one deep-violet family (radial violet washes over #3D3690 → #2B2569 → #1B1740); heading emphasis is now solid light lavender.
- Footer: background moved from navy-black #060A1E to deep violet #161226; column headings lavender.
- Other dark-blue surfaces unified for consistency: hero stats band, mechanism chain and the About release card now use the same deep-violet gradient; stat numbers are solid light lavender instead of blue gradient.
- Neutralized text inks: headings/body no longer carry a navy cast (--ink/--navy/--deep-blue moved to near-neutral charcoal and deep violet); remaining navy literals in buttons, emphasis and shadows replaced with violet equivalents.
- No layout/overflow changes; hero artwork assets untouched.

## v2.6 — hero enlarged & decluttered (2026-09-03)

- Hero restructured to a centered single-column hero: headline → lede → CTAs on top, then the **hero artwork full-width beneath it** (up to 1040px wide vs the previous ~540px half-column) so the artwork’s left/right details stay legible.
- Declutter: removed the tertiary “Source code” CTA (GitHub already lives in the navbar/footer) and removed the card chrome from the four KNOW/REASON/DESIGN/DISCOVER blocks — they now sit as a slim, flat capability strip under the artwork (4-across on desktop, 2×2 on smaller screens).
- Tighter top padding and margins; hero note kept as a small centered line. No overflow/regressions at 320–1920px.

## v2.5 — hero image → AA.png + Impeccable craft/colorize/optimize/clarify/layout pass (2026-09-03)

- Hero visual now uses `assets/AA.png` (1672×941, 16:9); superseded `assets/hero.png` removed.
- `optimize`: added a responsive `<picture>` with an optimized **WebP** (1440w, 122 KB vs 1.96 MB PNG ≈ 16× smaller), `fetchpriority="high"` + `<link rel=preload>` + explicit width/height for LCP/CLS.
- `colorize`/`craft-floor`: hero image elevation simplified to one soft offset shadow (no border+shadow ghost card), radius 16px; hero note copy tightened (“A research system, not a demo…”); visible `:focus-visible` states for all hero/nav controls; spacing cadence tuned (more space above the headline than below, lede measure capped at ~66ch).
- No layout/overflow regressions at 320–1920px.

## v2.4 — hero visual swapped to authored image (2026-09-03)

- Replaced the inline SVG mechanism cartoon in the hero with the authored 16:9 hero illustration `website/assets/hero.png` (1672×941), shown cleanly on the right side of the two-column hero (rounded, subtle border/shadow; stacked + centred below the copy on ≤1080px).
- Removed the figure “window chrome” (topbar + Fig 1 caption) around the hero image; the research note remains beneath it.
- New stylesheet block `.hero-art`; responsive centering updated. No layout/overflow regressions at 320–1920px.

## v2.3 — Impeccable-style quality pass on hero/header (2026-09-03)

Ran the [pbakaus/impeccable](https://github.com/pbakaus/impeccable) `detect` audit against the served page and fixed the actionable findings in the landing hero/header (legacy table/badge tokens in lower docs sections left untouched — they are a separate site-wide pass).

- Removed `background-clip: text` gradient text from the landing UI (hero headline emphasis, DISCOVER loop title, navbar/footer wordmark “Xtend”) → solid high-contrast ink (#0F2280 / #5B4FC4; footer #BABDEE on dark).
- AA contrast: functional purple text darkened to #5B4FC4; muted text token #6A7294 → #656E92; CTA/GitHub buttons use a darker gradient (white text now ≥5.4:1 on every stop); “Fig 1” chip background darkened.
- Functional text ≥11px: navbar version chip, hero loop numbers, quick-start label, figure badge/caption type all raised off the sub-11px floor.
- Figure SVG micro-type raised (protein labels, module key, ternary label, Ub/degradation labels, schematic note) and labels tightened so nothing overlaps.
- Long all-caps hero kicker → mixed case (“Ahuja Lab · IIIT Delhi · Targeted protein degradation”).

Hero findings dropped from 223 to 194; all remaining findings are in pre-existing validation-matrix/table/demo-tag tokens (9.5px badges, pipeline numbering) outside this scope.

## v2.2 — hero & header polish (homepage)

Presentation-only update to the above-the-fold hero (`website/index.html`, `website/styles.css`); no routing, copy-claims, or documentation structure changed.

Navbar / brand
- Logo lockup rebuilt as a single clean unit: brand device (X + molecular ring) cropped from `code/logo.png` into a transparent `assets/logo-mark.png`, shown at a legible size with the wordmark and version chip as one vertically-centred unit (removed the small white “floating tile” crop of the full square logo).
- Footer brand uses the same mark on a white tile for dark-background legibility.

Hero
- Two-column hero: left = kicker → headline → concise description → four KNOW/REASON/DESIGN/DISCOVER capability blocks (numbered 01–04 cards with coloured top accents) → CTAs; right = full-height publication-style figure.
- New hero figure (inline SVG, brand palette): target protein + E3 ligase bridged by a PROTAC (warhead·linker·E3 ligand), ternary-complex envelope, module key and Ub → 26S proteasomal-degradation cascade, framed by the existing “fig window” topbar + caption, tagged ILLUSTRATIVE (not a measured complex).
- Install/quick-start command moved out of the copy column into a full-width bar between the hero grid and the stats band; hero note (“research system, not a demo”) kept under the figure.
- Typography hierarchy tightened (title scale/leading, description rhythm, spacing between title → description → capability blocks → CTAs) so the hero is balanced instead of text-heavy.

Responsive & hygiene
- Desktop: balanced 50/50 grid; ≤1080px: stacked hero (text first, figure below, centred, capped width); small screens: capability blocks 2×2, quick-start wraps, code scrolls horizontally inside its pill.
- Zero horizontal overflow at 320–1440px (document-root clip added; legacy `.demo-banner` tag allowed to wrap on phones; fixed replaced-element min-width so the SVG scales cleanly).
- Removed unused `.hero-logo-card` / `.framework-strip` / `.fw*` hero styles.

## v2.0 — scientific-coherence rewrite (2026-09-02)

Positioning and messaging
- Hero rewritten to: **"An evidence-grounded autonomous research system for targeted protein degradation"**; kicker now *AHUJA LAB · IIIT DELHI · TARGETED PROTEIN DEGRADATION*.
- Macro-framework **KNOW → REASON → DESIGN → DISCOVER** added as the primary scientific architecture (hero strip + dedicated capability section), replacing the software-centric "six scientific engines" framing.
- Removed marketing language: "Every invisible interaction, made visible by agents", "Feynman-grade", "zero black boxes", "AI magic", "final build".
- Release chip changed from "v0.3 · final" / "Final build" to **"v0.3 core release · active research development"**; About now separates software release status from scientific validation status.
- About section rewritten around: *PROTAC design is a coupled biological, structural and chemical optimization problem* (copy supplied by the lead developer), with author/affiliation cards and CI/status card.
- Figure caption no longer uses the "Fig 1" label; the hero visual is presented as a *system map* with evidence-type badges and a plain descriptive caption.

Architecture honesty
- Node accounting is now explicit and code-traceable: **23-node core scientific workflow + 8 controlled-search/feedback extensions = 31 documented agent nodes** (`agents/graph.py`), replacing ambiguous "31-node pipeline" phrasing.
- "Feynman contract" renamed to **The scientific contract** (auditable evidence/model gates).

Science-first sections added
- **Mechanistic layers** — "From ternary formation to cellular degradation": hook-effect modeler (equilibrium-only), lysine-ubiquitination feasibility (structural surrogate, real-PDB pending), cooperativity (feasibility, data-gated), degradation + cell-context (trained, transcriptomic; proteotype not claimed).
- **Model panel** — Module 4, Module 5, TACK (DC50/Dmax/binary), SynGlue (DC50/Dmax) kept independent with provenance + validation columns; unified engine explicitly **UNDER EVALUATION**.
- **Validation matrix** — per-capability statuses (VALIDATED BASELINE / TRAINED / PARTIAL / STRUCTURAL SURROGATE / DATA-GATED / UNDER EVALUATION / PLANNED) with evidence type, data source, validation, limitation and public-claim columns; driven by `config/scientific_status.yaml`.
- **Evidence-type badge system** — MEASURED / RETRIEVED / CALCULATED / LEARNED PREDICTION / STRUCTURAL SURROGATE / HEURISTIC / ILLUSTRATIVE / NOT AVAILABLE across cards, tables and captions.

Simulator honesty (credibility fix)
- "Live agent pipeline simulator" → **"Interactive pipeline walkthrough"**.
- Prominent **ILLUSTRATIVE DEMO — NOT A LIVE SCIENTIFIC PREDICTION** banner and per-row badges.
- Explicit disclaimer: browser-only, precomputed illustrative values; run the CLI/API for model-backed predictions.
- Walkthrough stages expanded to mirror the real system: KNOW retrieval & grading → REASON resolution → DESIGN (linkers, **retrosynthesis**, assembly, ADMET) → mechanistic layers (ternary, ubiquitination, cooperativity, hook effect) → DISCOVER (Module 4, Module 5, Pareto dossier).
- Candidate table relabelled "Illustrative Pareto-ranked candidates"; example DC50/ternary values now carry ILLUSTRATIVE badges and are described as examples.

Installation truth
- Removed `pip install protacxtend` and the curl installer (PyPI 404, no install.sh) — install tabs are now **git clone** and **docker** (`docker build -t protacxtend <repo-url>`), with a note "PyPI publishing on the roadmap".
- Workflows rewritten to the actual CLI subcommands (`design`, `structure`, `dose`, `context`, `validate`, `ask`/`learn`/`api`, `contract`).

Documentation hub (rebuilt)
- Six tabs: Getting started · **Technical assets** (databases, live APIs, tools, models, xlsx/csv assets, how to read them) · Modules & models (M1–M7 statuses + artifact paths) · Workflows & CLI · API & data · GitHub & collaborators.
- Repository links updated to the working repo; canonical organization repo (the-ahuja-lab/PROTACXtend) listed with status.

Branding / assets
- PROTACXtend logo (`code/logo.png`, now `website/assets/logo.png`) used in navbar, hero and footer; square favicon variant added (`logo-square.png`).
- Hero uses the logo card + framework strip; visual language kept (PROTACXtend palette, `#8683DD → #706BD6` signature gradient).

Related files touched in the same change: `config/scientific_status.yaml` (new source of truth), `SCIENTIFIC_CLAIM_AUDIT.md`, `SITE_COHERENCE_AUDIT.md`, `AGENTS.md`/`AGENT_WORKFRAME.md` ("Feynman" → audit/scientific-contract language), module tracker de-duplication (stale Module-3 row removed), README badge/install reconciliation, `documentation/WORKFLOWS.md` and `documentation/ARCHITECTURE.md` reconciled with the current CLI/modules.

## v2.1 — canonical hosting on the Ahuja Lab organization (2026-09-02)

- Final code mirrored to **the-ahuja-lab/PROTACXtend** (full history) after the org granted
  push access; the organization repository is now canonical for code, CI and Pages.
- All site links, install commands (git clone / docker), README badges (live site, CI) and
  the docs "GitHub & collaborators" pane now point to **the-ahuja-lab/PROTACXtend** and
  **https://the-ahuja-lab.github.io/PROTACXtend/**; SaveenaSolanki/PROTACXtend is listed as
  the development mirror.
- GitHub Pages on the org repository is enabled by the repository admin (Pages → Source:
  GitHub Actions); the deploy workflow is already in the repo and deploys `website/`.
