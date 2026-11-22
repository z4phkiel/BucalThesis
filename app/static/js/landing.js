// Scroll reveal: each heading line and card animates in once, the first time it scrolls into view.
// landing.css does the motion (and skips it for reduced motion); this only marks the elements.
const revealObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
        if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            revealObserver.unobserve(entry.target);
        }
    });
}, { rootMargin: '0px 0px -10% 0px' });     // starts once the element is a little above the bottom edge

document.querySelectorAll('.section-head > *, .card').forEach(function (item) {
    item.classList.add('reveal');
    revealObserver.observe(item);
});
