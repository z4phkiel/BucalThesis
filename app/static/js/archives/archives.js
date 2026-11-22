document.addEventListener('DOMContentLoaded', function () {
    const GIVE_UP_MS = 20000;   // same as sign-in: the page comes back to normal if the reply never arrives
    let giveUpTimer = null;

    // ---------- Restore ----------
    // The menu closes at once, so the row itself shows it is being restored until the page reloads with the result.
    // The cover sits over the row (no column moves) and hides its dots, so it can't be sent twice.
    const status = document.getElementById('archivesStatus');

    document.querySelectorAll('form[data-restore]').forEach(function (form) {
        form.addEventListener('submit', function () {
            const row = form.closest('tr');
            const name = form.dataset.restore;
            const cover = document.createElement('div');
            const text = document.createElement('span');
            cover.className = 'archives-restoring';
            cover.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
            text.className = 'archives-restoring-text';
            text.textContent = name ? 'Restoring “' + name + '”…' : 'Restoring…';
            cover.appendChild(text);

            row.lastElementChild.appendChild(cover);
            row.classList.add('is-restoring');
            row.setAttribute('aria-busy', 'true');
            row.querySelector('.row-actions').disabled = true;
            status.textContent = text.textContent;
            giveUpTimer = setTimeout(reset, GIVE_UP_MS);
        });
    });

    // ---------- Delete permanently ----------
    // One shared popup, filled with the row whose button was clicked. Its button waits for "I understand".
    const modal = document.getElementById('deleteForeverModal');
    const deleteForm = modal.querySelector('form');
    const understood = document.getElementById('deleteForeverUnderstood');
    const deleteButton = deleteForm.querySelector('button[type="submit"]');
    const deleteLabel = deleteButton.innerHTML;
    let deleting = false;

    modal.addEventListener('show.bs.modal', function (event) {
        const button = event.relatedTarget;
        deleteForm.action = button.dataset.action;
        document.getElementById('deleteForeverName').textContent = button.dataset.name;
        understood.checked = false;     // asked again for every item
        deleteButton.disabled = true;
    });

    modal.addEventListener('shown.bs.modal', function () {
        understood.focus();
    });

    understood.addEventListener('change', function () {
        deleteButton.disabled = !understood.checked;
    });

    deleteForm.addEventListener('submit', function () {
        deleting = true;
        deleteButton.disabled = true;
        deleteButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Deleting…';
        modal.querySelectorAll('[data-bs-dismiss]').forEach(function (button) {
            button.disabled = true;
        });
        deleteForm.setAttribute('aria-busy', 'true');
        giveUpTimer = setTimeout(reset, GIVE_UP_MS);
    });

    // Esc and clicks beside the popup wait too: the item is already on its way out
    modal.addEventListener('hide.bs.modal', function (event) {
        if (deleting) {
            event.preventDefault();
        }
    });

    // ---------- Both ----------
    function reset() {
        clearTimeout(giveUpTimer);
        status.textContent = '';
        document.querySelectorAll('tr.is-restoring').forEach(function (row) {
            row.classList.remove('is-restoring');
            row.removeAttribute('aria-busy');
            row.querySelector('.row-actions').disabled = false;
            row.querySelector('.archives-restoring').remove();
        });

        deleting = false;
        deleteButton.innerHTML = deleteLabel;
        deleteButton.disabled = !understood.checked;
        modal.querySelectorAll('[data-bs-dismiss]').forEach(function (button) {
            button.disabled = false;
        });
        deleteForm.removeAttribute('aria-busy');
    }

    // The Back button can bring this page back exactly as it was left, still covered or still deleting
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            reset();
        }
    });
});
