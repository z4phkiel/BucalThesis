// A confirmation toast in place of the browser's confirm(), in the app's message stack (top right, above popups).
// It asks, so it stays until answered; the success message after it closes itself like flash-messages.js.
//   A form with data-confirm-toast="Question?" asks before it is sent (Linkage/Files, Grade Files).
//   confirmToast.ask({ title, opener, onYes }) asks from a script (Calendar, Grade Files' Replace). onYes returns
//   a promise (the toast waits for it, then closes) or nothing (a form that leaves the page: it stays "busy").
//   Optional: note, yes, busy (the button's labels), icon ('archive' or 'replace'), onCancel.
// Styled by .confirm-toast in index.css.
window.confirmToast = (function () {
    const SUCCESS_CLOSE_MS = 5000;      // same as flash-messages.js
    const GIVE_UP_MS = 20000;           // same as sign-in: a sent form that never answers unlocks the toast
    const ICONS = {     // the sidebar's archive box, and Grade Files' replace arrow
        archive: '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8M10 12h4"/>',
        replace: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8M21 3v5h-5"/>',
    };
    let open = null;                    // { toast, opener, labels, onCancel, confirmed, busy, timer } while a question shows

    function stack() {
        let found = document.querySelector('.flash-stack');
        if (!found) {
            found = document.createElement('aside');
            found.className = 'flash-stack';
            document.getElementById('pageContent').prepend(found);
        }
        return found;
    }

    function close(refocus) {
        if (!open) return;
        const closing = open;
        open = null;
        clearTimeout(closing.timer);
        closing.toast.remove();
        if (!closing.confirmed && closing.onCancel) closing.onCancel();
        if (refocus && closing.opener && closing.opener.isConnected) closing.opener.focus();
    }

    function setBusy(current, busy) {
        const yes = current.toast.querySelector('[data-confirm-yes]');
        current.busy = busy;
        if (busy) current.toast.setAttribute('aria-busy', 'true');
        else current.toast.removeAttribute('aria-busy');
        current.toast.querySelectorAll('button').forEach(function (button) {
            button.disabled = busy;
        });
        yes.textContent = busy ? current.labels.busy : current.labels.yes;
        if (busy) current.toast.focus();     // a disabled button would drop focus to the page
        else yes.focus();
    }

    function ask(options) {
        if (open && open.busy) return;      // one move at a time
        close(false);

        const toast = document.createElement('div');
        toast.className = 'confirm-toast';
        toast.tabIndex = -1;                // holds focus while its buttons are locked
        toast.setAttribute('role', 'alertdialog');
        toast.setAttribute('aria-labelledby', 'confirmToastTitle');
        toast.setAttribute('aria-describedby', 'confirmToastNote');
        toast.innerHTML = `
            <svg class="confirm-toast-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[options.icon] || ICONS.archive}</svg>
            <div class="confirm-toast-body">
                <p class="confirm-toast-title" id="confirmToastTitle"></p>
                <p class="confirm-toast-note" id="confirmToastNote"></p>
                <div class="confirm-toast-acts">
                    <button type="button" class="confirm-toast-btn" data-confirm-no>Cancel</button>
                    <button type="button" class="confirm-toast-btn is-danger" data-confirm-yes></button>
                </div>
            </div>`;
        const labels = { yes: options.yes || 'Move to Archives', busy: options.busy || 'Moving...' };
        toast.querySelector('.confirm-toast-title').textContent = options.title;
        toast.querySelector('.confirm-toast-note').textContent = options.note || 'It can be restored from the Archives.';
        toast.querySelector('[data-confirm-yes]').textContent = labels.yes;

        const current = { toast: toast, opener: options.opener, labels: labels, onCancel: options.onCancel,
                          confirmed: false, busy: false, timer: null };
        open = current;
        toast.querySelector('[data-confirm-no]').addEventListener('click', function () {
            close(true);
        });
        toast.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && !current.busy) close(true);
        });
        toast.querySelector('[data-confirm-yes]').addEventListener('click', function () {
            current.confirmed = true;
            setBusy(current, true);
            const sending = options.onYes();
            if (sending && sending.then) {
                sending.then(function () {
                    if (open === current) close(false);
                }, function () {
                    if (open === current) close(true);
                });
            } else {
                // A form leaves the page: the toast stays until the next page replaces it
                current.timer = setTimeout(function () {
                    current.confirmed = false;      // answerable again
                    setBusy(current, false);
                }, GIVE_UP_MS);
            }
        });

        stack().appendChild(toast);
        toast.querySelector('[data-confirm-yes]').focus();
    }

    // A green message that closes itself, like the server's success messages
    function done(text) {
        const message = document.createElement('div');
        message.className = 'alert alert-success alert-dismissible fade show';
        message.setAttribute('role', 'status');
        message.textContent = text;
        message.insertAdjacentHTML('beforeend', '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>');
        stack().appendChild(message);
        setTimeout(function () {
            bootstrap.Alert.getOrCreateInstance(message).close();
        }, SUCCESS_CLOSE_MS);
    }

    // Closes an unanswered question, e.g. with the popup it was asked from; one being sent is left to finish
    function dismiss() {
        if (open && !open.busy) close(false);
    }

    document.addEventListener('submit', function (event) {
        const form = event.target;
        if (!form.matches('form[data-confirm-toast]')) return;
        event.preventDefault();
        const menu = form.closest('.dropdown');
        ask({
            title: form.dataset.confirmToast,
            // a menu item is hidden once its menu closes, so focus goes back to the row's dots
            opener: (menu && menu.querySelector('.row-actions')) || event.submitter,
            onYes: function () {
                form.submit();      // sends without a second submit event
            },
        });
    });

    // The Back button can bring a page back still showing "Moving..."
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) close(false);
    });

    return { ask: ask, done: done, dismiss: dismiss };
})();
