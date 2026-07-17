# Government source pack (passive public)

Government registries are often stronger **source-of-truth** than social CVs — for **public** records only, under purpose limitation and local law.

## Indonesian modules

| Key | Portal | Dimension | Module |
|-----|--------|-----------|--------|
| `pddikti` | pddikti.kemdiktisaintek.go.id | education | `pddikti`, `pddikti_api`, HITL |
| `putusan_ma` | putusan3.mahkamahagung.go.id | risk | `gov_id` + HITL |
| `ahu` | ahu.go.id | work | `gov_id` + HITL |
| `lpse` | lpse.lkpp.go.id / regional LPSE | work | `gov_id` dorks |
| `kpu` | infopemilu.kpu.go.id / kpu PDF | notable | `gov_id` dorks |

```bash
python3 -m osint_cli -c "$CASE" collect --modules gov_id \
  --goal "sources=putusan_ma,ahu,lpse,pddikti,kpu"
```

## Optional PDDIKTI API (Parse.bot)

Third-party maintained wrapper — **not** an official Kemdikti API:

- Marketplace: https://parse.bot/marketplace/1b43c018-8c62-47d3-9843-6b24a057ad8b/pddikti-kemdiktisaintek-go-id-api  
- Base: `https://api.parse.bot/scraper/7adc51d7-b63d-45f5-87a7-49a7987989c3`  
- Auth: `PARSE_API_KEY` (or `PARSE_BOT_API_KEY`) header `X-API-Key`  
- Free tier: limited credits / rate limits  

```bash
export PARSE_API_KEY=…   # from parse.bot signup
python3 -m osint_cli -c "$CASE" collect --modules pddikti_api --goal "mahasiswa"
```

Always prefer re-check of high-stakes claims via official portal + HITL.

## Global (catalog only / dorks)

- UK Companies House  
- SEC EDGAR  
- CourtListener  

## Policy (hard)

**Allowed:** public search UIs, directed web dorks, single PDF review, Wayback, HITL real browser, optional documented third-party API keys.

**Forbidden in this tool:**

- IDOR sequential `?id=1000…5000` brute-force of pegawai/warga pages  
- Nmap/Nikto or aggressive scanning of `.go.id`  
- Captcha solving services  
- `admin.ahu` / undocumented grey-area government APIs  
- Mass NIK database assembly as a product feature  

Public court/election PDFs may contain sensitive identifiers (e.g. NIK). That does not make bulk harvesting or misuse lawful. Treat under investigation purpose + UU PDP / local rules.

## Passive discovery examples

```
"Nama Target" site:putusan3.mahkamahagung.go.id
"Nama Target" (PT OR Yayasan) site:ahu.go.id
site:lpse.*.go.id "Nama Perusahaan"
"Nama Target" filetype:pdf site:kpu.go.id
```
