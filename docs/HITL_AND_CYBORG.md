# Human-in-the-Loop (HITL) & Cyborg Mode

## Why

Government and social portals (PDDIKTI, Instagram viewers, Cloudflare) block pure HTTP bots. This tool **does not** buy captcha solvers or brute-force challenges. The operator’s real browser is the unlocker; the agent resumes collection.

## Paths (best → fallback)

| Path | When | Command |
|------|------|---------|
| **HITL complete** | Operator copied fields from a real browser | `hitl complete --gate g1 --grade full_page --value '{…}'` |
| **HITL import-file** | Operator saved HTML/JSON | `hitl import-file --gate g1 --path ./page.html` |
| **browser_cdp (Cyborg)** | Chrome already open with remote debugging | `collect --modules browser_cdp` |
| **pddikti_api** | Optional Parse.bot key available | `PARSE_API_KEY=… collect --modules pddikti_api` |
| **page.pause()** | Local script debug only | Not wired as default agent path |

## Operator: Cyborg Chrome

```bash
# Dedicated profile (do not hijack daily cookies carelessly)
chromium-browser \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-osint-profile"

# In that browser: open portal, pass Cloudflare, land on results.
# Then from agent/CLI:
python3 -m osint_cli -c "$CASE" collect --modules browser_cdp \
  --goal "url_contains=pddikti"
```

Optional full DOM extract needs Playwright:

```bash
pip install 'ai-osint-terminal[browser]'  # or: pip install playwright
playwright install chromium
```

Without Playwright, `browser_cdp` still lists open tabs via `http://127.0.0.1:9222/json/list`.

## Agent flow

1. `collect --modules pddikti` → may emit open HITL gate on challenge wall  
2. `next` / `status` surfaces `open_hitl_gates`  
3. Operator finishes browser work  
4. `hitl complete` or `browser_cdp` → graded evidence (`full_page` when honest)  
5. Continue `differentiate` / `dimension` / `report`

## Honesty grades

Same as `evidence add`: `full_page` | `search_snippet` | `portal_metadata` | `operator_clue`.

## Hard no

- Captcha farms / 2Captcha-style services  
- Headless mass bypass of Cloudflare  
- Treating HITL as license to violate portal ToS at scale  
