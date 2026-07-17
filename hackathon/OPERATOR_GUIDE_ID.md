# Panduan operator — deploy, test, submit, video

Bahasa sederhana. Tidak perlu jadi DevOps.

---

## 1. “Deploy” itu apa di hackathon ini?

**Bukan** wajib sewa server ECS 24/7 (meski boleh).

Yang **wajib** menurut rules:

| Item | Artinya untuk TraceLock | Kamu ngapain |
|------|-------------------------|--------------|
| Project jalan | Clone + `python3 -m tracelock run` | Pastikan di laptop/HP lab kamu jalan |
| Pakai Qwen Cloud | Kode panggil DashScope API | Isi `DASHSCOPE_API_KEY` saat demo live |
| Proof Alibaba | **Link file kode** di GitHub | Paste URL `tracelock/qwen_client.py` di form |
| Architecture | Gambar sistem | Link SVG di repo |

Jadi “deploy” di submit form ≈ **repo public + API Qwen (kode sudah nulis base URL Alibaba) + demo yang kelihatan jalan**.

### Opsional (kalau mau lebih “cloud”)

- Buka Qwen Cloud, buat API key, jalankan live di laptop kamu (ini sudah cukup “pakai Alibaba API”).
- Nanti kalau sempat: taruh proses di Alibaba ECS — **tidak wajib** untuk lolos proof “link to code file”.

---

## 2. Cara test (yang sama untuk juri & kamu)

```bash
# 1) Clone
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock

# 2) Offline (WAJIB bisa — tanpa key)
python3 -m tracelock run --offline

# 3) Live Qwen (disarankan untuk video)
export DASHSCOPE_API_KEY=sk-...   # dari https://www.qwencloud.com/
pip install '.[qwen]'
python3 -m tracelock run --clue 'username:demo_subject_ig' --clue 'phone:0812-5550-0100'

# 4) Proof fingerprint (tidak bocor secret)
python3 -m tracelock deploy-proof
```

**Lolos test kalau:**

- Exit sukses, ada **plan** (daftar tool), ada **HITL**, ada **TraceLock Investigation Report**.
- Offline mode bertuliskan `mode: offline` — itu normal.

**Testing instructions** (paste ke Devpost):

```text
git clone https://github.com/SeraKah-1/tracelock.git
cd tracelock
python3 -m tracelock run --offline
# optional live:
# export DASHSCOPE_API_KEY=...
# pip install '.[qwen]'
# python3 -m tracelock run
```

---

## 3. Apa yang dikirim di Devpost?

Bukan ZIP random. Form diisi + link:

| Field Devpost | Isi |
|---------------|-----|
| Project name | `TraceLock` |
| Elevator pitch | tagline pendek (sudah disiapkan) |
| About / story | Markdown project story |
| Track | **Track 4: Autopilot Agent** |
| Repo URL | `https://github.com/SeraKah-1/tracelock` |
| Architecture | `https://github.com/SeraKah-1/tracelock/blob/main/docs/assets/architecture.svg` |
| Proof Alibaba | `https://github.com/SeraKah-1/tracelock/blob/main/tracelock/qwen_client.py` |
| Demo video | Link YouTube / Vimeo / Youku **public** |
| Built with | Qwen, DashScope, Python, … |
| Testing | perintah clone + run di atas |

**Tidak perlu** kirim folder ke email juri. Mereka buka GitHub + video.

---

## 4. Video — ya, **screen record**

Rules: &lt; **3 menit**, project **terlihat jalan**, upload **YouTube / Vimeo / Youku** public.  
Tidak wajib sinematik. **Screen recording terminal + browser** = standar hackathon.

### Tools rekam (pilih satu)

| OS | Tool |
|----|------|
| Windows | Xbox Game Bar (`Win+G`) / OBS |
| macOS | `Cmd+Shift+5` |
| Linux | OBS / SimpleScreenRecorder |
| Android | Screen record bawaan (kalau demo di Termux) |

**Jangan** pakai musik copyright / logo merek orang tanpa izin.

### Naskah 2,5–3 menit (ikuti saja)

| Waktu | Layar | Bilang / caption |
|-------|--------|------------------|
| 0:00–0:20 | README GitHub TraceLock | “TraceLock: investigation autopilot for ambiguous clues.” |
| 0:20–0:40 | Terminal: clone + `run --offline` | “Offline demo for judges — same tool loop.” |
| 0:40–1:20 | Scroll output: plan tools, HITL, report | “Plans steps, calls tools, opens HITL, writes dossier.” |
| 1:20–1:50 | (Opsional) Live: set key + `run` tanpa offline | “Live planner uses Qwen on DashScope.” |
| 1:50–2:20 | Browser: `qwen_client.py` di GitHub (base URL DashScope) | “Alibaba Qwen Cloud API proof in-repo.” |
| 2:20–2:40 | `architecture.svg` | “Qwen → agent → tools → case → HITL → report.” |
| 2:40–3:00 | README / repo URL | “MIT · github.com/SeraKah-1/tracelock · Track 4.” |

### Checklist rekaman

- [ ] Resolusi kebaca (font terminal besarin dulu)  
- [ ] Jangan tampilkan full API key (sensor / export di luar frame)  
- [ ] Ada momen **project functioning** (bukan cuma slide)  
- [ ] &lt; 3:00  
- [ ] Upload **Unlisted atau Public** (boleh unlisted asal link bisa dibuka juri tanpa login aneh — Public paling aman)  
- [ ] Paste URL ke form Devpost  

### Upload YouTube cepat

1. youtube.com → Create → Upload  
2. Title: `TraceLock — Qwen Cloud Autopilot Demo`  
3. Visibility: **Public**  
4. Copy link → Devpost field “Demo video”

---

## 5. Urutan kerja kamu hari ini

```text
1. Pastikan di mesinmu: offline run OK
2. (Disarankan) Dapatkan DASHSCOPE_API_KEY, coba live run sekali
3. Screen record 2–3 menit (skrip di atas)
4. Upload YouTube
5. Buka Devpost → isi field → Submit
```

Kalau stuck cuma di “deploy server” — **skip**. Fokus: **run lokal + video + link proof di GitHub**.

---

## 6. Link cepat

| Apa | URL |
|-----|-----|
| Repo | https://github.com/SeraKah-1/tracelock |
| Proof file | https://github.com/SeraKah-1/tracelock/blob/main/tracelock/qwen_client.py |
| Architecture | https://github.com/SeraKah-1/tracelock/blob/main/docs/assets/architecture.svg |
| Hackathon | https://qwencloud-hackathon.devpost.com/ |
| Deadline | 20 Jul 2026 14:00 PT |
