# HANDOFF — ACL2 Analytics & Simulation

Konteks untuk melanjutkan pekerjaan di sesi berikutnya. Baca file ini dulu sebelum mengedit.

## 1. Proyek

- Path: `/home/kakarot/Documents/persib_acl2`
- Nama aplikasi (UI): **ACL2 Analytics & Simulation** (branding lama "PERSIB Simetris" sudah dihapus dari UI)
- Stack: Python 3.13 + Flask + SQLite (`acl2.db`) + Jinja2 + vanilla JS/CSS
- Interpreter: **`venv/bin/python`** (selalu pakai ini, bukan `python` global)
- Entrypoint: `app_v2.py` (`app.py` = aplikasi legacy, jangan dipakai)
- Data: **32 klub Grup A–H** (4 per grup), ACL2 2026/27. Skuad rinci **513 pemain hanya E–H**; A–D belum punya skuad resmi (lihat §8)
- Commit terakhir: `51814e9` "Expand group support to A-H and harden data pipeline"

## 2. Aturan kerja (penting, dari user)

1. Kerjakan **bertahap dan ringkas**; jangan cetak ulang seluruh isi file.
2. **Jangan pernah mencetak tag `<tool_call>` atau `<｜DSML｜...>` sebagai teks.** Gunakan tool block yang benar.
3. Edit pakai tool edit (`single_find_and_replace` / `edit_existing_file`), bukan `sed`/`awk`.
4. Tool call besar rawan "Premature Close" → pecah jadi potongan kecil.
5. Setelah edit: jalankan `pytest tests/test_metrics.py -v` + cek route utama, lalu beri **ringkasan singkat per file**.
6. Bahasa UI: Indonesia. Komentar/identifier kode: English.
7. Tampilan harus bersih/standar: **tanpa emoji dekoratif**, tanpa frasa bergaya AI.

## 3. Status progres

Semua langkah di bawah **selesai & terverifikasi** (`24 passed`, route utama 200).

| Langkah | Status |
|---|---|
| 1. Konsistensi layout & navigasi | Selesai |
| 2. Rebranding + hapus emoji dekoratif | Selesai |
| 3. Knockout Stage `/knockout` (read-only) | Selesai |
| 4. Gol di Scenario Duel + indikator sumber | Selesai |
| 5. Filter grup di Home & Fixtures (satu grup per render) | Selesai |
| 6. Perataan container `/fixtures` + opsi `All` | Selesai |
| 7. Pemodelan duel kontekstual (venue/form/h2h) + ketahanan API | Selesai |
| 8. `/fixtures` mode All: gabung kronologis + filter status | Selesai |
| 9. Konsistensi label filter (Inggris) + dukungan A–H di Klub & Skuad | Selesai |
| 10. Seed klub resmi Grup A–D + snapshot A–H | Selesai |

### Verifikasi terakhir
- `venv/bin/python -m pytest tests/test_metrics.py -v` → **24 passed**.
- Route 200: `/`, `/?group=A`, `/balance`, `/duel`, `/picks`, `/insights`, `/knockout`, `/fixtures` (semua varian grup/status), `/clubs`, `/clubs?group=C`, `/players`, `/players?group=A`, `/club/<slug>` (E–H dan A–D).
- `POST /knockout` → **405** (read-only).
- Mode offline (mock `_fetch_json` gagal): fixtures & klasemen tetap **A–H** dari snapshot.
- `/knockout` dengan A–H: **16 slot / 4 babak**, semua TBD karena undian belum ada.
- Data lama utuh: klub E–H tetap 16, pemain tetap 513.

## 4. Arsitektur & API penting

### `data_sources.py`
- `SOURCE_URL`, **`SUPPORTED_GROUPS = A–H`** (parser), `GROUP_NAMES = ("E","F","G","H")` (fallback saja)
- TTL & retry: `CACHE_TTL_SECONDS=300`, `FALLBACK_TTL_SECONDS=60`, `FETCH_RETRIES=3`, `RETRY_BACKOFF_SECONDS=0.5`, `FETCH_TIMEOUT_SECONDS=10`
- `_fetch_with_retry()` → backoff untuk kegagalan transien; **4xx (selain 429) tidak diulang**
- `_fetch_with_cache()` berlapis: cache segar → API live → **`stale`** (`_last_good`, payload live terakhir) → snapshot → kosong. Respons kosong = gangguan, bukan live
- `get_club_slug()` juga cocok via **nama klub di DB** (`_slugs_by_name()`, cache TTL) → klub hasil seed langsung tertaut tanpa alias manual
- `get_clubs()`, `get_club_by_slug(slug)`, `get_players(club_id=None)` — fault-tolerant, return `[]` bila DB bermasalah
- `load_fixtures()` / `load_standings()` → list per grup: `{"group","name","fixtures"/"standings"}`
- `load_dashboard_groups()` → payload gabungan untuk `index.html`
- `get_data_status()` → `{"fixtures": "live"|"stale"|"snapshot"|"empty", "standings": ...}`
- `get_season_context()` → `source_label` mencakup stale/empty; `zone` mengikuti grup yang benar-benar ada
- `get_database_stats()`
- Fallback: `data/snapshot_east.json` (**kini memuat A–H**); kegagalan di-cache dengan TTL pendek agar pemulihan cepat
- Normalisasi menyertakan **alias legacy** (`tanggal`, `waktu`, `iso_utc`, `skor_home/away`, `pos`, `tim`, `main`, `menang`, `seri`, `kalah`, `gf`, `ga`, `gd`, `poin`) + `home_slug/away_slug` (selalu resolve ke slug DB), `home_logo/badge`, `matchweek`

### `metrics.py`
- `POSITIONS = ("GK","DF","MF","FW")`, `NEUTRAL_SCORE = 50.0`
- `squad_composition(players)`, `squad_balance_score(a, b)` → netral 50 bila salah satu kosong
- `home_away_split(fixtures, club_slug)` → ada `has_data`, `label_id`
- `head_to_head(standings, id_a, id_b)` → cocok via slug **atau** nama; ada `has_data`, `note`
- `goal_baseline(base)` → rata-rata gol/laga (1–1 bila `played == 0`)
- `resolve_goals(base, result, gf=None, ga=None, baseline=None)` → `{"goals_for","goals_against","source"}`, source = `manual|average|mixed|contextual`; clamp 0–20; rekonsiliasi skor yang bertentangan dengan hasil
- **Pemodelan kontekstual** (dipakai `/duel`):
  - `_iter_club_matches()` hanya laga `FT`, gol diorientasikan ke klub, urut terbaru; `_aggregate()`
  - `club_form(fixtures, slug, limit=5)`, `venue_record(fixtures, slug, venue)`, `head_to_head_record(fixtures, slug, opponent)`, `goal_rates(base)`
  - `contextual_goal_baseline(base, fixtures, club_slug, venue, opponent, recent=5)` → bobot `CONTEXT_WEIGHTS` venue 0.5 / form 0.3 / h2h 0.2, tiap komponen di-shrink `n/(n+FORM_PRIOR_MATCHES=3)`, bobot dinormalisasi, gol dibatasi 0–6
  - mengembalikan `source`, `components`, `component_labels`, `samples`, `rate_for/against`; **tanpa fixtures → fallback persis rata-rata musim**
- **`simulate_scenario(base, result, goals_for=None, goals_against=None, model_goals=False, baseline=None)`**
  - `model_goals=False` (default) = perilaku lama (poin saja) → kompatibel dengan TC-03
  - selalu set `goal_diff` & `goals_modelled`; bila dimodelkan juga set `scenario_goals` (+ `components`/`samples` bila `baseline` diberikan)
  - **input manual selalu menang** atas proyeksi kontekstual
- **Helper listing fixtures**: `FIXTURE_FILTERS = ("all","played","upcoming")`, `FIXTURE_FILTER_LABELS` = **All / Played / Upcoming** (Inggris, konsisten dengan tombol `All`/`Group X`)
  - `is_played(match)` → hanya `FT`; `fixture_sort_key()` + `_kickoff_stamp()`/`_parse_stamp()` → kronologis, **tanggal kosong/rusak turun ke akhir** (flag 1), tie-break grup + nama tim
  - `merge_fixtures(groups)` → satu daftar lintas grup, huruf grup dipertahankan; `filter_fixtures(matches, status)` → status tak dikenal/`None` aman
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
- **`SUPPORTED_GROUPS = A–H`**; `get_clubs_grouped()` mengikuti data (normalisasi huruf, grup kosong/tak dikenal dibuang) — dulu hardcoded E–H, ini akar masalah A–D tidak muncul
- `search_players(group_name=...)` menerima A–H; `get_database_stats()` menambah `groups` & `zones` dinamis

### `seed_west_groups.py` (baru)
- Menarik **klub resmi Grup A–D** dari endpoint standings AFC (nama, singkatan, negara, logo); slug dari `slugify(nama)`
- `insert_clubs()` **idempoten** (hanya slug yang belum ada), `--dry-run` tersedia
- `refresh_snapshot()` (`--snapshot`) menambah fixtures/klasemen A–D ke snapshot tanpa mengubah entri lama
- **Tidak mengarang skuad**: endpoint publik tidak menyediakan pemain A–D

## 5. Route (`app_v2.py`)

`/` · `/balance` · `/duel` · `/picks` · `/picks/<id>/delete` (POST) · `/knockout` (GET saja) · `/insights` · `/fixtures` · `/clubs` · `/players` · `/club/<slug>` · error handler 404/503

- `inject_globals()` context processor → `season`, `source_url`, `GOAL_SOURCE_LABELS`
- Konstanta: `BALANCE_MODES`, `DUEL_RESULTS`, `RESULT_LABELS`, `GOAL_SOURCE_LABELS` (+ `contextual`), `VENUES`, `VENUE_LABELS`
- `_select_group(groups, requested, allow_all=False)` → satu grup per render; `allow_all=True` (hanya `/fixtures`) mengizinkan `?group=all`
- `/fixtures`: `?group=` + `?status=` (`all|played|upcoming`, divalidasi). Mode All → `merge_fixtures` lalu filter, dirender sebagai satu daftar kronologis; mode grup → filter pada grup itu saja. Context: `matches`, `merged`, `groups`, `status_filter`, `status_filters`, `status_labels`, `total_matches`
- `/clubs`: `?group=` (`all` atau satu grup), context `group_letters` & `active_group`; grup tak dikenal → All
- `/players`: validasi grup via `database.SUPPORTED_GROUPS`, kirim `group_letters`
- `_pick_club()` aman terhadap slug ngawur/DB kosong; mode tak dikenal → fallback, bukan 400/500
- `/knockout` **GET saja (read-only)**: standings + fixtures per grup, `data_sources.load_knockout_draw()`, `data_sources.load_knockout_results()` → `knockout_stage.build_stage(...)`; tidak ada form/input klub maupun pemenang (POST → 405)
- `/duel` baca `gf_a`, `ga_a`, `gf_b`, `ga_b` + **`venue`** (`home|away`) + **`opponent`** (slug lawan segrup, klub sendiri dikecualikan) → `model_goals=True` dengan `baseline=contextual_goal_baseline(...)`. Context: `goal_baseline` (kontekstual), `goal_inputs`, `venues`, `venue_labels`, `selected_venue`, `opponents`, `selected_opponent`
- Secret key: env `FLASK_SECRET_KEY` (fallback dev)

## 6. Template & CSS

- **Semua template `extends "_layout.html"`** (index, fixtures, clubs, players, club_detail sudah dikonversi; inline script pindah ke `{% block scripts %}`)
- `_layout.html`: nav loop `nav_items` (9 item termasuk Knockout Stage), `aria-current="page"`, hamburger `.nav-toggle` + `#primary-nav`, **indikator sumber data** `.source-indicator-{live|snapshot|empty}`, banner snapshot, footer, scroll-to-top teks "Atas", blok `scripts`
- CSS: `static/css/style.css` (base; nav flex+gap, `.scroll-to-top` pill) + `static/css/simetris.css` (komponen fitur)
  - Nama file `simetris.css` **sengaja dipertahankan** (referensi teknis, bukan teks UI)
  - Kelas baru: `.bracket*`, `.slot-*`, `.seed-tag`, `.simulation-notice`, `.champion-banner`, `.goal-inputs`, `.source-indicator-*`, `.transparency-note`, `.stacked-bar`/`.seg-{gk,df,mf,fw}`, `.limitation-list`, `.btn-secondary`, `.form-actions`, `.group-switcher a.is-active`, `.status-switcher`, `.match-group-tag`, `.small-note`
  - **`.jl-fixtures-wrapper` = `max-width: 1200px; margin: 30px auto; padding: 0 20px`** — sengaja disamakan dengan `.header-container`/`.content-wrapper` agar tepi konten sejajar dengan nav
- **`templates/_fixture_row.html`** (baru): partial satu baris pertandingan, dipakai mode grup maupun gabungan (`show_group` → tag `Group X`),hindari duplikasi markup
- `fixtures.html`: dua nav (grup + status) saling mempertahankan pilihan; heading `ALL GROUPS` (gabungan) atau `GROUP X`; label Inggris (`All`/`Played`/`Upcoming`)
- `clubs.html`: judul & tombol grup dinamis dari data (tautan filter server, bukan anchor hardcoded E–H)
- `club_detail.html`: bila skuad kosong → keterangan "Data skuad klub ini belum tersedia pada sumber resmi." (bukan tabel hampa)
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
ds.RETRY_BACKOFF_SECONDS = 0
ds._fetch_json = lambda u: (_ for _ in ()).throw(OSError('offline'))
import app_v2; c = app_v2.app.test_client()
urls = ['/','/?group=A','/balance','/duel','/duel?club=al-wahda-fc','/picks','/insights',
        '/knockout','/fixtures','/fixtures?group=all','/fixtures?group=all&status=played',
        '/fixtures?group=D&status=upcoming','/clubs','/clubs?group=C','/players',
        '/players?group=A','/club/persib-bandung','/club/al-wahda-fc']
for u in urls:
    print(c.get(u).status_code, u)
print('grup:', [g['name'] for g in ds.load_fixtures()])
"
```

`RETRY_BACKOFF_SECONDS = 0` penting saat mock agar smoke test tidak menunggu backoff.

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
- **Grup A–D: data resmi, bukan rekaan.** API AFC sudah publishes 4 klub + 12 fixtures per grup A–D; yang kurang hanya skuad pemain. Jangan mengisi pemain fiktif untuk "melengkapi" — merusak validitas balance/duel/insights.
- Klub A–D punya `logo_url` dari CDN AFC dan `local_logo = None`; `city`/`stadium`/`coach`/`website` sengaja `NULL` karena tidak tersedia di endpoint publik.
- Emoji bendera pada `/players` & `club_detail` berasal dari **data** (`nationality_flag`, `country_flag`), bukan dekorasi template — jangan dihapus.
- Backup lokal `acl2.db.bak` & `data/snapshot_east.json.bak` dibuat sebelum seeding; pola `*.bak` dan `.pytest_cache/` sudah masuk `.gitignore`.
- Menjalankan seed ulang aman (idempoten): klub yang sudah ada dilewati, snapshot hanya menambah grup yang belum ada.

## 9. Kandidat pekerjaan lanjutan

1. **Skuad resmi Grup A–D** — perlu sumber skuad (endpoint/berkas resmi) untuk diimpor; saat ini halaman klub A–D menyatakan skuad belum tersedia. Jangan mengarang nama pemain.
2. Lengkapi `knockout_draw` & `knockout_results` pada snapshot dari undian resmi (pasangan tetap; tanpa tombol acak ulang/input manual). Sekarang 16 slot A–H masih TBD.
3. Simpan hasil Balance ke Saved Picks (Duel sudah punya tombol simpan). Knockout tetap read-only.
4. Tambah tes untuk `resolve_goals` kasus `mixed` dan `build_slots` dengan grup kurang dari 2 baris.
5. Pertimbangkan pagination/lazy render untuk `/fixtures?group=all` (96 baris) bila dataset bertambah.
6. `app.py` (legacy) masih menyebut Zona Timur/E–H — perbarui atau tandai deprecated bila masih dipakai.