// A student's enrollment form: the floating button while viewing, and unlocking the fields while editing
(function () {
    const fab = document.querySelector('.form-fab');
    if (fab) {
        document.getElementById('printFormBtn').addEventListener('click', function () {
            window.print();
        });
        fab.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                document.activeElement.blur();
            }
        });
    }

    const form = document.getElementById('studentForm');
    if (!form) {
        return;
    }

    // This runs while the page loads, so it comes before the DOMContentLoaded code of the form's other
    // scripts. Those then lock again whatever doesn't apply, such as the follow-up to a "No" answer.
    form.querySelectorAll('input, select').forEach(function (field) {
        if (!field.hasAttribute('data-locked')) {
            field.readOnly = false;
            field.disabled = false;
        }
    });

    function currentValues() {
        return new URLSearchParams(new FormData(form)).toString();
    }

    // This file loads last, so this runs after the other scripts have filled in the form.
    // A rejected form has no starting point: what was typed there isn't saved yet, so leaving always asks.
    let startingValues = null;
    document.addEventListener('DOMContentLoaded', function () {
        if (!form.hasAttribute('data-unsaved')) {
            startingValues = currentValues();
        }
    });

    let saving = false;
    form.addEventListener('submit', function () {
        saving = true;
    });

    window.addEventListener('beforeunload', function (event) {
        if (!saving && currentValues() !== startingValues) {
            event.preventDefault();
            event.returnValue = '';
        }
    });

    // Saving takes the Save changes button, so pressing Enter in a field can't save by accident
    form.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && event.target.tagName === 'INPUT') {
            event.preventDefault();
        }
    });
})();
