/**
 * scroll-to-top.js
 * Navigasi tombol 'Kembali ke Atas' (Back to Top)
 * Memastikan tombol muncul saat halaman di-scroll dan melakukan smooth scroll langsung ke atas saat ditekan.
 */

(function () {
    function initScrollToTop() {
        const scrollToTopButton = document.querySelector(".scroll-to-top");
        if (!scrollToTopButton) return;

        // Ambil jarak scroll saat ini dari berbagai kemungkinan properti browser
        const getScrollTop = () => {
            return (
                window.pageYOffset ||
                document.documentElement.scrollTop ||
                document.body.scrollTop ||
                0
            );
        };

        // Atur visibilitas tombol berdasarkan posisi scroll
        const updateVisibility = () => {
            const isVisible = getScrollTop() > 150;
            scrollToTopButton.classList.toggle("is-visible", isVisible);
            scrollToTopButton.setAttribute("aria-hidden", String(!isVisible));
        };

        // Event listener saat tombol ditekan
        scrollToTopButton.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();

            // 1. Eksekusi smooth scroll langsung ke posisi paling atas
            try {
                window.scrollTo({
                    top: 0,
                    left: 0,
                    behavior: "smooth"
                });
            } catch (err) {
                // Fallback untuk browser versi lama
                window.scrollTo(0, 0);
            }

            // 2. Fallback untuk documentElement / body
            if (document.documentElement) {
                document.documentElement.scrollTop = 0;
            }
            if (document.body) {
                document.body.scrollTop = 0;
            }

            // 3. Fallback jika ada elemen target #top
            const topElement = document.getElementById("top");
            if (topElement && typeof topElement.scrollIntoView === "function") {
                try {
                    topElement.scrollIntoView({ behavior: "smooth", block: "start" });
                } catch (e) {
                    topElement.scrollIntoView();
                }
            }

            // Bersihkan hash '#top' di URL agar tidak mengganggu navigasi berikutnya
            if (window.history && window.history.replaceState) {
                const cleanUrl = window.location.pathname + window.location.search;
                window.history.replaceState(null, "", cleanUrl);
            }
        });

        // Pantau event scroll dan resize window
        window.addEventListener("scroll", updateVisibility, { passive: true });
        window.addEventListener("resize", updateVisibility, { passive: true });

        // Cek posisi awal saat halaman selesai dimuat
        updateVisibility();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initScrollToTop);
    } else {
        initScrollToTop();
    }
})();
