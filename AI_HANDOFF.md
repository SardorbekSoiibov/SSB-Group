# SSB Group — shared development handoff

Updated: 2026-11-03 (Asia/Tashkent). Read this file before changing code.

## Latest continuation checkpoint — supersedes earlier stopping point below

Continued Antigravity's latest `static/boshqaruv/entry.css` login-modal work.
Preserved its design and fixed concrete integration issues:

- `templates/accounts/_login_modal.html`: added the eyebrow and subtext classes
  required by the existing CSS; text and authentication behavior are unchanged.
- `static/boshqaruv/entry.css`: scroll overflowing modal content on short screens,
  visible keyboard focus for buttons, narrower mobile padding, 16px mobile input
  text to avoid automatic input zoom, and reduced-motion transition overrides.
- `templates/base_public.html`: entry.css cache version raised from 2 to 3.

PostgreSQL recovery issue resolved: starting the existing cluster using pg_ctl
outside the restricted sandbox succeeded. The earlier direct launch failed because
its startup process could not signal for checkpoint (Operation not permitted).
No cluster reset, deletion or data migration was needed. Server left running.

Validation at this checkpoint:

- `manage.py test apps --noinput`: 113 tests, OK, 1 skipped, 67.872 seconds.
  This includes the previous TaskForm regressions. Optional desktop journey was
  not enabled; do not claim a fresh Windows EXE acceptance run.
- `manage.py check`: zero issues.
- entry.css parsed successfully with the installed lightningcss parser.
- Login partial rendered successfully with the expected matching CSS classes.
- No browser visual verification was performed in this continuation.

Exact next action: visually verify public login modal at desktop and mobile
widths and short viewport height, keyboard focus, error state and password toggle.
Then verify project-dependent task selections in the current boshqaruv UI.
External integrations listed below remain pending. No Git repository is available
in this copy, so these changes were saved to files without a commit.

The sections below preserve the earlier inspection and implementation history;
their PostgreSQL/test-blocker stopping point has been resolved by this checkpoint.

## Project and location

SSB Group corporate website and company management system: projects, tasks,
employees, permissions, CMS, finance, reviews, archives and Windows desktop client.
The actual project root is the nested `oxirgi versiya` directory containing
`manage.py`; the parent directory contains only this project and a launcher.

## Architecture

- Django 5.2 / PostgreSQL; configuration in `config/`.
- `apps/accounts`: identity and capability-based roles; `apps/crm`: business
  models, forms, policies, workflows and views; `apps/enterprise`: finance,
  operations, APIs and dashboard; `apps/website`: public website and CMS cache.
- `apps/core`, `apps/audit`, `apps/notifications`: shared infrastructure.
- Django templates, Tailwind 4, Alpine, HTMX and locally vendored JavaScript.
- Current task pages use `templates/boshqaruv/operations/tasks/` and the
  `boshqaruv` shared layout. Older architecture documents predate this layout.
- Electron client in `desktop/` uses the same Django backend.

## Verified checkpoint and completed features

No previous AI_HANDOFF.md or AGENTS.md was found. No `.git` directory was found
in either the project root or its immediate parent, and Git is not on PATH.
Existing files cannot be classified as committed/uncommitted. No commit made.

`docs/DASHBOARD_REPLACEMENT.md` describes completed dashboard consolidation.
`docs/ECOSYSTEM_ACCEPTANCE.md` records prior desktop and business acceptance
testing (103 tests at that earlier checkpoint). Those historical results have
not been independently reproduced in this session.

## Current stage and latest changes

Task creation validation hardening:

- `apps/crm/forms.py`: TaskForm validates the submitted/initial project ID with
  its ModelChoiceField before using it to scope parent, dependency, milestone
  and assignee choices. Invalid IDs previously reached a raw integer PK filter
  during form construction and could raise ValueError/HTTP 500. Invalid values
  now leave dependent choices empty and produce normal field validation errors.
- `apps/crm/tests/test_workflow.py`: added regression coverage for malformed
  and oversized POST project IDs, absence of task creation, and malformed GET
  initial project IDs.
- `AI_HANDOFF.md`: introduced this shared checkpoint.

No model, migration, template, CSS or business data changes were made.

## Validation and exact stopping point

- `.venv/Scripts/python.exe manage.py check`: passed, zero issues.
- Python compileall for the two edited Python files: passed.
- Direct TaskForm probes with Project.objects.none(): passed malformed and
  oversized POST IDs and malformed initial IDs, without a database query.
- Full suite `manage.py test apps --noinput` could not connect to PostgreSQL;
  interrupted while waiting. Focused TaskLifecycleTests also could not initialize
  the test database. Integration tests are NOT marked passed.

Portable PostgreSQL was initially stopped. `pg_ctl start` failed with Windows
restricted-token error 87. Started `.pg/bin/postgres.exe` directly with a hidden
window and the existing `.pgdata` cluster. Its log shows crash recovery following
the previous unclean shutdown, REDO finished, but no ready-for-connections message
at the last check. Do not delete cluster files, reset WAL, reinitialize the cluster
or kill recovery to make tests pass. Startup logs:
`.setup/postgres-continuation.err.log` and `.setup/postgres-continuation.out.log`.
The server was left recovering; production records were not intentionally edited.

## Commands (PowerShell from project root)

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.crm.tests.test_workflow.TaskLifecycleTests --noinput
.\.venv\Scripts\python.exe manage.py test apps --noinput
.\.venv\Scripts\python.exe manage.py runserver
npm run build:all
Get-Content .setup/postgres-continuation.err.log -Tail 30
```

PostgreSQL is configured on 127.0.0.1:5433, database ssb. Keep credentials in
`.env`; never copy them into this file. Tests must use Django's separate test DB.
Build CSS only when styles/templates require it. No CSS build needed this stage.

## Remaining tasks / known limitations

1. Resolve/observe local PostgreSQL recovery and rerun the focused and full tests.
2. Once tests run, investigate actual failures before introducing new features.
3. Verify the current boshqaruv task create/edit UI in the browser, including
   project-specific dependent selections; this session did not browser-test it.
4. Historical external setup remains: SMTP, production Redis, real company
   content, AI gateway, antivirus executable, code signing and HTTPS update feed.
   Consult docs/ECOSYSTEM_ACCEPTANCE.md; do not invent credentials or claim these
   integrations are configured. Its installer upgrade acceptance is unfinished.

## Technical decisions / exact next action

Preserve the existing architecture, layouts, workflows and server-side policies.
Use the actual scoped project ModelChoiceField for validation; do not trust raw
IDs or broaden project visibility. No speculative redesign or new project.

Next action: inspect `.setup/postgres-continuation.err.log` and PostgreSQL process
state. When the server accepts connections, run TaskLifecycleTests, then the full
suite, and record exact results here. If recovery still stalls, diagnose it without
deleting or resetting the existing company database.

## Local launch — 2026-11-03
User requested application startup. Django launched hidden in the background using .venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload. Homepage and management entry respond HTTP 200. Logs: .setup/django-run.out.log and .setup/django-run.err.log. URL: http://127.0.0.1:8000/ .


## 3D globe hero — 2026-11-03
Replaced cube geometry in static/js/hero.js with a textured Three.js globe. Uzbekistan is mint green with Tashkent beacon, halo and label; initial view faces Central Asia. Preserved drag, keyboard, reduced-motion and visibility pause. Uses local static/vendor/world-countries.json (177 country outlines, Natural Earth public domain); attribution in world-countries.LICENSE.txt. Updated templates/website/home.html with globe fallback SVG and hero.js cache version. Node syntax and Django check pass; assets HTTP 200; headless Edge verified stage.is-live and screenshot visually inspected (.setup/globe-desktop.png). Label subsequently moved aside to avoid covering Uzbekistan. No backend/schema changes. Next: mobile visual/interaction review if further refinement requested.


## Realistic globe refinement — 2026-11-03 (latest checkpoint)
User requested a more creative, realistic globe. static/js/hero.js now loads locally vendored Earth surface, normal, specular and cloud maps from static/vendor/earth/. Uses terrain normals, ocean highlights, directional sunlight, hemisphere fill, independently drifting clouds and a softer atmosphere/shadow. Natural Earth country outlines remain a transparent overlay, with Uzbekistan filled mint. Toshkent beacon now connects to a scene-space coordinate label that hides on the back of the globe. Corrected apostrophe corruption using JS Unicode escapes. templates/website/home.html hero asset version is globe2. Texture source recorded in static/vendor/earth/ATTRIBUTION.txt. Node syntax and Django check passed; headless Edge WebGL live check and screenshots inspected at 1440x1000 and 390x844 (.setup/globe-desktop.png, .setup/globe-mobile.png). No backend changes; full backend suite not repeated for this visual-only refinement. Next: user visual review at http://127.0.0.1:8000/ (Ctrl+F5). Existing external integration tasks remain pending.


## Site-matched login modal — 2026-11-03 (latest checkpoint)
Updated static/boshqaruv/entry.css to match public site: frosted pale surface, navy/slate gradient CTA, Onest font, larger rounded inputs, subtle orbital decoration, toned focus and lighter blurred backdrop. Kept existing scoped CSS protection and responsive/reduced-motion rules. templates/accounts/_login_modal.html now uses SSB Group wordmark and submit arrow. templates/base_public.html entry.css version 4. Existing authentication handlers unchanged. CSS parser passed; all 5 ModalLoginTests passed. Desktop and mobile screenshots captured using headless Edge (.setup/login-modern-desktop.png and login-modern-mobile.png). Restarted only project runserver to clear compiled template cache; homepage HTTP 200. Server remains at 127.0.0.1:8000. Next: user review of login modal; prior integration tasks remain pending.


## Globe blended into site palette — 2026-11-03 (latest checkpoint)
User requested globe blend with page. static/js/hero.js now remaps photographic surface luminance into slate/silver using material.onBeforeCompile, preserving terrain detail. Softer cool lighting and brighter hemisphere fill remove harsh black night side; cloud opacity, atmosphere, shadow and floating motion reduced. Uzbekistan/beacon/leader use muted blue, label uses pale site surface with larger two-line text. Natural textures, geography, interactions and reduced-motion behavior retained. templates/website/home.html asset version globe3. Node syntax and Django check passed; headless Edge WebGL live checks at desktop/mobile passed, desktop screenshot inspected. Screenshot paths unchanged in .setup/. No backend/schema changes. Next: user visual review; hard-refresh homepage to bypass browser JS cache.


## Reference-style SSB logo — 2026-11-03 (latest checkpoint)
User supplied black slanted SSB GROUP reference. Created a vector reconstruction in static/img/ssb-group.svg using paths (no font dependency). Shared templates/website/_logo.html now renders this asset, inverted on dark backgrounds. Applied to public header/footer, loading screen, login modal, boshqaruv rail and standalone login branding; favicon.svg uses matching S shape. Files changed: new SVG, favicon, shared logo include, base_public.html, accounts/_login_modal.html, boshqaruv/base.html, boshqaruv/auth/login.html. 15 public-site/modal-login tests passed; Django check passed. Local server restarted to refresh template cache; desktop homepage and mobile login screenshots checked using headless Edge. SVG is manually reconstructed from supplied reference, not the original uploaded raster. Next: user review of logo matching; no uncommitted classification possible (Git unavailable).


## Uzbekistan map replaces globe — 2026-11-03 (latest checkpoint)
User requested Uzbekistan map instead of globe. static/js/hero.js now creates a beveled extruded map from the locally projected Natural Earth Uzbekistan outline. Slate/silver materials match the site, with subtle shadow, city dots and Toshkent halo/label. Drag/keyboard tilt is bounded so the map stays readable; reduced-motion/visibility pause preserved. New static/vendor/uzbekistan.json contains just the existing Natural Earth country geometry; source attribution remains world-countries.LICENSE.txt. Removed globe textures from the active scene but retained asset files to preserve prior work. templates/website/home.html now has matching geographic SVG fallback and asset version uzmap1. Node syntax and Django check passed. Headless Edge desktop/mobile live checks passed and screenshots visually inspected (.setup/globe-desktop.png, globe-mobile.png; historical filenames now show the map). Local runserver restarted for updated templates, left running. No backend changes. Next: user review at http://127.0.0.1:8000/.


## Logo rollback requested — 2026-11-03 (latest checkpoint)
Restored logos to their state before reference-style logo work: public wordmark include, text loader, SSB Group modal wordmark, original S-dot boshqaruv rail and standalone login branding. favicon restored from existing staticfiles/img/favicon.svg backup. New ssb-group.svg retained as an unused asset; no active template references it. Uzbekistan map and all unrelated UI changes preserved. Django check passed; local server restarted; homepage HTTP 200 with original wordmark and without new SVG reference verified. Next: user review; previous reference-logo checkpoint is superseded by this rollback.


## Creative map refinement — 2026-11-03 (latest checkpoint)
User requested a more creative map. static/js/hero.js now adds a floating outline layer behind the extruded map, a polygon-clipped dot lattice, five decorative curved connections from Toshkent to existing city points, animated light particles, a spreading capital halo, and Nukus/Buxoro/Samarqand labels. Site slate palette, original logos, bounded drag/keyboard tilt and reduced-motion behavior retained. Routes are decorative and do not represent live traffic or company offices. templates/website/home.html version uzmap2. Node syntax and Django check passed. Desktop/mobile headless Edge live checks passed and screenshots inspected (.setup/globe-desktop.png, globe-mobile.png). No backend/schema changes. Next: user visual review; Ctrl+F5 refreshes JS. Local server remains running.


## Modern layered map — 2026-11-03 (latest checkpoint)
User requested another modern creative refinement. Updated static/js/hero.js with deeper slate face, thicker beveled extrusion, translucent lower silhouette, bright perimeter, gentle shader-driven light sweep, raised city pins/rings, light connection arcs and dotted orbital guide. Toshkent label now has a navy background for contrast. Geometry overlays raised to match the new face depth. Kept original logos, geographic outline, interactions and reduced-motion freeze. templates/website/home.html version uzmap3. Node syntax and Django check passed; desktop/mobile headless Edge live checks and screenshots visually verified. No backend changes or new dependencies. Next: user visual review of live homepage (Ctrl+F5).


## Map contrast fix — 2026-11-03 (latest checkpoint)
User reported washed-out map. Darkened face to matte slate navy, reduced directional/hemisphere intensity and metallic highlights, reduced scan emission, increased route opacity and white city-label weight/size. Files: static/js/hero.js, templates/website/home.html (uzmap4). Node syntax passed; headless Edge live render passed and desktop screenshot inspected: map remains consistently dark and labels clearer. Prior layout, animation and logos retained. Next: user review, Ctrl+F5.


## Public site visual/motion refinement — 2026-11-03 (latest checkpoint)
User requested major modern creative polish without structural changes. Added static/css/studio-polish.css, linked after existing public styles in templates/base_public.html. Preserved all sections, routes, content and map/logo choices. Added cool gradient hero typography, restrained dotted background, glass header scrolled state, stronger CTA treatment, refined card borders/surfaces/shadows, image zoom, service arrow feedback, dark CTA/footer surfaces, selected option feedback and focused input outlines. Extended existing static/js/motion.js with body.is-scrolled in its existing scroll frame and one delegated/rAF pointer spotlight for cards on fine-pointer devices. Existing reveal/stagger/tilt/magnetic effects retained, reduced-motion disables added motion. New CSS is scoped to body.site; CRM unaffected. motion.js version3. Validation: CSS parsed; JS syntax passed; 24 website/modal-login tests passed (19.676s). Headless browser checked 15 section/viewport cases at 1440/768/390, no horizontal overflow, CSS loaded, reduced-motion animation none. Desktop/mobile screenshots inspected and CTA screenshot at .setup/studio-cta.png. Local server refreshed and left running. No backend/schema changes or dependencies. Next: user review of whole public site; remaining external integrations unchanged.


## Simplified login modal — 2026-11-03 (latest checkpoint)
User asked to remove unnecessary elements from screenshot of login modal. Removed eyebrow, explanatory subtitle, footer note/divider and decorative orbital rings. Kept SSB Group wordmark, title, credential fields, password toggle, validation errors, close and submit controls. Reduced logo spacing. Files: templates/accounts/_login_modal.html, static/boshqaruv/entry.css, templates/base_public.html (entry.css v5). All 5 modal login tests passed. Refreshed local server template cache; other site design and map untouched. Next: user review of simplified login.


## Site-wide 3D art direction — 2026-11-03 (latest checkpoint)
User requested full 3D appearance. New static/css/spatial.css defines dimensional layered surfaces, extruded card/button shadows, perspective card tilt, raised icons, a projected hero grid, and site-matched depth for header, portfolio, inquiry form, and dark panels. New static/js/spatial-scene.js uses the existing local Three.js module for one decorative background scene (torus, polyhedron, wire cage, orb), capped at ~30 FPS and DPR 1.25. Scene pauses when hidden, honors reduced motion dynamically and skips initial mobile/save-data devices. Lightweight CSS depth remains on mobile. Existing Uzbekistan map and original logos preserved. Extended existing motion.js card handler to reuse delegated/rAF pointer tracking for tilt, spotlight and cleanup; existing data-tilt controls retained. Avoided overriding sticky positioning. Linked assets globally in templates/base_public.html; motion.js v4. Shared public pages only, CRM unchanged. Validation: JS syntax and CSS parser passed; 24 website/modal tests passed in 23.102s. Browser checks: desktop/tablet/mobile, 15 section/viewport cases, no JS exceptions or horizontal overflow, reduced-motion animation none. Desktop/mobile and CTA screenshots inspected; simplified login checked. Seven public page routes return HTTP 200 with both new shared assets. Local server refreshed, left running. No schema/business-data changes. Next: user visual review at http://127.0.0.1:8000/ (Ctrl+F5).


## Lusion-inspired correction — 2026-11-03 (LATEST, supersedes spatial art direction)
User clarified reference is Lusion.co, not general 3D card decoration. Browsed https://lusion.co/ and inspected its loaded desktop appearance via headless Edge (.setup/lusion-reference.png). Reworked home hero into editorial heading above a wide dark interactive WebGL canvas. New original composition uses interlocking cobalt/porcelain/graphite rings and knots with environment lighting, drag/keyboard rotation, pointer response, idle/scroll motion. No Lusion assets copied. Uzbekistan map preserved behind accessible 3D sahna / O‘zbekiston view toggle. Existing sections, data bindings, routes, logo and simplified login remain. New files: static/js/immersive.js, static/css/immersive.css. Changed templates/website/home.html and templates/base_public.html; removed active references to spatial.css/spatial-scene.js (files retained unused). Immersive palette is lavender-white/cobalt/graphite; flattened old decorative extrusion. CSS fallback stays visible if WebGL unavailable, DPR capped and hidden/reduced-motion scenes pause. Validation: JS syntax/CSS parse/Django check passed. 24 website/modal tests passed (12.860s). Browser QA: 15 section/viewport cases at 1440/768/390, no JS exceptions/overflow, view toggle passed, reduced-animation none. Desktop and mobile screenshots inspected (.setup/immersive-desktop.png, immersive-mobile.png). Contrast/Unicode fixes and a small scroll-motion refinement applied after checks; final JS syntax and Django check passed. Local server restarted for latest templates and remains running. Next: user review at http://127.0.0.1:8000/ (Ctrl+F5).


## Restore structure; section-entry motion only — 2026-11-03 (LATEST)
User clarified: revert Lusion-inspired layout changes and retain original structure, add only section transition animations. Restored original two-column home hero (existing title/text left, Uzbekistan map right), captions and bottom line in templates/website/home.html. Removed active immersive.js/immersive.css references, no spatial backdrop loaded. Existing logos, palette, content, remaining sections and simplified login preserved. New static/css/section-motion.css applies gentle perspective/lift/opacity entries, stagger timing and heading-word easing without changing layout. static/js/public.js initReveal adds data-reveal/data-section-motion to existing main sections and reuses its existing IntersectionObserver (one-time entry, unobserved afterward); no scroll hijacking or duplicate loop. Focus-within forces visibility; reduced-motion shows all content without transitions. base_public.html uses section-motion.css and public.js v6. Previous immersive/spatial files retained unused. Validation: JS syntax/CSS parser passed; 24 website/login tests passed in 13.722s. Browser 15 section/viewport cases at desktop/tablet/mobile: no exceptions/overflow, reduced-motion none. Original hero/map screenshot inspected. Local server restarted and left running. Next: user review of original structure with section-entry transitions (Ctrl+F5).


## Stronger section motion — 2026-11-03 (LATEST)
User explicitly selected stronger animations, not smaller elements. Updated only static/css/section-motion.css and its cache version (v2) in base_public.html. Sections enter with more pronounced but restrained perspective/lift, card staggering at 90ms, heading words rise with slight rotation and capped delay, section-index line grows, hero eyebrow/title/lede/map enter in a coordinated sequence. Mobile uses vertical transitions; prefers-reduced-motion and focus visibility retained. No structure/content/map/logo changes. CSS parser and Django check passed; browser QA 15 section/viewport cases, no JS errors/horizontal overflow, reduced-motion animation none. Existing 24-test suite passed previous stage; not repeated for CSS-only edit. Next: user visual review of scroll transitions, Ctrl+F5. Local server remains running.


## Scroll-scrubbed section choreography — 2026-11-03 (LATEST)
User clarified again: Lusion-like changing transitions BETWEEN sections, original structure retained. Extended existing static/js/motion.js scroll rAF with active-section IntersectionObserver and ResizeObserver, assigning types to existing sections/children without wrappers. About/services slide in from opposing sides; portfolio aperture opens and content scales up; process approaches in perspective; team fans into alignment; inquiry settles into place; hero map/text have independent gentle drift. Progress follows actual scroll and reverses when scrolling back, no wheel interception/pinning/height changes. Product reel excluded to preserve existing sticky sequence. Existing reveal/stagger still handles inner content. Focus locks a section fully visible; dynamic reduced-motion disables transformations. Added corresponding CSS in static/css/section-motion.css. base_public.html: motion.js v5, section-motion.css v3. Validation: JS syntax, CSS parser and Django check passed; 24 website/modal tests passed (23.967s). Browser verified reverse scrub scale values [0.8899,1,0.8899], 15 desktop/tablet/mobile section cases with no JS exceptions/overflow and reduced animation none. CTA screenshot inspected (.setup/scroll-scenes-cta.png). Local server refreshed and left running. No content, routes, map or logo changes. Next: user should scroll down AND back up to review effect, Ctrl+F5 first.


## Cancel dark-only restriction — 2026-11-03 (LATEST)
User cancelled restricting animations to dark sections. Keep prior all-section scroll choreography. Disk filled during first write to motion.js and truncated it; removed only this session's generated QA screenshots inside .setup, then reconstructed motion.js with previous all-section logic and validated JavaScript syntax (5863 bytes). public.js, section-motion.css and template versions remained at previous checkpoint (public v6 / motion v5 / CSS v3), verified. Django check passed. No dark-only changes remain. No browser profile/test DB writes attempted after disk-space issue. Remaining environment limitation: C drive nearly full; avoid large builds/downloads until user frees space. Latest cancellation handled; next action only as requested by user.


## Creative loading screen — 2026-11-03 (LATEST)
User screenshot refers to the initial brand loading screen. Updated base_public.html loader markup and added static/css/loader.css: original SSB Group wordmark, three lightweight CSS orbital contours/nodes, soft blue glow, indeterminate line/dots and restrained baseline. Localization loader completion now plays a 650ms upward curtain using WAAPI and a once-only finish callback; reduced-motion removes immediately; readiness waits/delays unchanged. Fixed original issue where removing ssb-loading immediately hid the intended exit animation. localization.js version3, loader.css version1. No site-structure, map, section-motion or login changes. Disk initially had zero free bytes: safely removed only our .setup/edge-globe-check temporary browser profile (~52MB), used atomic source writes. Browser verification used disposable .setup/loader-qa then removed it, leaving ~109MB free. Validation: JS syntax/CSS parser/Django check passed. Browser normal+mobile reduced-motion: loader removed, scroll unlocked, ssb:loaded emitted exactly once, no exceptions/overflow. Screenshot inspected (.setup/loader-preview.png). Backend tests not repeated for loader-only change. Server refreshed and left running. Next: user refreshes page to review loading screen. C drive remains low on space; avoid large downloads/builds.


## Public entry button label — 2026-11-03 (LATEST)
User requested Kirish instead of screenshot's Boshqaruv paneli. Updated public desktop/mobile/footer account entry labels in base_public.html to Kirish for signed-in and signed-out states. Preserved existing destinations and authentication behavior. Django check passed. No backend changes.


## iOS management UI and persistent appearance — 2026-11-03 (LATEST)
User requested consistent, easy-to-use iOS-style management interface and Dark/Light modes. Updated frontend/boshqaruv-design.css with unified type/spacing/control sizes, consistent light sidebar and grouped surfaces, calmer metric/finance cards, responsive form/table layouts and complete light/dark semantic tokens. Added theme selector to templates/boshqaruv/base.html (Light, Dark, Tizimga mos) and new static/boshqaruv/theme.js. Head script resolves preference before CSS, persists in localStorage (ssb-boshqaruv-theme), follows OS changes in system mode, syncs tabs and tolerates storage failure. Theme menu is keyboard/focus accessible and closes outside/Escape. Standalone boshqaruv auth/login.html loads the same prepaint theme script. static/boshqaruv/app.js chart grid/ticks follow theme changes without altering data. Compiled static/boshqaruv/app.css via npm run build:workspace; app CSS/JS cache versions3. Public site styles and business policies unchanged. Last files: source CSS, compiled CSS, theme.js, app.js, boshqaruv/base.html, boshqaruv/auth/login.html.
Validation: full manage.py test apps --noinput: 113 tests, OK (1 optional Windows journey skipped), 80.720s. JS syntax and Django check pass; workspace CSS build passes. Browser QA 48 cases: 8 routes (dashboard, projects, tasks, task form, employees, finance, schedule, profile) x 3 widths (1440/768/390) x Light/Dark; no errors or page overflow. Verified preference reload persistence, OS Light/Dark changes, manual override, search dialog and mobile nav. Screenshots inspected: .setup/ios-dashboard-light.png, ios-dashboard-dark.png, ios-task-mobile-dark.png; results in ios-qa-results.json. Minor sidebar tagline/dark badge polish then rebuilt CSS. Used a temporary owner QA session without changing credentials/business rows, deleted it afterward and removed disposable browser profile. No real user sessions changed. Local server restarted for templates and left running.
Next action: user opens /management/enterprise/, Ctrl+F5; appearance control in topbar switches modes. Remaining external integration setup remains as earlier; original handoff's older blockers and UI descriptions are historical.


## In progress: queued management requests — 2026-11-03
Completed source changes for all queued requests: compact searchable sidebar with direct native links/immediate feedback; reusable iOS modal forms (create/edit/profile/password/finance) preserving server errors and uploads; read-only profile summary; readable Audit labels/date filters/expandable detail; UZS/USD choices via apps/core/currencies.py with legacy model records untouched; desktop User-Agent hides Windows download links inside Electron; clearer brand and 48px native Windows chrome. Main new assets: static/boshqaruv/navigation.js and forms.js. Changes in templates/boshqaruv/base.html/profile/audit and primary form markers, app.js reusable allocation binding, enterprise UI/forms/views, CRM forms/audit views, desktop chrome/main files. Source CSS compiled. Full existing suite 113 OK (1 skip), 5 new workspace UI tests passed. Browser final-ui-check.cjs passed native sidebar clicks, pending feedback, task project options, invalid-date errors with preserved input, profile/password/finance modals, currency choices, Audit, mobile dark sheet and desktop-UA link hiding. Visual review found and fixed desktop modal centering and oversized textareas. User business records were not saved during QA (invalid date only).
Installer update version2.0.1: first default build/download blocked; separate output desktop/release-next uses local .setup/electron-dist. Packaged app and NSIS archive are ready, installer compiler hit disk-space limit. To preserve sources/releases recovered space using hard links for identical non-executable runtime files between .setup/electron-dist and release-next/win-unpacked. Currently compressing original cached .setup/electron-dist/electron.exe into verified gzip (cell session36446); only remove original after SHA256 decompression matches. Next: finish compression, rerun prepackaged NSIS, verify package smoke, hardlink completed installer into desktop/release/ expected by config DESKTOP_VERSION2.0.1, clean temporary QA sessions/profiles, update final handoff. Existing open Windows application must not be force-closed. No completed Windows installer claim yet.


## Queued management work completed — 2026-11-03 (LATEST; supersedes in-progress note)
All queued requests implemented and verified. Sidebar uses real native links with immediate pending feedback, compact groups, name filtering and session scroll position. New navigation.js. No client route interception for sidebar. iOS record-dialog sheets support create/edit/project/task/employee/role, profile/password and inline finance/schedule/settings forms with full-page fallback, multipart uploads, CSRF, native validation, server error redisplay, preserved values, flash messages and focus restoration. New forms.js; primary form markers across boshqaruv templates. Allocation editor now reinitializes per modal via ssb:formready. Project-dependent task selects refresh without discarding input, cancel stale requests. Modal field IDs are namespaced; checkbox-group headings no longer produce invalid empty label-for attributes. Profile is an uncluttered read-only summary plus edit modal. Modal textareas/selects normalized, desktop centered/mobile bottom sheet.
Audit retained (security-required existing feature) with action labels, date/search/actor filters, accurate count, clearable filters and expandable pretty JSON details. Brand simplified into one-line SSB Boshqaruv + Ish maydoni. UZS/USD only for new operation/project/rule/settings choices via core/currencies.py and views; historical EUR model/ledger rows remain untouched, legacy project currency read-only. No migration changes. Windows link omitted from both sidebar/group and pinned footer when User-Agent indicates SSBDesktop or Electron; web keeps link.
Native Windows chrome uses consistent 48px title bar and BrowserView bounds, readable labels and controls, connection indicators and OS dark styling. main.cjs adds explicit desktop UA while preserving remote sandbox/no IPC. Version bumped in desktop/package.json/package-lock.json and config/settings.py to 2.0.1. Installer built, verified and available at desktop/release/SSB-Boshqaruv-Setup-2.0.1.exe (121660275 bytes). SHA256 file + release-manifest.json updated. Installer also hard-linked in release-next (ignored by Git). No code signing certificate/feed configured; no automatic update or installation into user's running app claimed.
Verification: existing full Django suite 113 OK (1 optional desktop skip), new WorkspaceUiTests 5 OK (repeated after final fixes); separately enabled packaged Windows journey passed for 2.0.1 (real login, web-to-desktop task change, desktop-to-web task change, protected download, logout, sandbox). Packaged hidden startup smoke passed, version2.0.1. NSIS embedded archive integrity: Everything is Ok; expected data-after-archive warning for executable wrapper. JS syntax, workspace CSS builds, Django check and migration dry-run passed. Final browser QA passed native navigation/immediate feedback, filters, task project refresh, invalid-date redisplay/no task created, profile/password modal, finance allocation binding, currency choices, Audit filters, mobile dark sheet, desktop UA link hiding, and modal label-to-control association. Corrected modal centering after screenshot review. Local server refreshed and left running with latest source/cache versions (CSS6, appJS4, formsJS3). Browser owner sessions and disposable QA profiles deleted; existing user sessions/business records unchanged.
Disk management: builds hit low space. Only disposable build/QA artifacts or reproducible caches were cleaned. Identical non-executable Electron runtime files used temporary hardlinks; generated win-unpacked and intermediate NSIS archives removed after verified installer. Original cached .setup/electron-dist/electron.exe preserved as SHA256-verified electron.exe.gz plus electron.exe.sha256; inflate before future electronDist builds if needed. For future packaged QA, extract the verified installer with 7za x into desktop/release-next/win-unpacked, then set SSB_DESKTOP_EXE to its EXE. Safely cleared only Cache/Code Cache/GPU/shader cache subfolders under project QA browser profiles (cookies/history/screenshots preserved) after disk filled again; recovered ~715MB at that checkpoint. Temporary credentials files removed. Existing installers and source assets preserved.
Exact next action: user opens http://127.0.0.1:8000/management/enterprise/ and Ctrl+F5, uses create/edit buttons and profile edit. Native title-bar changes require running/installing the new 2.0.1 installer; existing open app was never force-closed. No requested development task remains unfinished; production external integrations from earlier handoff remain outside this stage.



## Formal Windows connection screen - 2026-11-03 (LATEST)
User requested a more formal desktop startup/offline screen. Updated desktop/chrome.html, chrome.css and chrome.js: restrained navy company panel, readable connection card, explicit state badge and server address, separate retry/server-settings actions, responsive layout, complete OS light/dark colors and focus rings. Kept 48px native bar, existing window controls, trusted bridge and remote sandbox. Update notifications no longer overwrite body connection state. Loading/offline messages now distinct; malformed server labels handled without throwing. Existing architecture, management UI and public website unchanged.
Version 2.0.2 in desktop/package.json/package-lock.json and config/settings.py. Installer at desktop/release/SSB-Boshqaruv-Setup-2.0.2.exe, hard-linked from release-next; SHA256 and release-manifest updated. Built using 2.0.1 verified extracted Electron runtime and repacked app.asar, then NSIS prepackaged build. Existing open application not stopped or changed.
Validation: node syntax pass; hidden Edge connection-check.cjs: 24 cases (1440/800/390 x light/dark x setup/offline/loading/connected), no overflow/exceptions, correct visibility, retry/settings callbacks passed. Screenshot .setup/connection-preview.png inspected. Hidden packaged smoke: ok=true, packaged=true, version=2.0.2, sharedLogin=true, sandbox=true. No backend behavior change; full previous Django suites not repeated.
Run browser verification: node .setup/connection-check.cjs; packaged smoke node .setup/smoke-2.0.2.cjs (requires extracted runtime retained at .setup/installer-extract). New installer must be installed/launched to see this screen; old running installation remains unchanged. Exact next action: install 2.0.2 and review the connection screen. Disk remains limited; temporary extracted runtime can be removed only after QA closes; never remove source, data or existing releases.


## Windows navigation flicker fix - 2026-11-03 (in progress)
User reports workspace flashes off/on between sections. Root cause desktop/main.cjs did-start-loading called status(loading), which detached BrowserView on every page navigation. Removed that transition from ordinary navigation; explicit connect/retry still shows initial loading and real main-frame failure shows offline. Notification polling execution-context errors during navigation no longer falsely mark app offline. Added packaged smoke regression which loads another same-server page and verifies BrowserView remains attached at did-start-loading and completion. Hidden packaged 2.0.3 smoke passed: sharedLogin/sandbox/navigationAttached all true. Source syntax passed. Version bumped package/lock to 2.0.3. NSIS installer build running in release-next. Next: verify build completion, publish hardlink+SHA256+manifest, bump DESKTOP_VERSION, finalize handoff. Existing open app untouched.

## Windows navigation flicker fix completed - 2026-11-03 (LATEST)
2.0.3 installer built successfully at desktop/release/SSB-Boshqaruv-Setup-2.0.3.exe (hardlink from release-next), SHA256 file and release-manifest updated. config/settings.py DESKTOP_VERSION now 2.0.3. Source changes and packaged navigation regression verified; no Django business behavior changes. Tests: node --check desktop/main.cjs; node .setup/smoke-2.0.3.cjs confirms ok/packaged/sharedLogin/sandbox/navigationAttached all true. Ordinary document loads keep workspace attached, initial connect/retry and true main-frame offline behavior retained. Polling context loss during navigation no longer hides workspace. No router rewrite or artificial delay. No Git repository available. Exact next action: install the new 2.0.3 installer and review transitions; user's original running app was not stopped/modified. Previous 2.0.2 formal screen preserved.


## Workspace reset + installer fix - 2026-11-03 (in progress)
User explicitly authorized clearing business data except director to reenter it. Completed transactional maintenance reset with full gzip Django fixture backup + SHA256: .setup/backups/before-workspace-reset-20261103T125835Z.json.gz. Verified decompress/record counts before reset. Sole retained director User id1 ssbgroup, original password hash unchanged. Removed other employee, CRM/inquiries/projects/tasks/enterprise operations/schedules/notifications/audit/session rows; zero business rows verified. Preserved public website content, roles/departments/config/schema/uploads. Full reset script and counts .setup/reset-workspace.py and .setup/backups/reset-result.json. Earlier attempts rolled back entirely on FK/immutable checks; successful reset uses explicit TRUNCATE set including CRM M2M and only-empty external FK tables, no CASCADE/trigger disabling or application policy changes. No need to run reset again.
Installer issue: default electron-builder WMI path-prefix running-process detection can include setup itself; switching to exact executable nsProcess checks with explicit close prompt, graceful close then confirmed force cleanup/recheck, safe cancel on failure. New desktop/installer.nsh included from NSIS config. Uninstall now preserves client app data. Version2.0.4 source updated; next build/test installer, publish checksum/manifest/config version. No SSB processes were running when inspected.

## Reset and installer fix completed - 2026-11-03 (LATEST)
Business reset completed and verified: only director ssbgroup remains, same credentials; CRM and enterprise rows zero. Full verified pre-reset gzip fixture backup at .setup/backups/before-workspace-reset-20261103T125835Z.json.gz (+ SHA256). Preserve it; includes credentials, not for public sharing. Public content, role/department system config and uploads retained. All previous sessions cleared, so director signs in again. Temporary verification session removed after checks. Authenticated dashboard/projects/profile returned 200 with empty business database.
Installer2.0.4 built successfully: desktop/release/SSB-Boshqaruv-Setup-2.0.4.exe, hardlink release-next, checksum + manifest published, DESKTOP_VERSION updated. Exact-name nsProcess check replaces default WMI prefix detection; asks before closing app, waits/graceful close then force cleanup, allows cancel if still locked. Preserves client data on uninstall. New installer.nsh. Tests: NSIS build pass (removed unused-label compiler warning), isolated no-write installer harness in .setup/installer-process-qa.nsi/exe passed self-detection regression exit0; packaged2.0.4 smoke sharedLogin/sandbox/navigationAttached all true; WorkspaceUiTests5 passed; Django check passed. No actual installation into user's application or production-registry QA performed; user must run new installer. No SSB application process was running when checked. Old releases retained; only duplicate electron download parts removed to free disk. Exact next action: run 2.0.4 installer (cancel old setup first if still open), log in as existing director and enter new data. No repeat reset needed.


## Modern standalone login - 2026-11-03 (LATEST)
User requested a modern redesign of screenshot showing standalone management sign-in. Updated templates/boshqaruv/auth/login.html and scoped .auth-modern styles in frontend/boshqaruv-design.css; rebuilt static/boshqaruv/app.css. Login stylesheet cache7. Navy rounded brand panel, larger reliable headline, decorative CSS workspace visual (aria-hidden, no business data), uncluttered wider form, consistent 50px fields, theme selector using existing theme.js, password visibility toggle with aria-pressed/control via new static/boshqaruv/auth.js. Responsive compact brand on mobile, complete light/dark styles. Removed modal marker from standalone login form; native POST/CSRF/next/username/error behavior preserved. Corrected decorative icons to existing project/people/chart/shield catalog. Changes scoped to login; no dashboard/public structure or business data changes.
Verification: CSS build, node --check auth.js, Django check passed. Hidden browser .setup/auth-modern-check.cjs passed 8 viewport/theme combinations (1920/1280/768/390 x light/dark), no overflow/errors, headline/input sizing, password toggle, theme persistence and invalid-login error/username preservation. Screenshot .setup/auth-modern-dark.png reviewed. Server restarted after final icon adjustment; server-rendered login is shared by web and Windows, so no new Windows installer needed. Previous business reset remains complete; do not repeat it. Exact next action: refresh/reopen login page to view design.


## Formal login refinement - 2026-11-03 (LATEST)
User requested serious/corporate styling after modern login preview. Removed decorative faux workspace/chart markup and its CSS; replaced with three plain module labels. Changed headline to Kompaniya boshqaruv tizimi, form title Hisobga kirish. Solid charcoal/navy brand panel, square outer layout, calmer button without glow; retained theme choices, password toggle and native authentication/errors. Updated template app.css cache8 and rebuilt CSS. Only templates/boshqaruv/auth/login.html, frontend/boshqaruv-design.css and compiled static/boshqaruv/app.css changed. Django check/build passed. Re-ran auth-modern-check.cjs: 8 viewport/theme cases, password toggle/theme persistence/invalid-login errors all passed, no exceptions/overflow. Dark screenshot visually reviewed. Server refreshed. No database reset, credentials change or installer rebuild needed. Exact next: refresh login in web/Windows to review formal style.


## Login copy simplified - 2026-11-03 (LATEST)
User requested removal of unnecessary login text. Removed both eyebrow labels, descriptive paragraphs, module list, restricted-staff footer and account-help note. Retained logo, company system title, sign-in title, labeled inputs, password toggle, required validation errors, appearance controls and home link. Adjusted title/form spacing. Files login.html, source design CSS and compiled app.css (cache9). Build/Django check and existing 8-case auth browser check passed including password/theme/invalid-login behavior. Server refreshed. No data/credentials/desktop release changes. Next: refresh sign-in page.


## Claude takeover: archive two-step + messenger - 2026-11-04 (LATEST)
Claude took over from Codex. Codex's real stopping point was AFTER the last entry above: post-18:21 work (notifications, chat app, financial reports, global archive code) is documented in docs/ but was not in this file; its archive rework left 2 stale failing tests.
Archive (docs/ARCHIVE.md): one Founder code asked on EVERY visit (ArchiveVisitMiddleware relocks on real navigation away; background requests do not), RAR/ZIP only, author shown, math question per download (archive_access.new_challenge/check_challenge, template business/archive_download.html). The live archive code is NOT set yet: the Founder must set it on the archive page. Interpretation of "ikki bosqichli": step 1 code, step 2 math question.
Chat (docs/CHAT.md): rebuilt views/chat.js/chat.css; reply, edit, delete, forward, pin, reactions, files/images, presence, typing, search/jump. Migration chat/0002 applied to live DB after verified backup .setup/backups/before-chat-messenger-20261104.json.gz (+sha256; contains credential hashes, do not share). Group chats, voice and calls are NOT implemented.
Other fixes: PrivateStorage now follows override_settings and CompanyTestCase isolates private media (tests had leaked 54 files into private_media/attachments; moved to .setup/orphaned-test-attachments, zero DB references). forms.js corrupted "?" apostrophes fixed. QA scripts close Edge through CDP Browser.close (launcher exits, so child.kill left orphans that blocked test DB teardown). Legacy ArchivePolicy model left in place on purpose.
Validation: full suite with chat/report/archive/messenger browser tests: 181 OK, 1 skipped; the skipped packaged Windows journey then passed when run separately against desktop/release/win-unpacked. Windows client needs no rebuild: it loads the same server pages. A real .rar was not exercised by automated tests (ZIP used).
Launch note: Postgres does not survive a reboot; `.pg/bin/pg_ctl -D .pgdata -l .setup/postgresql.log -w start`. Do NOT run runserver with --noreload: that served stale code and showed the user the old archive page. Previous external integration items remain pending.


## Archive access modal - 2026-11-04 (LATEST)
User asked for the archive code screen as a modern modal. templates/boshqaruv/business/archives.html now renders #archive-gate (native dialog, rendered open, promoted by new static/boshqaruv/archive.js; Escape blocked) over a decorative blurred placeholder without data, plus #archive-code-dialog for Founder rotation inside the unlocked section. New static/boshqaruv/archive.css; bottom sheet at <=560px. ArchiveCodeForm uses auto_id archive_new_%s because it shares a page with the unlock form. Server rules, code hashing and URLs unchanged.


## Archive page redesign - 2026-11-04 (LATEST)
Unlocked archive is now stats strip + search/sort toolbar + project cards (#archive-list, .archive-card) instead of table and panels. "Loyiha qo'shish" opens the existing record-dialog through a data-record-template-source wrapper (#archive-upload), so forms.js multipart, error redisplay and upload_key behaviour are unchanged; archive.js adds the drop zone and a project-name suggestion. Sort whitelist ARCHIVE_SORTS in views. ProjectArchive.file_type is a property (no migration).


## Download question modal - 2026-11-04 (LATEST)
archive_download.html is now a modal (#archive-challenge) over the same decorative placeholder; closing it returns to the archive. Native POST is kept so large files stream without a browser blob. After a correct answer the response sets short-lived cookie ssb_archive_download=<client token> (alphanumeric only) so archive.js can switch to a "Yuklab olish boshlandi" state; previously the page stayed on a used question.


## Archive project removal - 2026-11-04 (LATEST)
User requested deleting projects. The immutable_history DB trigger on enterprise_projectarchive was deliberately NOT removed: new ArchiveRemoval table (migration 0005) marks a project removed, the stored file is deleted on commit, and archive.removed goes to audit. Always query through archive_access.active_archives(). Author or Founder only, unlocked visit, POST + CSRF, confirmation modal.


## Settings page + shared confirmation - 2026-11-04 (LATEST)
Settings page rebuilt as value cards plus honest connection states (previously raw "False", green badges for unconnected services and developer paths). Editing stays in the shared record dialog via data-record-template. `current` context is a fresh load because form validation mutates its instance. window.ssbConfirm({title,text,accept,danger}) in app.js now drives #confirm-dialog for data-confirm forms and chat; no native confirm() remains. Email/Telegram integrations are still NOT configured.


## Chat times - 2026-11-04 (LATEST)
Stored times were correct; display was the problem. chat.js now formats through Intl with data-time-zone (settings.TIME_ZONE) and derives Bugun/Kecha from the server clock (clockSkew from server_time). Workspace tabular-nums split digits in this font (1 6:47), so chat and archive cards use normal numerals; the rest of the workspace keeps tabular-nums. Messenger browser QA runs with a New York browser zone to guard this.


## Smooth section changes + sidebar brand - 2026-11-04 (LATEST)
Workspace pages use cross-document View Transitions (@view-transition, app-rail/app-topbar stay fixed, #content cross-fades); links stay native. Do NOT add speculation-rules prefetch: a prefetch is a navigation request and ArchiveVisitMiddleware would relock the archive. Page CSS moved to {% block head %} (was end of body and caused an unstyled first paint). Sidebar scroll restored by an inline script right after the nav. navigation.js adds a delayed progress line on beforeunload. Sidebar now shows one brand block; role remains in the account row.


## Windows page + sidebar logo - 2026-11-04 (LATEST)
User had the S-dot symbol removed from the sidebar only (login page keeps it) and explicitly said NOT to delete anything from the dashboard. business/desktop.html rebuilt as hero + feature cards with a download modal (#desktop-dialog, desktop.js/desktop.css, reuses .archive-modal). The unsigned-installer fact is kept as a plain SmartScreen note in the modal. Installer code signing is still not configured.


## Dashboard layout - 2026-11-04 (LATEST)
No dashboard content removed. Overview columns stretch to one bottom edge, widgets use auto-fit equal columns with fixed 300px height and internal scroll, activity widget shows audit labels instead of raw codes. ProjectArchive.__str__ added; old audit rows keep their stored "object (n)" text, which the widget hides. Browser QA asserts this at 1920/1440/1280.


## Compact top bar - 2026-11-04 (LATEST)
Top bar is now Yaratish + one icon group (search, appearance, notifications) + account. Removed the Avto label (kept sr-only for theme.js), Ctrl K chip (shortcut unchanged, shown in the tooltip) and the duplicate Tezkor amal dashboard button. Fixed a corrupted character in the account menu.


## Permanent deletion - 2026-11-04 (LATEST)
User chose full deletion protected by two steps, over keeping finance history. apps/enterprise/erasure.py erases an employee (Founder only, never an owner): account, chat, finance rows about them, reviews, shifts, archive uploads and files, comments, notifications, audit rows, public team card. Rows they only signed for others move to the Founder; their agreement share returns to the company so later receipts still split. Tasks, projects and task attachments stay, unassigned. Triggers remain active: migration 0006 lets them pass only when ssb.authorized_erase is set locally in the erase transaction. Use erase_mode() only after confirm_delete_password(). window.ssbSecureDelete and data-secure-delete drive the shared dialog. ArchiveRemoval was dropped; archive removal is a real delete. Chat message deletion keeps its single confirmation. Old backups in .setup and private_media/backups still contain erased data.


## Chat search, presence, verified badge, screenshots - 2026-11-04 (LATEST)
Chat search matches each word across name, username, role, job title and department, tolerates o‘/o'/oʻ, and covers every account; peer_for no longer hides inactive accounts, send() still blocks them. Presence is refreshed from the notifications poll, with last_login as fallback. User.is_verified is Founder-only (crm:employee_verify). User.allow_screenshots: Windows app uses BrowserWindow.setContentProtection from body[data-screenshots=blocked]; a browser cannot truly block screenshots, capture-guard.js only hides the page on focus loss, reacts to Print Screen and adds a name watermark.


## Windows 2.0.6 - 2026-11-04 (LATEST)
Installer desktop/release/SSB-Boshqaruv-Setup-2.0.6.exe built with --prepackaged from a repacked app.asar (.setup/repack.cjs; previous asar saved as .setup/app-2.0.5.asar). desktop/qa/capture.cjs proves the window reports protected=true for a restricted account and false otherwise, via capture-state.json written only in --qa-hidden mode. A real screenshot attempt was not performed; a cross-process GetWindowDisplayAffinity query returned 0 and is not usable. Backup before the erasure migrations: .setup/backups/before-erasure-20261104.json.gz (contains credential hashes).


## Verified badge position - 2026-11-04
Badge now follows the name (chat.js nameNode, chat/index.html, chat.css v5, chat.js v6); .chat-name-text truncates long names so the badge stays visible. After an unclean stop Postgres recovered by itself with pg_ctl; full suite 204 OK before this change, apps.chat 31 OK with browser checks after it.


## Profile, password dialog, weekly schedule - 2026-11-04
Profile (operations/profile.html, profile.css, profile.js): hero with photo; photo moved out of ProfileForm into crm:profile_photo (ProfilePhotoForm, preview dialog, remove, old file deleted after commit). User.photo_version is added to photo URLs because employee_photo is cached for 1 hour. Chat avatars now show photos (public_person['photo']).
Password: UzbekPasswordMixin translates labels and validator errors (also for SetPasswordForm); password-form.js adds show/hide and live hints; single column. Shared .record-body fields are 46px and no longer stretch.
Schedule (business/schedule.html, schedule.css, schedule.js): 7 equal day columns, week navigation, totals, add per day, edit in the record dialog through data-form-modal (the old edit link opened nothing). Employee is locked while editing: save_shift raised DoesNotExist if it changed. After saving, the page opens the shift's week. Periods over 42 days list only days with shifts.
Validation: full suite with browser and Windows flags 216 OK. app.css v14, forms.js v5, chat.css v6, chat.js v7.


## Clear notifications - 2026-11-04
crm:notification_clear deletes the signed-in person's own notifications behind the two-step password dialog; audit action notifications.cleared. Deadline reminders are recreated by polling, so clear_notifications stores today's dedupe keys in ClearedReminder (ids only, purged on later clears); notify() skips them, and tomorrow's keys differ. Migration notifications/0003 applied live after backup .setup/backups/before-cleared-reminder-20261104.json.gz (contains credential hashes). Full suite with browser and Windows flags: 222 OK.
Live data note: the Founder erased employees 3 and 4 at 19:41 and 19:46 through the UI (audit user.erased), which is why chat messages fell from 13.


## Reviews, project page, project deletion, schedule for everyone, SSB AI - 2026-11-04
Review dialog: presets, period errors at the field, default this month. Page no longer shows the AI gateway warning; real AI still needs PERFORMANCE_AI_ENDPOINT and PERFORMANCE_AI_KEY. .prose colour was hardcoded and unreadable in dark mode on 16 templates; now var(--ink).
Project page rebuilt (project.css). erase_project in apps/enterprise/erasure.py: Founder only, two-step, deletes tasks, files, finance rows (balances change, shown in step one), archives, audit rows; records project.erased with code and name. Published portfolio entries stay (SET_NULL); linked inquiries stay.
Schedule menu item is now in Ish maydoni for everyone; employees see only their own shifts; only schedule.manage can add.
SSB AI (apps/enterprise/schedule_ai.py, schedule-ai.js): rule-based Uzbek parser, NOT an external model. Proposes shifts, saves only after the manager confirms; apply() goes through operations.save_shift.
Validation: full suite with browser and Windows flags 252 OK.



## Ranking for everyone - 2026-11-04
Jamoa reytingi is in Ish maydoni for all staff. Ranking shows approved totals company-wide; comments and analysis remain visible only to the person and managers.


## Weekly rating - 2026-11-04 (structure given by the user)
apps/enterprise/weekly_rating.py, page enterprise:rating (Haftalik reyting, everyone). A week runs Sunday 00:00 to the next Sunday 00:00 and is published at that moment; before it only performance.manage holders see it. SSB AI lists each person's accepted tasks, projects, delays, corrections from real records and suggests an order (rule-based, formula shown on the page); the boss picks places and writes the 1st place prize. A published week is locked; the week just closed can still be set if nobody was placed, and publishes on saving. announce_due runs from the notification poll and uses WeeklyRating.announced, so clearing notifications cannot repeat it. Founder is not rated. Migration enterprise/0007 applied live after backup .setup/backups/before-weekly-rating-20261104.json.gz. Periodic reviews stay under Jamoa bahosi va AI.



## Public site rebuilt from scratch (iOS style) + company-wide panel colour - 2026-11-12 (LATEST)
Public site: new templates/base_public.html, all templates/website/*, accounts/_login_modal.html; new static/site/ios.css + ios.js (old site.css/site.js, dist/app.css, entry.css no longer linked on public pages). iOS System Blue only, automatic light/dark, CSS 3D hero (iPhone + floating widgets, pointer/scroll tilt), segmented product showcase, iOS grouped-list inquiry wizard (same Alpine logic/field names), iOS alert success dialog. Hero title/statement are NOT split into word spans so localization.js can translate whole sentences; 75 new rows in static/js/languages.tsv, "yana N belgi" handled in localization.js. Test markers kept: data-hero-stage, hero-poster, member-card, "Loyiha boshlash". PUBLIC_INPUT in website/forms.py is now the "input" class.
Panel colour: WorkspaceSettings.accent_color (migration core/0003, default #007aff). POST crm:settings_accent, owner (Asoschi = director) only, audit settings.accent. Picker in account menu only for owner; colour served via <html style="--accent-custom">; theme.js no longer stores per-user colours. static/boshqaruv/accent.css (loaded last, also on auth pages) maps buttons, icons, active nav, KPI, progress, focus, chat, charts to the accent; status colours stay semantic. Tests: apps/crm/tests/test_accent.py.
NOT VERIFIED: Postgres crashed (orphan bgwriter left, postmaster.pid gone) during this session; restart was not permitted, so migrate + test suite were not run. Verified only: manage.py check, makemigrations --check (no changes), 32 templates compile, JS syntax, headless screenshots of DB-free renders (desktop light/dark, 390px mobile, contact).
Next: restart Postgres, run `manage.py migrate`, then `manage.py test apps --noinput`.


## Management panel restyled to match public iOS site - 2026-11-12 (LATEST)
Design-only: new static/boshqaruv/ios-panel.css (v2) linked before accent.css in boshqaruv/base.html and standalone auth pages. No template structure, JS, views or section order changed. Same tokens as static/site/ios.css: #f2f2f7/#000 canvas, #fff/#1c1c1e cards, iOS label colours, Onest/SF font (numbers no longer mono), capsule glass topbar, glass rail with blue S mark, tinted secondary buttons, iOS filled inputs (letter-spacing reset), sheet dialogs, glass menus/toasts. Postgres restarted (orphan bgwriter stopped with user permission), migration core/0003 applied, dev server at 127.0.0.1:8000. Verified by owner-rendered screenshots (dashboard light/dark, projects, new project, settings, chat, 390px mobile). Known: CompanyTestCase fixtures expect roles "Bosh direktor"/"Xodim" that bootstrap_company no longer creates (since 11-10), so the Django test suite cannot set up - pre-existing, not fixed. Production waitress (8080) not restarted.


## Announcements with images + link button; iOS notification center - 2026-11-12 (LATEST)
crm.Announcement gained link_label/link_url (http/https only, label requires URL); new AnnouncementImage (private_storage, RandomName("announcements"), downscaled, post_delete removes file on commit). Migration crm/0005 applied live. AnnouncementForm.images = MultipleImageField (unlimited count per post, JPG/PNG/WebP, 8 MB each; Django still caps one request at DATA_UPLOAD_MAX_NUMBER_FILES=100 files). Images served only via crm:announcement_image (announcements.view|manage, also in capability_gate). New templates/boshqaruv/operations/announcements.html (feed cards, 1/2/3/4+ gallery with +N and lightbox, link button, composer with drop zone/previews/remove, live button preview, iOS switch) + announcements.js/css v3. Notifications page redesigned only (same forms/actions): grouped by day, kind icons, unread dot, new notifications-page.css. Tests: apps/crm/tests/test_announcement_media.py (7 OK, standalone, not using broken CompanyTestCase). Verified screenshots with rollback-only sample data.


## Employee page redesign, 3D badge + PDF + QR verification, announcement delete - 2026-11-12 (LATEST)
Employee detail (templates/boshqaruv/operations/employees/detail.html, static/boshqaruv/employee-detail.css v2, employee-badge.js): iOS contact card with quick call/Telegram/mail/badge buttons, stat tiles, open tasks list (open_task_count added), same actions/forms as before. 3D CR80 badge (front: photo/name/title/dept/ID; back: QR), click/keyboard/drag to flip, no lanyard. apps/crm/badges.py: badge_id = SSB-{pk:04d} (no migration), QR = signed URL (Signer salt ssb-employee-badge) to public /xodim/<token>/ (badge_verify, noindex, robots Disallow) showing CURRENT status (non-active => "Bedjik amal qilmaydi"), photo only for active via /xodim/<token>/rasm/. PDF: crm:employee_badge_pdf (reportlab, A4, real size 54x85.6 mm front+back with crop marks, Segoe UI TTF fallback Helvetica). verify_url uses SITE_URL unless localhost, else request host (SITE_URL is not set in .env). Announcements: crm:announcement_delete (POST, author or owner, confirm dialog with danger style via data-confirm-danger; app.js v9 passes danger flag), audit announcement.deleted. Tests: test_badge_and_delete.py, test_announcement_media.py, test_accent.py rewritten standalone: 18 OK.


## Weekly performance rebuilt + employment contract + equipment empty state - 2026-11-16 (LATEST)
Baholash va reyting (enterprise:performance, one page; enterprise:rating redirects there). Week Mon 00:00 - Sun 23:59 Asia/Tashkent; everyone active except owner/superuser is rated. During the week performance.manage holders give each visible employee (not self) a 0-100 score + comment (new ManagerWeeklyScore, migration enterprise/0013). Monday 00:00 performance_system.close_week(): collect() evidence, Claude analysis per employee (anthropic SDK, ANTHROPIC_API_KEY + PERFORMANCE_AI_MODEL default claude-opus-5-5, structured JSON, may shift the 4 rule criteria by at most +/-15, falls back to the formula on any error), manager score folded in (missing => manager weight dropped and the rest renormalised, row marked "rahbar baholamagan"), rows created already approved and the week published in one transaction (fits the 0009/0010 DB guards), notifications "Haftaning eng faol xodimi" on commit. A week with zero accepted tasks company-wide is skipped (no ranking). Triggers: deploy/serve.py start_scheduler() (30 s loop) + ensure_closed_async() from the notification poll and the page (catch-up), pg advisory lock 7310001 so only one process closes. process_weekly_performance command now calls close_week (--actor optional). NOT live-tested against the real Claude API (no key in .env); parsing/clamping/fallback tested with stubbed responses; full flow tested rollback-only on the live DB. xd and xamid lack performance.self, so they are rated but cannot open the page until the founder ticks it.
User gained contract (private_storage, contracts/), contract_number, contract_signed_on, contract_ends_on (migration accounts/0010). Upload validated by extension + magic bytes, 15 MB. Separate "Mehnat shartnomasi" panel in the employee form (replace / remove; old file deleted on commit), row on employee detail (can_view_contract) and own profile. Download crm:employee_contract (self, owner, or a manager who can manage that employee), audited user.contract_downloaded; erase_employee deletes the file.
Equipment mini list empty state used .ep-empty from employee-detail.css, which the profile page does not load; now .eq-mini-empty in equipment.css (v=4).


## Telegram bot admin panel + Hackaton e'lonlari - 2026-11-16 (LATEST)
Bot (@ssbcrm_bot) logic now lives in apps/notifications/bot.py. Long-polling listener thread ssb-telegram-bot (runtime._bot_loop) with pg advisory lock 73910249 so only one process calls getUpdates; started by deploy/serve.py and lazily from the notification poll (api.notifications) and the connections page. channels.poll_once() handles each update in its own transaction and saves the offset per update; poll_telegram() is a one-shot that does nothing while the listener holds the lock. allowed_updates: message, callback_query, my_chat_member.
Admins: TELEGRAM_ADMIN_IDS in .env (owners, cannot be removed via bot, read live via configuration.value) + TelegramAdmin rows added in the bot. Admin panel (inline menus edited in place): post (choose channel/all -> text/photo/video/animation with entities -> "Tugma qo'shilsinmi?" -> name + URL, up to 8 -> preview -> send, double-send guarded), channels (add by @username/t.me link/forward or automatically when an admin promotes the bot; removed when bot is kicked), admins (add by ID or forwarded message, remove). New models TelegramAdmin, TelegramChannel, TelegramBotState, TelegramPost (migration notifications/0007). Notifications to Telegram are HTML with kind icon and a "🔗 Ochish" URL button (only when SITE_URL is a real domain; localhost gives no button; on 400 the message is resent without the button).
Announcements section renamed "Hackaton e'lonlari" (menu icon spark). Announcement gained event_date, registration_deadline, location, prize (migration crm/0008), shown as fact tiles with "N kun qoldi". User.is_hackathon_staff (job_title matches ha[ck]at(h)on) => has_cap grants announcements.view/manage. Optional "Telegram kanallarga ham yuborish" posts via bot.post_announcement (first image uploaded multipart by channels.telegram_upload + URL button). Tested offline with a faked Telegram API and rollback-only DB; NOT tested against live Telegram yet (no admin ID provided).


## Modern dropdowns + "Nega SSB Group" redesign - 2026-11-16 (LATEST)
static/js/ssb-select.js + static/css/ssb-select.css, loaded in boshqaruv/base.html and base_public.html. Closed <select> keeps its existing styling; mousedown/Space/Enter/Alt+Down opens a custom listbox instead of the OS list (check mark, keyboard nav, typeahead, search when >9 options, optgroups, disabled options), then sets selectedIndex and dispatches input+change (so onchange auto-submit filters still work). Inside an open <dialog> it uses popover="manual" (top layer); elsewhere it is a fixed div on body. Skipped on touch devices (pointer:coarse), for multiple/size>1/disabled selects and inside [data-native-select]. Verified in real Chrome (equipment filter, modal select, Esc keeps the dialog). Note: headless Chrome --screenshot does not paint this panel even though it is laid out and hit-testable, so use a real browser to check it.
Home "Nega SSB Group" (templates/website/home.html .why*, styles appended to static/site/ios.css v7): sticky intro (lead, badges from reasons/process counts, CTA) + numbered reason cards; old .bento markup no longer used. RU/EN rows added to static/js/languages.tsv.
The earlier panel-wide "polish" pass (polish.css, forms.js single-panel change, username help text) was reverted at the user's request.


## Cleanup of unused files - 2026-11-16 (LATEST)
Deleted at the user's request after a reference scan (project ~6.5 GB -> 0.8 GB): 370 test/QA leftovers in .setup (browser profiles, electron build dirs/zips, postgres installer archives, old logs/screenshots), desktop/release installers 1.0.0-2.0.5 + win-unpacked + builder-debug.yml + stale latest.yml, desktop/release-next, .venv.old, dump.rdb, root __pycache__, and 39 unreferenced static/template files (old public-site CSS/JS: site.css/site.js/hero3d.js, static/js motion/public/hero/immersive/spatial-scene/auth-scene, 13 static/css files, vendor/earth, world-countries.json, overview.css, schedule-ai.js, empty auth.js, weekly-performance.css, static/audio, templates performance_empty/performance_weekly/rating_weekly/reward_form/_performance_nav, dashboards/_tasks, website/_product_scene).
Kept: .setup/backups, .setup/*-backup-* code snapshots and backup zips, .setup/postgresql.log, desktop/release 2.0.6 installer + sha256 + release-manifest.json, static/dist/app.css (used by password_reset pages).
Verified: manage.py check, all templates compile, 69 pages render (owner + anonymous) without 5xx, all 96 linked /static/ files resolve.
Note: tests test_windows_journey/test_windows_capture default to desktop/release/win-unpacked/SSB Boshqaruv.exe; set SSB_DESKTOP_EXE or rebuild the desktop app to run them.
