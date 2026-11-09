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

    form.addEventListener('submit', function () {
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
});
