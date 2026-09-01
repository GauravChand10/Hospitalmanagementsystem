(() => {
    const root = document.documentElement;
    const hero = document.querySelector('.care-hero');
    const sections = document.querySelectorAll('.reveal-section');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    root.classList.add('motion-ready');

    if (reducedMotion.matches) {
        sections.forEach((section) => section.classList.add('is-revealed'));
        return;
    }

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add('is-revealed');
                observer.unobserve(entry.target);
            });
        }, {rootMargin: '0px 0px -8% 0px', threshold: 0.08});

        sections.forEach((section) => observer.observe(section));
    } else {
        sections.forEach((section) => section.classList.add('is-revealed'));
    }

    if (!hero || window.matchMedia('(max-width: 767px)').matches) return;

    let frameRequested = false;
    const updateHeroPhoto = () => {
        const distance = Math.min(Math.max(window.scrollY, 0), hero.offsetHeight);
        const progress = distance / hero.offsetHeight;
        hero.style.setProperty('--hero-parallax-y', `${(distance * 0.04).toFixed(2)}px`);
        hero.style.setProperty('--hero-photo-scale', (1.02 + progress * 0.02).toFixed(3));
        frameRequested = false;
    };

    window.addEventListener('scroll', () => {
        if (frameRequested) return;
        frameRequested = true;
        window.requestAnimationFrame(updateHeroPhoto);
    }, {passive: true});

    updateHeroPhoto();
})();
