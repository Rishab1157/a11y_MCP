# a11y MCP — handover

Context for an agent or developer picking this project up cold.
Last updated 2026-10-06.

---

## What this is

An **MCP server that audits web pages for accessibility**, driven by Selenium.
It exposes 9 tools over `streamable-http` on port 8081. An LLM agent calls the
tools; the server owns the browsers.

It is a deliberate rebuild of an older CrewAI pipeline
(`Desktop/ai-accessibilityTesting`) whose stages largely did not work. Do not
copy patterns from that repo.

**The goal:** a generic, application-independent accessibility scanner, tiered:

| tier | what | status |
|---|---|---|
| 1 | Static semantics — accessibility tree + axe rules | tree **done**, axe **not started** |
| 2a | Keyboard reachability | not started |
| 2b | Screen-reader sampling | not started |
| 3 | Interaction / live regions | not started |

`run_axe` is the single biggest outstanding piece. Tier 1 has been half-built
for weeks.

---

## Repo layout

```
main.py                     the 9 MCP tools (FastMCP)
Settle.py                   THE settle primitive — lives at root on purpose (see below)

Config/DriverConfig/        pydantic browser configs, discriminated on "browser"
Config/DriverConfigBuilder/ config -> selenium Options -> driver, one builder per browser

Auth/                       5 auth modes: none, token, api, form, storage
Session/                    session registry, arrival verification, auth-scheme detection
Session/Workflow/           the workflow engine: Models, Resolver, Actions, Expectations, Executor
Scan/                       accessibility-tree readers (Chromium via CDP, Firefox via DOM walk)
```

### The 9 tools

```
create_driver           open a browser session, returns session_id
close_session           close one
list_sessions           count of open sessions
navigate                go to a URL and VERIFY arrival
authenticate            apply credentials, verify against a state-free page
get_accessibility_tree  the scan
resolve_target          probe whether a Target matches exactly one element
run_steps               drive a sequence of UI actions
reach_state             get the app into a state, then confirm it
```

### Running it

```bash
cd a11y_MCP
./.venv/Scripts/python.exe main.py        # Windows
# serves streamable-http on http://0.0.0.0:8081/mcp
```

Python 3.13, selenium 4.49, fastmcp 4.0.3. Logging goes to **stderr** — stdout
is block-buffered when it is not a terminal, which is why `print()` appears to
do nothing. `logging.basicConfig(stream=sys.stderr)` is set in `main.py`.

**Restart the server after every code change.** It holds browsers and imported
modules in memory; a stale process silently runs old code, and that has already
cost hours once.

### Typical call order

```
create_driver(browser="edge")           -> session_id
navigate(url)                           -> reached_target?
  └ false + failure_kind="auth"         -> authenticate(...)
  └ false + failure_kind="prerequisite" -> reach_state(url, steps=[...])
resolve_target(target)                   probe before building a workflow
run_steps(steps, dry_run=true)           then dry_run=false
get_accessibility_tree()                 the scan
close_session(session_id)
```

`get_accessibility_tree` **refuses** unless `reached_target` is set and the
browser is still on the verified page. That guard is deliberate: scanning a
login page and reporting it as the application is the failure mode the whole
verification layer exists to prevent.

---

## Environment constraints — read this first

**Chrome does not work on the original dev machine.** Windows **Smart App
Control** is enforced and blocks `chromedriver.exe`, which Google does not
code-sign:

```
OSError: [WinError 4551] An Application Control policy has blocked this file
```

Not a corporate policy — SAC ships in evaluation mode and promotes itself.
Turning it off is one-way (requires reinstalling Windows). **Use Edge instead:**
same Chromium, same CDP, `msedgedriver.exe` is Microsoft-signed, Selenium
Manager fetches it automatically. `ChromiumAxTreeReader` is registered for both
`chrome` and `edge` and needs no changes.

Verify on a new machine before assuming it applies:
```powershell
(Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy).VerifiedAndReputablePolicyState
# 0 = off, 1 = enforced, 2 = evaluation
```

**Firefox needs `enable_bidi = True`** (set in `FirefoxOptionsBuilder`). Selenium
removed CDP from Firefox, so the settle hooks install over WebDriver BiDi, which
only exists when `webSocketUrl` was requested at session creation.

---

## The architectural decisions that matter

### 1. One settle primitive, at the repo root

`Settle.py` is at the root, **not** inside `Session/`, because both `Auth` and
`Session` import it. Putting it in either package creates a circular import:

```
Auth/__init__ -> AuthProvider -> Session/__init__ -> Verification -> Auth (half-built)
```

`Settle.py` imports only `time` and selenium — nothing from the project — so no
package can cycle through it. **Keep it that way.**

`wait_until_settled()` watches three signals together:
- **URL stability** (the one that decides the result)
- DOM node count
- in-flight `fetch`/`XHR`, via hooks installed by `arm_settle_hooks()`

`arm_settle_hooks()` must run once per session right after `create_driver`. It
installs a counter that runs **before any page script**, via CDP
`Page.addScriptToEvaluateOnNewDocument` (Chromium) or
`script.add_preload_script` (Firefox BiDi). Without it, a request fired during
page parsing is invisible and the settle returns too early.

Check `preloaded` in the settle result: `false` means arming silently failed and
`inflight` means nothing.

A weaker `Scan/PageReady.py` (DOM count only) was **deleted**. Do not reintroduce
a second waiter.

### 2. Targets are located by accessible name, not CSS

`Session/Workflow/Models.py` — `Target(name, role, within, nth, css)`. A target
that cannot be found by accessible name **is itself an accessibility finding**:
a screen-reader user could not identify that control either.

`Resolver.find_all` matches names **exactly** (whitespace-normalised, lowercased).
On a miss it settles once and retries — from a single pass, "does not exist" and
"has not rendered yet" are indistinguishable.

### 3. Action and assertion are separate

`Step` performs, `Expect` verifies. An action must never read back its own
result — a controlled React component updates on re-render, not on click, so an
immediate read returns the pre-click value. `verify_all` re-resolves on every
poll and waits to `expect.timeout`.

**`Expect.target` is never inherited from `Step.target`.** After an action the
step's target may not exist any more.

---

## Reference — the parts worth reading closely

### The workflow model (`Session/Workflow/Models.py`)

```
Target  WHICH element     name, role, within, nth, css
Step    WHAT action       click, fill, ensure_checked, ensure_unchecked,
                          press, hover, scroll_to, navigate  + expects[]
Expect  HOW we know        state, text_changed (element-level, need own target)
                          appears, disappears, text_contains (page-level, no target)
```

Expectation strength, strongest first:
`state` > `appears`/`disappears` > `text_contains` > `text_changed`.

Validator rules, enforced in `_check_shape`:
- `state` and `text_changed` **require their own `target`**
- `appears`, `disappears`, `text_contains` **forbid** a target — they carry
  their own locator
- an `Expect` must assert *something*

`Target` resolution order: `within` → `name`/`role` → `css` → `nth` → ambiguity
check. **`css` is a filter, not a bypass** — an earlier version returned early on
`css` and silently ignored `name`/`role`. `nth` is always last so it indexes the
fully filtered list.

**Pydantic gotcha, already hit once:** `Optional[int] = Field(ge=0, …)` with no
positional default makes the field **required**. `Optional` means "None is a
valid value", not "you may omit it". `nth` had this and every `Target` was
rejected until it became `Field(None, ge=0, …)`.

### Auth modes (`Auth/AuthConfig.py`)

| mode | when | catch |
|---|---|---|
| `none` | public page | — |
| `api` | app exposes a login endpoint | the POST runs in Python, not the browser — cookies and token must be carried over explicitly |
| `token` | you already hold one | works with SSO and MFA, since the token is obtained outside the tool |
| `form` | visible username+password | cannot pass SSO, MFA or CAPTCHA |
| `storage` | replay an exported real session | expires like a token |

`detect_auth_scheme` ranks the usable modes on a failed arrival. **Always verify
auth against a page that needs no application state** — otherwise a bad token
and an unselected project are indistinguishable.

`USERNAME_GUESSES` ends with `input[type='text']` as a last resort, which can
match a header search box on a half-rendered page and type the username into it.
The settle makes that unlikely, not impossible; scoping the username lookup to
the password field's `<form>` would close it properly.

### Role vocabulary (`Scan/Roles.py`)

Chrome's CDP tree uses its own role names, so `CDP_TO_ARIA` normalises them
**before** any filtering, and every downstream check speaks ARIA. The mapping was
harvested from ~15,000 nodes across Wikipedia, MDN, GOV.UK, GitHub, BBC News and
the W3C WAI pages.

Decisions in there that are not obvious:
- `LayoutTable`/`LayoutTableRow`/`LayoutTableCell` → `generic`. They are **not**
  data tables; mapping them to `table` would raise a false "unnamed table" for
  every layout table on the page.
- `StaticText` is folded into its owner's text, never emitted.
- `InlineTextBox` is dropped — it sits *below* StaticText at line-fragment
  granularity, so folding both duplicates every string. It is also the single
  most common node type in the tree.
- `generic` is dropped **unless it carries text of its own**. A wrapper div is
  noise; one holding "ALM CONNECTIONS" is content.

### The two readers (`Scan/`)

**Chromium** (`ChromiumAxTreeReader`) — `Accessibility.getFullAXTree` over CDP.
Ground truth: the exact tree the browser hands to assistive technology. Three
passes: index by `nodeId` (ignored nodes included, so parent lookups resolve),
fold `StaticText` onto the nearest surviving ancestor, then emit.

**Firefox** (`FirefoxAxTreeReader`) — Firefox exposes no equivalent tree, so this
computes one from the DOM using a **vendored `dom-accessibility-api` bundle**
(`Scan/vendor/`), injected by `DomA11yLoader` as a blob plus a dynamic
`import()` via `execute_async_script`. It walks the DOM, piercing shadow roots.

Known Firefox gaps:
- **No visibility checks** for zero-size or clipped elements — this produced 399
  phantom links on one site.
- `getRole()` returns `null` for `<svg>`/`<canvas>`; patched to `img`, but other
  embedded content may still fall through.
- The ESM loader is **blocked by CSP** on strict sites (MDN, GitHub, GOV.UK). An
  IIFE variant was written and works everywhere; the user chose to defer it.

**Measured agreement** across 12 public sites: 90.7% recall, 68.4% precision,
69.2% findings agreement. On the user's own app: **100% / 100%** (18/18
interactive elements, 8/8 findings). The public-site gap is mostly the Firefox
visibility gap above.

---

## What was fixed, and why (the DOM-stability arc)

The whole project was unreliable because **`driver.get()` returns at
document-ready, while a React app redirects afterwards**. Symptom: everything
worked under a debugger and failed at speed, because pausing gave React time.

Every DOM read now settles, retries, or polls:

| where | file |
|---|---|
| after every action | `Session/Workflow/Executor.py` |
| on a resolution miss | `Session/Workflow/Resolver.py` |
| before judging arrival | `Session/Verification.py` |
| before hunting login fields | `Auth/AuthProvider.py` |
| before injecting credentials | `main.py` (`authenticate`) |
| before reading the a11y tree | `main.py` (`get_accessibility_tree`) |

Related fixes worth not undoing:

- **`verify_arrival` samples state AFTER waiting, never before.** Sampling first
  was the original bug.
- **`classify_failure`** distinguishes `auth` / `prerequisite` / `unknown`. An
  app redirecting to another of its own pages means you *are* logged in and the
  route needs state. Previously every failure was blamed on authentication.
- **`detect_auth_scheme`** derives `protected` instead of hardcoding `True`.
- **`authenticate` returns `authenticated` and `reached_target` separately.**
  They differ when a page needs application state.
- **`session.verified_url`** records *which* page was verified;
  `get_accessibility_tree` refuses to scan if the browser has moved since.
- **`reach_state(force_steps=True)`** runs the steps first instead of only when
  arrival failed. Needed when a URL loads in the *wrong state* rather than
  redirecting — a checkout page opens fine with an empty cart.
- **`StaleElementReferenceException`** is retried once in the executor. WebDriver
  rejects a stale reference *before* dispatching, so the action did not happen
  and repeating it is safe even for `click`.
- **`ApiAuthProvider`** carries `Set-Cookie` into the browser (uses
  `requests.Session` so redirect hops are captured), supports dotted
  `token_field` paths like `data.token`, and accepts `token_field: null` for
  cookie-only apps. It fails only when *nothing* reached the browser.

---

## Pending

### 1. `run_axe` — the main one

Tier 1's other half. Inject axe-core, run it, merge its ~90 rule findings with
the accessibility-tree findings into one set. Nothing exists yet.

### 2. Accessibility-tree output quality

Three known defects in `Scan/ChromiumAxTreeReader.py`, all verified on real
pages, none fixed:

**a. Children-presentational pruning.** ARIA roles like `button`, `checkbox`,
`img`, `radio`, `switch`, `tab` do not expose their descendants — the content
becomes the parent's name. The reader emits those descendants anyway. On the
QXcel projects page `total_exposed` reports 88 where the truth is ~56 (24
paragraphs + 8 generics inside buttons). Fix: in pass 3, drop a node when any
ancestor has such a role; the `by_id`/`parentId` walk already exists.

`link` and `heading` are **not** in that set — an unnamed `<img>` inside a link
is a genuine finding and must survive.

**b. Findings are unlocatable.** A finding reads `role: button, name: "",
text: ""` — there is no way to tell which element it is. `backend_id` is a CDP
handle that resolves: `DOM.getOuterHTML({backendNodeId})` gives the HTML, and
`DOM.resolveNode` + `Runtime.callFunctionOn` builds a unique CSS selector.
Apply to findings only (two round trips each), not all nodes.

When building the selector, **check an element's id BEFORE pushing its own
nth-child descriptor** — doing it after puts the element in the path twice and
the selector matches nothing.

**c. Icon-font names are a false negative.** Verified on
`opensource-demo.orangehrmlive.com`: buttons whose accessible name is a single
Private Use Area glyph (`U+F64E`) from Bootstrap Icons, picked up by
name-from-content. `if not n["name"]` passes, so the scan reports zero problems
and misses them. Worse, *contents outrank `title`* in the name computation, so
a button with `title="Help"` announces as an unpronounceable glyph and the
author's label is never heard.

Rule: a name consisting only of `Co`/`Cn`/`Cf` category characters is
effectively empty. Keep it as a **separate bucket** from truly-unnamed — the fix
differs (`aria-hidden` on the icon *and* `aria-label` on the button).

### 3. Firefox parity

`FirefoxAxTreeReader` walks the DOM rather than a parent-linked tree, so each
of the above needs its own implementation there. Until then the two readers
report different `total_exposed` for the same page — which matters, because
cross-browser agreement has been the correctness check.

### 4. Deferred by the user — do not re-raise unprompted

Known, triaged, intentionally parked:

- `Scan/Dump.py` writes 4 JSON files into the repo on **every** scan, to
  `Path(__file__).parent`, so the working directory cannot redirect them.
  Concurrent sessions clobber each other.
- `reap_idle()` is only called from `create_driver`; no session cap. Browsers
  leak once an agent stops creating them.
- `SessionRegistry.add` is annotated `-> Session` but returns a `str`.
- `Session.browser` defaults to `"chrome"`.
- No per-session locking. Two concurrent MCP calls on one `session_id` race a
  non-thread-safe WebDriver. FastMCP runs sync tools in a threadpool, so this is
  reachable today.

---

## Roadmap — where this is going

The end goal is a **generic, application-independent accessibility scanner**:
point it at any app, let it reach the states worth auditing, and report findings
with enough detail to fix them. Everything below is design intent, not settled
detail — argue with it.

### Tier 1 — static semantics (finish this first)

What a page *claims* about itself. Two independent sources, merged:

- **The accessibility tree** — what the browser actually exposes. Catches
  unnamed controls, wrong roles, missing states. Done.
- **axe-core** — ~90 rule-based checks: contrast, landmarks, form labels,
  duplicate ids, heading order. Not started.

They overlap deliberately. The tree finds things axe has no rule for (a control
with a name nobody can pronounce); axe finds things invisible to the tree
(contrast, which needs pixels). **The merge step matters more than either
source** — the same defect must not be reported twice with different wording,
and each finding needs a WCAG criterion, a locator and the offending HTML.

### Tier 2a — keyboard reachability

The tree says *what should be operable*. Tab order says *what actually is*. The
scanner tabs through the page and compares the two sets:

- in the tree as interactive, **never reached by Tab** → keyboard trap or
  `tabindex="-1"` on something that needs operating (**WCAG 2.1.1**)
- reached by Tab, **absent from the tree** → focusable but invisible to
  assistive tech
- reached in a **different order than visual order** → **WCAG 2.4.3**
- **no visible focus indicator** → **WCAG 2.4.7**

This is the tier that proves the tree's claims rather than trusting them. The
counts in `get_accessibility_tree` (`interactive_count`) are the expected set.

### Tier 2b — screen-reader sampling

The tree is what the browser exposes; it is *not* what a user hears. A real
screen reader applies its own heuristics on top. Tier 2b drives **NVDA** over a
sample of elements and captures the actual announcement.

The old repo did this with NVDA's Speech Logger add-on writing to a log file —
workable but fragile, and it never produced data because the add-on was not
installed. Treat the old implementation as a reference for the idea only.

Value: catching the gap between *"the tree says this button is named Help"* and
*"NVDA says 'button' and nothing else"*. Expensive and Windows-only, so it is a
sampling tier, not a full sweep.

### Tier 3 — interaction and live regions

Everything that only exists after you *do* something:

- a modal opens — does focus move into it, is it trapped, does Escape close it,
  does focus return?
- an error appears — is it announced, or does it only change colour?
  (**WCAG 4.1.3**, the one the QXcel loading states fail)
- content loads into a live region — `aria-live` present and correct?
- a menu expands — does `aria-expanded` track reality?

**This is what the workflow engine was built for.** `run_steps` and
`reach_state` already drive the app through real interactions; Tier 3 is
scanning *during* those transitions rather than only at rest.

### Cross-cutting, needed before any of the tiers are trustworthy

- **Cross-browser parity.** Chromium and Firefox must report the same findings
  for the same page. Disagreement is currently the only correctness check there
  is — so the Firefox reader has to keep pace with every Chromium change.
- **A findings model.** Right now findings are ad-hoc lists on the scan result.
  They need a shared shape: WCAG criterion, severity, locator, HTML, source
  (tree / axe / keyboard / screen reader), and a stable id so the same defect
  across two runs is recognisably the same defect.
- **Crawling.** Everything today audits one page at a time. A real audit covers
  a site, which means a crawl that respects auth and application state —
  `reach_state` is the primitive, but nothing orchestrates it yet.
- **Reporting.** Findings have to leave the MCP boundary in a form a human can
  act on and a manager can read.

### Beyond accessibility

The user's stated longer-term direction is to apply the same
drive-the-app-and-observe machinery to **security and performance testing**. The
session registry, auth layer and workflow engine are deliberately generic for
that reason — none of them know anything about accessibility.

---

## How the user wants to work

These are explicit, repeated instructions. Honour them.

- **They write their own code.** Give snippets in chat; do not edit files in
  their repos unless they say so for a specific change. They are learning the
  codebase by typing it.
- **Verify by output, never by exit code.** Inspect real artefacts. "It ran" is
  not evidence. They have called this out directly.
- **Once they defer an issue, stop listing it.** They track their own backlog.
- **One thing at a time.** Snippet, confirm, next. Long multi-part answers get
  pushback.
- **Be brief.** Explanations should be short unless they ask to go deeper.

---

## Companion project — the agent

`Desktop/Projects/a11y` is a CrewAI agent that drives this server via
`localhost:8081`, using a local Ollama model (`qwen2.5:14b` at
`192.168.3.90:11434`).

Three workarounds live in its `main.py` and are all still required:

1. **`crewai_tools` cannot be imported** — its `__init__` eagerly imports
   chromadb → opentelemetry → grpc, and `cygrpc.pyd` is blocked by Smart App
   Control. Use `mcpadapt.core.MCPAdapt` + `CrewAIAdapter` directly.
2. **`mcpadapt`'s `$ref` resolver recurses forever** on `Target`, which is
   self-referential (`within: Target`). Monkeypatch it with a depth-limited
   version.
3. **`AnyAuthConfig` is an `anyOf`**, which mcpadapt maps to `str`, so passing
   the auth object is rejected client-side and login silently never happens.
   Override that one tool's `args_schema` with `auth: dict`.

**Lesson learned:** a 14B model cannot reliably re-emit a 4 KB nested JSON tool
argument, and it drops arguments like `browser='firefox'` (falling back to the
Chrome default, which is blocked). It also looped `create_driver` nine times and
leaked eight browser sessions. The fix was to **bind arguments in Python** and
expose zero-argument wrapper tools — the model still chooses the sequence and
reads every real result, it just cannot corrupt the values.

Credentials live in `Desktop/Projects/a11y/.env` (gitignored) and are read via
`envFile` in `.vscode/launch.json`. **Never commit them.**

---

## The old repo — why this one exists

`Desktop/ai-accessibilityTesting` is a CrewAI pipeline that this project
replaces. It was audited stage by stage, by inspecting real output rather than
exit codes. Findings:

- **working** — axe scan, recommendations, text spacing, zoom, HTML report
- **partial** — keyboard Tab/DOM-gap: stops early and emits false positives
- **produced nothing** — screen reader: NVDA's Speech Logger add-on was never
  installed, so the stage "passed" while writing an empty log

Real bugs found and fixed there, listed because they are the same classes of
mistake worth watching for here:

- NVDA path hardcoded to `Program Files (x86)` while 2026 builds install
  64-bit — and `os.system` fails **silently**, so the stage reported that the
  site announces nothing
- `a2a-sdk` unpinned; 1.1.2 removed `a2a.types.TextPart` and broke imports
- pandas 3.x rejects bool→str column assignment, so LLM results were silently
  replaced with error defaults
- an LLM prompt asked for a JSON array while `response_format` was
  `json_object`, which forbids arrays

**The standing lesson, and the user has said this directly:** a stage completing
is not evidence it produced anything. Inspect the artefact.

**`a11y/.env` and `a11y/.env.a2a` in that repo are tracked in git and contain
live credentials** (API key, MongoDB URI). They need rotating and
`git rm --cached`. Not done.

---

## Test targets

- **QXcel** — `qxcel.ai`, the user's own app. React, path-based routing. The UI
  source is at `Desktop/Qxcel/QXcel-UI`. `TxGenie.tsx` has a `RequireProject`
  guard: `/txgenie/{stories,review,analyzer,…}` redirect to `/projects` when no
  project is selected. This is the canonical prerequisite-state case.
- **OrangeHRM demo** — `opensource-demo.orangehrmlive.com`, public, credentials
  shown on its own login page. Good for icon-font and unnamed-button findings.

### A real finding worth fixing in QXcel's own UI

`ProjectsStep.tsx` renders each project as a `<button>` with no `aria-label`, so
its accessible name is computed from contents:

```
"QXcel QX · Ajay Bezawada 617 issues · updated 2 hours ago"
```

That name **changes every hour**, which repeatedly broke the workflow targets.
`aria-label={`Select project ${p.name}`}` fixes both the announcement and the
test stability. Also: the avatar-initial fallback `<div>{p.name.charAt(0)}</div>`
leaks a stray letter into the name and needs `aria-hidden="true"`, and the
loading/error states have no `role="status"`, so screen-reader users are told
nothing (WCAG 4.1.3).
