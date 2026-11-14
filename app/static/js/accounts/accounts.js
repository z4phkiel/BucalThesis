document.addEventListener('DOMContentLoaded', function () {
    // The Accounts popups are checked here before they are sent (their forms have novalidate, so the browser's
    // own bubbles never show). Every problem is listed in one warning popup. The server checks the same rules again.
    const warning = document.getElementById('formWarning');
    const warningList = document.getElementById('formWarningList');
    const takenUsernames = Array.from(document.querySelectorAll('tr[data-username]'), function (row) {
        return row.dataset.username.toLowerCase();
    });
    let fixFirst = null;

    // [field, message] for each problem, in the order the fields appear
    function problems(form) {
        const found = [];
        const name = form.elements.full_name;
        const username = form.elements.username;
        const password = form.elements.password;
        const confirm = form.elements.confirm_password;

        if (name && !name.value.trim()) {
            found.push([name, 'Enter the full name.']);
        }
        if (username) {
            const value = username.value.trim();
            const pattern = new RegExp('^(?:' + username.dataset.pattern + ')$');
            // An older username outside the rule can stay as it is (same as the server)
            if (!value) {
                found.push([username, 'Enter a username.']);
            } else if (value !== username.defaultValue && !pattern.test(value)) {
                found.push([username, 'A username is 3 to 50 letters, numbers, dots, dashes or underscores.']);
            } else if (value.toLowerCase() !== username.defaultValue.toLowerCase() && takenUsernames.includes(value.toLowerCase())) {
                found.push([username, 'That username is already taken.']);
            }
        }
        if (password) {
            if (password.value.length < password.minLength) {
                found.push([password, 'The password needs at least ' + password.minLength + ' characters.']);
            }
            if (confirm.value !== password.value) {
                found.push([confirm, 'The two passwords do not match.']);
            }
        }
        return found;
    }

    function unmark(field) {
        field.classList.remove('is-invalid');
        field.removeAttribute('aria-invalid');
    }

    document.querySelectorAll('.modal form[novalidate]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            form.querySelectorAll('.is-invalid').forEach(unmark);
            const found = problems(form);
            if (!found.length) {
                return;
            }

            event.preventDefault();
            found.forEach(function (problem) {
                problem[0].classList.add('is-invalid');
                problem[0].setAttribute('aria-invalid', 'true');
            });
            warningList.replaceChildren.apply(warningList, found.map(function (problem) {
                const item = document.createElement('li');
                item.textContent = problem[1];
                return item;
            }));
            fixFirst = found[0][0];
            // Inside the open popup, so Bootstrap's focus trap leaves the warning alone
            form.appendChild(warning);
            warning.showModal();
        });

        form.addEventListener('input', function (event) {
            unmark(event.target);
        });

        form.closest('.modal').addEventListener('hidden.bs.modal', function () {
            form.querySelectorAll('.is-invalid').forEach(unmark);
        });
    });

    warning.querySelector('[data-warning-close]').addEventListener('click', function () {
        warning.close();
    });

    // Esc closes only the warning, not the popup under it
    warning.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            event.stopPropagation();
        }
    });

    warning.addEventListener('close', function () {
        if (fixFirst) {
            fixFirst.focus();
        }
    });
});
