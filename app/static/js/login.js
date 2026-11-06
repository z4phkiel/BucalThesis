// Checking the password takes a moment, so the button shows that it's working and can't be pressed twice
document.addEventListener('DOMContentLoaded', function () {
    const GIVE_UP_MS = 20000;       // lets the user try again if loading was stopped or never finishes

    const form = document.querySelector('form');
    const button = form.querySelector('button[type="submit"]');
    const label = button.textContent;
    let giveUpTimer = null;

    function reset() {
        clearTimeout(giveUpTimer);
        button.disabled = false;
        button.textContent = label;
    }

    form.addEventListener('submit', function () {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Signing in…';
        giveUpTimer = setTimeout(reset, GIVE_UP_MS);
    });

    // The Back button can restore this page exactly as it was left
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            reset();
        }
    });
});
