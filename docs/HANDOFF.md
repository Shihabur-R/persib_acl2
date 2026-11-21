# HANDOFF — ACL2 Analytics & Simulation

Konteks untuk melanjutkan pekerjaan di sesi berikutnya. Baca file ini dulu sebelum mengedit.

## 1. Proyek

- Path: `/home/kakarot/Documents/persib_acl2`
- Nama aplikasi (UI): **ACL2 Analytics & Simulation** (branding lama "PERSIB Simetris" sudah dihapus dari UI)
- Stack: Python 3.13 + Flask + SQLite (`acl2.db`) + Jinja2 + vanilla JS/CSS
- Interpreter: **`venv/bin/python`** (selalu pakai ini, bukan `python` global)
- Entrypoint: `app_v2.py` (`app.py` = aplikasi legacy, jangan dipakai)
- Data: 16 klub / 513 pemain, ACL2 2026/27 East Zone Grup E–H

## 2. Aturan kerja (penting, dari user)

1. Kerjakan **bertahap dan ringkas**; jangan cetak ulang seluruh isi file.
2. **Jangan pernah mencetak tag `<tool_call>` atau `<｜DSML｜...>` sebagai teks.** Gunakan tool block yang benar.
3. Edit pakai tool edit (`single_find_and_replace` / `edit_existing_file`), bukan `sed`/`awk`.
4. Tool call besar rawan "Premature Close" → pecah jadi potongan kecil.
5. Setelah edit: jalankan `pytest tests/test_metrics.py -v` + cek route utama, lalu beri **ringkasan singkat per file**.
6. Bahasa UI: Indonesia. Komentar/identifier kode: English.
7. Tampilan harus bersih/standar: **tanpa emoji dekoratif**, tanpa frasa bergaya AI.

## 3. Status progres

| Langkah | Status |
|---|---|
| 1. Konsistensi layout & navigasi | **Selesai & terverifikasi** |
| Tambahan: rebranding + hapus emoji | **Selesai & terverifikasi** |
| 2. Knockout Stage `/knockout` | **Selesai & terverifikasi (route + modul)** |
| 3. Gol di Scenario Duel + indikator sumber + transparansi | **Selesai secara kode; verifikasi akhir BELUM tuntas** |

### Yang belum diverifikasi (kerjakan pertama di sesi berikutnya)
- `pytest tests/test_metrics.py -v` **belum dijalankan setelah 3 tes baru ditambahkan** (run terakhir sebelum penambahan: 5 passed). Tes baru:
  - `test_scenario_goals_manual_and_fallback`
  - `test_scenario_goals_invalid_and_contradictory`
  - `test_knockout_bracket_propagation`
- Render `/balance` (catatan transparansi baru), `/insights` (keterbatasan baru), dan indikator sumber di header belum dicek setelah edit CSS/template terakhir.
- Cek mode **live API** (tanpa mock) sekali lagi.

## 4. Arsitektur & API penting

### `data_sources.py`
- `SOURCE_URL`, `GROUP_NAMES = ("E","F","G","H")`, `CACHE_TTL_SECONDS`
- `get_clubs()`, `get_club_by_slug(slug)`, `get_players(club_id=None)` — fault-tolerant, return `[]` bila DB bermasalah
- `load_fixtures()` / `load_standings()` → list per grup: `{"group","name","fixtures"/"standings"}`
- `load_dashboard_groups()` → payload gabungan untuk `index.html`
- `get_data_status()` → `{"fixtures": "live"|"snapshot"|"empty", "standings": ...}`
- `get_season_context()` → termasuk `source_label` & `data_status`
- `get_database_stats()`
- Fallback: `data/snapshot_east.json`; kegagalan **ikut di-cache** agar tidak timeout 15s tiap request
- Normalisasi menyertakan **alias legacy** (`tanggal`, `waktu`, `iso_utc`, `skor_home/away`, `pos`, `tim`, `main`, `menang`, `seri`, `kalah`, `gf`, `ga`, `gd`, `poin`) + `home_slug/away_slug` (selalu resolve ke slug DB), `home_logo/badge`, `matchweek`

### `metrics.py`
- `POSITIONS = ("GK","DF","MF","FW")`, `NEUTRAL_SCORE = 50.0`
- `squad_composition(players)`, `squad_balance_score(a, b)` → netral 50 bila salah satu kosong
- `home_away_split(fixtures, club_slug)` → ada `has_data`, `label_id`
- `head_to_head(standings, id_a, id_b)` → cocok via slug **atau** nama; ada `has_data`, `note`
- `goal_baseline(base)` → rata-rata gol/laga (1–1 bila `played == 0`)
- `resolve_goals(base, result, gf=None, ga=None)` → `{"goals_for","goals_against","source"}`, source = `manual|average|mixed`; clamp 0–20; rekonsiliasi skor yang bertentangan dengan hasil
- **`simulate_scenario(base, result, goals_for=None, goals_against=None, model_goals=False)`**
  - `model_goals=False` (default) = perilaku lama (poin saja) → kompatibel dengan TC-03
  - selalu set `goal_diff` & `goals_modelled`; bila dimodelkan juga set `scenario_goals`
- `compare_scenarios(a, b)` → `advantage`, `advantage_label`, `symmetry_a/b`, `more_balanced`, `balance_score`, `balance_label_id`, `gap_score`
- `scenario_symmetry(scenario)` → TV distance vs 1/3 merata (100 = merata)
- `composition_by_club(clubs, players)`, `group_comparison_table(standings)` (ppg, gap_to_leader)

### `knockout.py` (read-only, tanpa input manual)
- `ROUND_ORDER = ("R32","R16","QF","SF","F")`, `ROUND_LABELS`, `TBD_LABEL = "TBD"`
- Status slot: `SLOT_FILLED` (`draw`), `SLOT_PENDING_GROUP` (`group_incomplete`), `SLOT_PENDING_DRAW` (`draw_pending`), `SLOT_EMPTY` (`empty`) + `STATUS_LABELS` berbahasa Indonesia
- `group_completion(standings_by_group, fixtures_by_group)` → per grup `{complete, expected_played, min_played, remaining_fixtures, reason}`; selesai hanya bila tiap klub mencapai `(n-1)*2` laga **dan** tidak ada fixture non-`FT`
- `qualified_seeds(standings_by_group, completion, per_group=2)` → seed `1E`, `2F`, ... **hanya dari grup yang sudah selesai**
- `build_slots(seeds, completion, draw=None, slot_count=None)` → slot terisi hanya bila grup selesai **dan** undian menempatkan seed itu; sisanya TBD berstatus jelas
- `build_bracket(slots, results=None, draw=None)` → `{"rounds":[{key,label,matches}], "champion", "complete", "slot_count", "filled_count", "draw_available", "is_simulation": False}`
  - jumlah slot dibulatkan ke pangkat dua berikutnya (`_bracket_size`), jumlah babak mengikuti (`R32`→`F`), sehingga kontestan lintas grup tidak pernah dibuang
  - match id mengikuti ronde aktif (mis. `R161..R168`, `QF1..QF4`, `SF1`, `SF2`, `F1`)
  - pemenang hanya dari hasil tercatat (`winner_slug`/`winner` dicocokkan ke slug/nama peserta tie); nilai bebas seperti `"home"`/`"away"` dan hasil prematur diabaikan
- `build_stage(...)` = satu pintu untuk `/knockout`: completion, seeds, slots, bracket, `draw_available`, `draw_ties`, `note`, `groups_all_complete`, `cross_group`
- Pasangan **tidak pernah dikarang**: tanpa `draw` seluruh bagan TBD

### `picks_store.py`
- `_connection()` = `@contextmanager` (selalu close)
- unique index `idx_picks_identity (title, side_a, side_b)`; `IntegrityError` → `PickValidationError`
- `save_pick(title, side_a, side_b, payload, mode="duel")`; mode whitelist `duel|squad|home_away|head_to_head`
- `list_picks()` → + `payload` (decoded), `created_label`, `mode_label`; `delete_pick(id)`

### `database.py`
- `get_db_connection()` = `@contextmanager` (dulu bocor handle per query)

## 5. Route (`app_v2.py`)

`/` · `/balance` · `/duel` · `/picks` · `/picks/<id>/delete` (POST) · `/knockout` (GET saja) · `/insights` · `/fixtures` · `/clubs` · `/players` · `/club/<slug>` · error handler 404/503

- `inject_globals()` context processor → `season`, `source_url`, `GOAL_SOURCE_LABELS`
- Konstanta: `BALANCE_MODES`, `DUEL_RESULTS`, `RESULT_LABELS`, `GOAL_SOURCE_LABELS`
- `_pick_club()` aman terhadap slug ngawur/DB kosong; mode tak dikenal → fallback, bukan 400/500
- `/knockout` **GET saja (read-only)**: standings + fixtures per grup, `data_sources.load_knockout_draw()`, `data_sources.load_knockout_results()` → `knockout_stage.build_stage(...)`; tidak ada form/input klub maupun pemenang (POST → 405)
- `/duel` baca `gf_a`, `ga_a`, `gf_b`, `ga_b` → `model_goals=True`; context: `goal_baseline`, `goal_inputs`
- Secret key: env `FLASK_SECRET_KEY` (fallback dev)

## 6. Template & CSS

- **Semua template `extends "_layout.html"`** (index, fixtures, clubs, players, club_detail sudah dikonversi; inline script pindah ke `{% block scripts %}`)
- `_layout.html`: nav loop `nav_items` (9 item termasuk Knockout Stage), `aria-current="page"`, hamburger `.nav-toggle` + `#primary-nav`, **indikator sumber data** `.source-indicator-{live|snapshot|empty}`, banner snapshot, footer, scroll-to-top teks "Atas", blok `scripts`
- CSS: `static/css/style.css` (base; nav flex+gap, `.scroll-to-top` pill) + `static/css/simetris.css` (komponen fitur)
  - Nama file `simetris.css` **sengaja dipertahankan** (referensi teknis, bukan teks UI)
  - Kelas baru: `.bracket*`, `.slot-*`, `.seed-tag`, `.simulation-notice`, `.champion-banner`, `.goal-inputs`, `.source-indicator-*`, `.transparency-note`, `.stacked-bar`/`.seg-{gk,df,mf,fw}`, `.limitation-list`, `.btn-secondary`, `.form-actions`
  - Breakpoint: ≤1100px nav turun baris; ≤760px hamburger + judul mengecil
- JS: `static/js/nav-toggle.js` (baru), `scroll-to-top.js`, `local-time.js`

## 7. Perintah verifikasi

```bash
venv/bin/python -m pytest tests/test_metrics.py -v
```

Smoke test route (mock offline → pakai snapshot):

```bash
venv/bin/python -c "
import data_sources as ds
ds._fetch_json = lambda u: (_ for _ in ()).throw(ValueError('offline'))
import app_v2; c = app_v2.app.test_client()
for u in ['/','/balance','/duel','/picks','/insights','/knockout','/fixtures','/clubs','/players','/club/persib-bandung']:
    print(c.get(u).status_code, u)
"
```

Validasi sintaks semua template:

```bash
venv/bin/python -c "
import app_v2; env = app_v2.app.jinja_env
for n in sorted(env.list_templates()):
    if n.endswith('.html'):
        env.parse(open('templates/'+n, encoding='utf-8').read()); print('OK', n)
"
```

Mode live: jalankan smoke yang sama **tanpa** mock `_fetch_json`, cek `ds.get_data_status()`.

## 8. Catatan & jebakan

- `acl2.db` ikut ter-modifikasi karena penambahan unique index (disengaja). Dua baris lama `Smoke Test` / `TC Test` **sudah ter-commit sejak sebelumnya** — bukan artefak sesi ini; boleh dibersihkan bila user minta.
- Tes TC-04/TC-05 memakai `tmp_path` + monkeypatch `DB_PATH`, tapi sebagian run sempat menulis ke DB asli → cek & bersihkan pick sisa uji setelah menjalankan tes.
- Bersihkan artefak sebelum selesai: `rm -rf .pytest_cache tmp .venv` (folder `tmp/` & `.venv` pernah dibuat lalu dihapus).
- `docs/SRS.md` masih berjudul "PERSIB Simetris" — **sengaja dibiarkan** (dokumen spesifikasi asli). Label metrik "Sangat Simetris" di `metrics.py` juga dipertahankan (istilah pengukuran, bukan branding).
- Jangan menambah dependensi berat; chart dibuat dengan CSS (stacked bar), bukan library JS.

## 9. Kandidat pekerjaan lanjutan

1. Tuntaskan verifikasi (poin 3 di atas).
2. Simpan hasil Knockout / Balance ke Saved Picks (saat ini hanya Duel yang punya tombol simpan).
3. Lengkapi dataset `knockout_draw` & `knockout_results` pada snapshot (pasangan tetap dari undian resmi; tanpa tombol acak ulang/input manual).
4. Tambah tes untuk `resolve_goals` kasus `mixed` dan `build_slots` dengan grup kurang dari 2 baris.
5. Rapikan README agar menyebut `/knockout` dan input gol.