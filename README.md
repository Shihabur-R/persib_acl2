# ACL2 Dashboard - AFC Champions League Two 2026/27

## Identitas Proyek
- **Mata Kuliah:** Rekayasa Perangkat Lunak (RPL)
- **Tugas:** Tugas 1 Kelompok (Pertemuan 07)
- **Judul Proyek:** Dashboard Klasemen & Jadwal Real-Time AFC Champions League Two 2026/27 (Grup E–H / Zone East)

## Deskripsi Aplikasi
ACL2 Dashboard adalah aplikasi web berbasis Flask yang menyajikan data jadwal pertandingan dan klasemen grup secara real-time untuk kompetisi AFC Champions League Two 2026/27 (khusus Zona Timur / Grup E–H yang melibatkan Persib Bandung). Data diambil secara dinamis dari API resmi AFC dan disesuaikan dengan zona waktu lokal pengguna (WIB, WITA, WIT).

## Fitur Utama
1. **Klasemen Real-Time (Grup E–H):** Menampilkan perolehan poin, jumlah main, menang, seri, kalah, serta selisih gol.
2. **Jadwal Pertandingan (Fixtures):** Menampilkan jadwal lengkap per grup beserta status pertandingan.
3. **Konversi Waktu Otomatis (Local Time):** Menyesuaikan tampilan zona waktu pertandingan secara otomatis di browser pengguna.
4. **Navigasi Responsif & Scroll-to-Top:** Desain antarmuka rapi, responsif, dan mudah diakses dari perangkat mobile maupun desktop.

## Teknologi yang Digunakan
- **Backend:** Python 3 (Flask)
- **Frontend:** HTML5, CSS3, JavaScript (Vanilla JS)
- **Integrasi Data:** REST API AFC (External Data Fetching)

## Struktur Folder
```text
persib_acl2/
├── app.py                  # Server utama Flask & Endpoint Routing
├── requirements.txt        # Daftar dependensi Python
├── README.md               # Dokumentasi petunjuk penggunaan
├── static/
│   ├── css/
│   │   └── style.css       # Styling UI/UX
│   ├── js/
│   │   ├── local-time.js   # Script konversi zona waktu
│   │   └── scroll-to-top.js# Script tombol kembali ke atas
│   └── images/             # Asset logo klub & kompetisi
└── templates/
    ├── index.html          # Halaman Klasemen
    └── fixtures.html       # Halaman Jadwal Pertandingan
