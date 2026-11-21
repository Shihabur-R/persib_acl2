# PERSIB Simetris — SRS Ringkas

## Ringkasan
Aplikasi Flask modular berbasis data persib_acl2 dengan tiga fitur:
Balance Meter, Scenario Duel, dan Saved Pick.

## Data
- SQLite: 16 klub, 513 pemain (musim 2026/27)
- API AFC live: fixtures & standings (99 laga, 67 selesai) dengan cache TTL 300s
- Fallback snapshot lokal: data/snapshot_east.json (48 fixtures Grup E-H)

## Temuan Statistik (2)
1. **Distribusi komposisi posisi per klub** (grouped bar chart).
2. **Perbandingan head-to-head klasemen Grup E** (poin, gol, selisih gol).

## Keterbatasan Dataset (1)
Proyeksi Scenario Duel tidak memodelkan gol (hanya poin & rasio menang/seri/kalah);
data skuad statis satu musim, dan data live bergantung API eksternal.

## Skenario Uji (TC-01 s.d. TC-05)

| ID | Skenario | Langkah | Hasil yang Diharapkan |
|----|----------|---------|------------------------|
| TC-01 | Balance Meter data valid | GET /balance?mode=squad | Skor 0–100 muncul + label status |
| TC-02 | Balance Meter data kosong | Uji unit squad_balance_score([], x) | Tidak error, skor netral 50.0 |
| TC-03 | Scenario Duel simulasi | POST /duel (win vs draw) | Kedua kartu tampil + verdict |
| TC-04 | Saved Pick validasi | POST /picks (title kosong) lalu duplikat | Flash error jelas, pick tidak tersimpan ganda |
| TC-05 | Saved Pick hapus | POST /picks/<id>/delete | Item hilang dari daftar |
