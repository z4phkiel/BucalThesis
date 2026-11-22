document.addEventListener('DOMContentLoaded', function () {
    const GIVE_UP_MS = 20000;       // lets the user try again if loading was stopped or never finishes

    const form = document.querySelector('form');
    const button = form.querySelector('button[type="submit"]');
    const password = document.getElementById('password');
    const toggle = document.getElementById('togglePassword');
    const capsHint = document.getElementById('capsHint');
    const original = button.innerHTML;
    let giveUpTimer = null;

    // Checking the password takes a moment, so the button shows that it's working and can't be pressed twice
    function reset() {
        clearTimeout(giveUpTimer);
        button.disabled = false;
        button.innerHTML = original;
    }

    // An empty field turns red, shakes and says what's missing under it, instead of the browser's bubble.
    // A password is never trimmed: spaces can be part of one. The server checks again.
    function isEmpty(field) {
        return field === password ? !field.value : !field.value.trim();
    }

    function mark(field) {
        const box = field.closest('.field');
        document.getElementById(field.getAttribute('aria-describedby')).textContent = field.dataset.required;
        field.setAttribute('aria-invalid', 'true');
        box.classList.add('is-invalid');
        box.classList.remove('is-shaking');
        void box.offsetWidth;           // restarts the shake on every try
        box.classList.add('is-shaking');
    }

    function unmark(field) {
        if (field.getAttribute('aria-invalid') !== 'true') return;
        field.removeAttribute('aria-invalid');
        field.closest('.field').classList.remove('is-invalid', 'is-shaking');
        document.getElementById(field.getAttribute('aria-describedby')).textContent = '';
    }

    form.addEventListener('input', function (event) {
        if (event.target.hasAttribute('required')) unmark(event.target);
    });

    form.addEventListener('submit', function (event) {
        const empty = Array.from(form.querySelectorAll('[required]')).filter(isEmpty);
        if (empty.length) {
            event.preventDefault();
            empty.forEach(mark);
            empty[0].focus();
            return;
        }
        password.type = 'password';     // password managers only save what was sent from a password field
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>Signing in…';
        giveUpTimer = setTimeout(reset, GIVE_UP_MS);
    });

    // The Back button can restore this page exactly as it was left
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            reset();
        }
    });

    // Show or hide the password
    toggle.addEventListener('click', function () {
        const show = password.type === 'password';
        password.type = show ? 'text' : 'password';
        toggle.setAttribute('aria-pressed', String(show));
        toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
        password.focus();
    });

    // Caps Lock turns a correct password into a wrong one, so say when it's on
    ['keydown', 'keyup'].forEach(function (type) {
        password.addEventListener(type, function (event) {
            capsHint.hidden = !event.getModifierState('CapsLock');
        });
    });
    password.addEventListener('blur', function () {
        capsHint.hidden = true;
    });

    // Login photo slideshow: moves on every SLIDE_MS; a bar jumps to its photo.
    // With reduced motion it stays put and only the bars change the photo.
    const SLIDE_MS = 6000;
    const slides = document.querySelectorAll('.photo-slide');
    const dots = document.querySelectorAll('.photo-dot');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let currentSlide = 0;
    let slideTimer = null;

    function showSlide(index) {
        slides[currentSlide].classList.remove('is-active');
        dots[currentSlide].classList.remove('is-active');
        dots[currentSlide].removeAttribute('aria-current');
        currentSlide = (index + slides.length) % slides.length;
        slides[currentSlide].classList.add('is-active');
        dots[currentSlide].classList.add('is-active');
        dots[currentSlide].setAttribute('aria-current', 'true');

        clearTimeout(slideTimer);
        if (!reduceMotion.matches) {
            slideTimer = setTimeout(function () { showSlide(currentSlide + 1); }, SLIDE_MS);
        }
    }

    if (dots.length) {
        dots[0].parentElement.style.setProperty('--slide-time', SLIDE_MS + 'ms');
        dots.forEach(function (dot, i) {
            dot.addEventListener('click', function () { showSlide(i); });
        });
        showSlide(0);
    }

    // Authorized-use notice: opens with the page, then hands focus back to the form.
    // Reopened from the top-right button, Bootstrap returns focus to that button instead.
    const notice = document.getElementById('authNotice');
    if (notice.hasAttribute('data-auto-open')) {
        notice.addEventListener('hidden.bs.modal', function () {
            document.getElementById('username').focus();
        }, { once: true });
        bootstrap.Modal.getOrCreateInstance(notice).show();
    }
});
