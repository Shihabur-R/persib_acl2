/**
 * local-time.js
 * Deteksi otomatis zona waktu lokal pengguna dan konversi jadwal pertandingan dari UTC
 * ke waktu lokal (misalnya WIB, WITA, WIT untuk penonton di Indonesia).
 */
(function () {
    "use strict";

    /**
     * Mendapatkan informasi zona waktu lokal pengguna (singkatan & offset GMT).
     * @param {Date} date - Objek tanggal referensi
     * @returns {{ timeZone: string, tzAbbr: string, gmtOffsetStr: string }}
     */
    function getLocalTimeZoneInfo(date) {
        let timeZone = "";
        try {
            timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
        } catch (e) {
            timeZone = "";
        }

        // Hitung offset menit kebalikan dari getTimezoneOffset()
        const offsetMinutes = -date.getTimezoneOffset(); // e.g. +420 untuk UTC+7
        const offsetHours = offsetMinutes / 60;
        const sign = offsetMinutes >= 0 ? "+" : "-";
        const absHours = Math.floor(Math.abs(offsetHours));
        const absMins = Math.abs(offsetMinutes % 60);
        const gmtOffsetStr = `UTC${sign}${absHours}${absMins > 0 ? `:${String(absMins).padStart(2, "0")}` : ""}`;

        // Pemetaan khusus zona waktu Indonesia:
        // WIB (UTC+7): Asia/Jakarta, Asia/Pontianak
        // WITA (UTC+8): Asia/Makassar, Asia/Ujung_Pandang
        // WIT (UTC+9): Asia/Jayapura
        let tzAbbr = "";
        const idTimeZones = {
            "Asia/Jakarta": "WIB",
            "Asia/Pontianak": "WIB",
            "Asia/Makassar": "WITA",
            "Asia/Ujung_Pandang": "WITA",
            "Asia/Jayapura": "WIT"
        };

        if (timeZone && idTimeZones[timeZone]) {
            tzAbbr = idTimeZones[timeZone];
        } else {
            const userLang = (navigator.language || "").toLowerCase();
            const isIdLocale = userLang.startsWith("id");

            if (offsetMinutes === 420 && (isIdLocale || timeZone.includes("Jakarta") || timeZone.includes("Bangkok") || !timeZone)) {
                tzAbbr = "WIB";
            } else if (offsetMinutes === 480 && (isIdLocale || timeZone.includes("Makassar"))) {
                tzAbbr = "WITA";
            } else if (offsetMinutes === 540 && (isIdLocale || timeZone.includes("Jayapura"))) {
                tzAbbr = "WIT";
            } else {
                // Gunakan Intl.DateTimeFormat short timeZoneName untuk zona waktu internasional
                try {
                    const parts = new Intl.DateTimeFormat(navigator.language || "id-ID", {
                        hour: "2-digit",
                        timeZoneName: "short"
                    }).formatToParts(date);
                    const tzPart = parts.find((p) => p.type === "timeZoneName");
                    if (tzPart && tzPart.value) {
                        tzAbbr = tzPart.value;
                    }
                } catch (e) {}

                // Jika menghasilkan string GMT/UTC generic di offset Indonesia, prioritaskan WIB/WITA/WIT
                if (!tzAbbr || tzAbbr.startsWith("GMT") || tzAbbr.startsWith("UTC")) {
                    if (offsetMinutes === 420) {
                        tzAbbr = "WIB";
                    } else if (offsetMinutes === 480) {
                        tzAbbr = "WITA";
                    } else if (offsetMinutes === 540) {
                        tzAbbr = "WIT";
                    } else {
                        tzAbbr = tzAbbr || gmtOffsetStr;
                    }
                }
            }
        }

        return {
            timeZone: timeZone || "Waktu Lokal",
            tzAbbr: tzAbbr,
            gmtOffsetStr: gmtOffsetStr
        };
    }

    /**
     * Memformat waktu ke HH:mm + Zona Waktu (misal 17:00 WIB)
     * @param {Date} date
     * @param {string} tzAbbr
     * @returns {string}
     */
    function formatTime(date, tzAbbr) {
        const hours = String(date.getHours()).padStart(2, "0");
        const minutes = String(date.getMinutes()).padStart(2, "0");
        return `${hours}:${minutes} ${tzAbbr}`;
    }

    /**
     * Memformat tanggal ke format "DD MMM YYYY" (misal: 16 Sep 2026)
     * @param {Date} date
     * @returns {string}
     */
    function formatDate(date) {
        const months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
        const day = String(date.getDate()).padStart(2, "0");
        const month = months[date.getMonth()];
        const year = date.getFullYear();
        return `${day} ${month} ${year}`;
    }

    /**
     * Mengonversi semua elemen jadwal pada halaman
     */
    function applyUserLocalTime() {
        const now = new Date();
        const tzInfo = getLocalTimeZoneInfo(now);

        // Update indikator zona waktu
        const indicatorEls = document.querySelectorAll("#user-timezone-indicator, .user-timezone-text");
        indicatorEls.forEach((el) => {
            el.textContent = `Waktu Lokal: ${tzInfo.tzAbbr} (${tzInfo.gmtOffsetStr})`;
            if (el.parentElement) {
                el.parentElement.setAttribute(
                    "title",
                    `Waktu otomatis disesuaikan dengan perangkat Anda: ${tzInfo.timeZone} (${tzInfo.gmtOffsetStr})`
                );
            }
        });

        // Update jam kickoff
        const timeEls = document.querySelectorAll("[data-utc-time]");
        timeEls.forEach((el) => {
            const utcVal = el.getAttribute("data-utc-time");
            if (!utcVal) return;
            const matchDate = new Date(utcVal);
            if (!isNaN(matchDate.getTime())) {
                const localInfo = getLocalTimeZoneInfo(matchDate);
                el.textContent = formatTime(matchDate, localInfo.tzAbbr);
                el.setAttribute("title", `Waktu lokal: ${localInfo.tzAbbr} (${localInfo.gmtOffsetStr})`);
            }
        });

        // Update tanggal (antisipasi jika perpindahan zona waktu melintasi tengah malam)
        const dateEls = document.querySelectorAll("[data-utc-date]");
        dateEls.forEach((el) => {
            const utcVal = el.getAttribute("data-utc-date");
            if (!utcVal) return;
            const matchDate = new Date(utcVal);
            if (!isNaN(matchDate.getTime())) {
                el.textContent = formatDate(matchDate);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", applyUserLocalTime);
    } else {
        applyUserLocalTime();
    }
})();
