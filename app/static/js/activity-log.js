// The bell in the sidebar opens a card with the latest Masterlist, Calendar and Linkage/Files actions.
// The entries load each time the card opens, so they are current and no page waits for them.
document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('activityToggle');
    const card = document.getElementById('activityCard');
    if (!toggle || !card) {
        return;
    }
    const list = document.getElementById('activityList');
    const placeholder = document.getElementById('activityPlaceholder').innerHTML;
    const filters = card.querySelectorAll('[data-area]');
    let area = '';
    let latest = 0;     // only the newest request may fill the list, so a slow one can't replace a later filter

    function load() {
        const request = ++latest;
        list.innerHTML = placeholder;
        list.setAttribute('aria-busy', 'true');
        fetch(card.dataset.url + (area ? '?area=' + encodeURIComponent(area) : ''), { cache: 'no-store' })
            .then(function (res) {
                if (res.status === 401) {
                    // Logged out in the meantime: reloading goes to the login page, so this never resolves
                    window.location.reload();
                    return new Promise(function () {});
                }
                if (!res.ok) {
                    throw new Error(`status ${res.status}`);
                }
                return res.text();
            })
            .then(function (html) {
                if (request === latest) {
                    list.innerHTML = html;
                }
            })
            .catch(function () {
                if (request === latest) {
                    list.innerHTML = `<div class="dashboard-load-error activity-error">
                        <p>The activity log could not be loaded.</p>
                        <button type="button" class="activity-retry" data-activity-retry>Try again</button>
                    </div>`;
                }
            })
            .finally(function () {
                if (request === latest) {
                    list.removeAttribute('aria-busy');
                }
            });
    }

    function setOpen(open, returnFocus) {
        card.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        if (open) {
            load();
        } else if (returnFocus) {
            toggle.focus();
        }
    }

    toggle.addEventListener('click', function () {
        setOpen(card.hidden);
    });

    card.addEventListener('click', function (event) {
        const filter = event.target.closest('[data-area]');
        if (filter) {
            area = filter.dataset.area;
            filters.forEach(function (button) {
                button.setAttribute('aria-pressed', String(button === filter));
            });
            load();
        } else if (event.target.closest('[data-activity-retry]')) {
            load();
        } else if (event.target.closest('[data-activity-close]')) {
            setOpen(false, true);
        }
    });

    // Escape or a click anywhere else closes it. The click's path is checked rather than its target,
    // because Try again replaces the button that was clicked before the click gets here.
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !card.hidden) {
            setOpen(false, card.contains(document.activeElement));
        }
    });
    document.addEventListener('click', function (event) {
        const path = event.composedPath();
        if (!card.hidden && !path.includes(card) && !path.includes(toggle)) {
            setOpen(false);
        }
    });
});
