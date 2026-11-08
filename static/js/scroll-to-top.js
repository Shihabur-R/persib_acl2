const scrollToTopButton = document.querySelector(".scroll-to-top");

if (scrollToTopButton) {
    const updateScrollToTopButton = () => {
        const isVisible = window.scrollY > 200;
        scrollToTopButton.classList.toggle("is-visible", isVisible);
        scrollToTopButton.setAttribute("aria-hidden", String(!isVisible));
    };

    window.addEventListener("scroll", updateScrollToTopButton, { passive: true });
    updateScrollToTopButton();
}
