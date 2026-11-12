// The activity log, in two places: the sidebar bell's card with the latest Masterlist, Calendar and
// Linkage/Files actions, and the Activity Log tab on each of those pages with every entry's details.
// Both load each time they open, so they are current and no page waits for them.
document.addEventListener('DOMContentLoaded', function () {
    const placeholder = document.getElementById('activityPlaceholder');
    if (!placeholder) {
        return;
    }
    const loading = placeholder.innerHTML;

    function fetchHtml(url) {
        return fetch(url, { cache: 'no-store' }).then(function (res) {
            if (res.status === 401) {
                // Logged out in the meantime: reloading goes to the login page, so this never resolves
                window.location.reload();
                return new Promise(function () {});
            }
            if (!res.ok) {
                throw new Error(`status ${res.status}`);
            }
            return res.text();
        });
    }

    const loadError = `<div class="dashboard-load-error activity-error">
        <p>The activity log could not be loaded.</p>
        <button type="button" class="activity-retry" data-activity-retry>Try again</button>
    </div>`;

    // Shows url's HTML in target, with the placeholder until it arrives, then runs then(). Only the newest
    // request for a target may fill it, so a slow one can't replace a later one.
    const latest = new Map();
    function loadInto(target, url, then) {
        const request = (latest.get(target) || 0) + 1;
        latest.set(target, request);
        target.innerHTML = loading;
        target.setAttribute('aria-busy', 'true');
        fetchHtml(url)
            .then(function (html) {
                if (latest.get(target) === request) {
                    target.innerHTML = html;
                    if (then) {
                        then();
                    }
                }
            })
            .catch(function () {
                if (latest.get(target) === request) {
                    target.innerHTML = loadError;
                }
            })
            .finally(function () {
                if (latest.get(target) === request) {
                    target.removeAttribute('aria-busy');
                }
            });
    }

    // ---------- The bell's card ----------
    const toggle = document.getElementById('activityToggle');
    const card = document.getElementById('activityCard');
    const list = document.getElementById('activityList');
    const filters = card.querySelectorAll('[data-area]');
    let area = '';

    function loadCard() {
        loadInto(list, card.dataset.url + (area ? '?area=' + encodeURIComponent(area) : ''), refreshDots);
    }

    function setOpen(open, returnFocus) {
        card.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        if (open) {
            loadCard();
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
            loadCard();
        } else if (event.target.closest('[data-activity-retry]')) {
            loadCard();
        } else if (event.target.closest('[data-activity-close]')) {
            setOpen(false, true);
        } else if (event.target.closest('a[href]')) {
            setOpen(false);     // an entry: it goes to its details in a page's Activity Log tab
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

    // ---------- Red dots on the bell and the Activity Log tab: entries by other users not seen yet ----------
    // Checked when a page loads and after the card or the tab shows entries (the server marks those seen).
    // Never on a timer: every request renews the session, so polling would keep idle users logged in.
    const tabButton = document.getElementById('activityTabButton');
    let dotsRequest = 0;

    // CSS draws the dot; the label says the same to screen readers
    function setDot(element, on) {
        element.classList.toggle('has-unseen', on);
        if (on) {
            element.setAttribute('aria-label', element.textContent.trim() + ', new activity');
        } else {
            element.removeAttribute('aria-label');
        }
    }

    function refreshDots() {
        const request = ++dotsRequest;     // only the newest answer counts, as one sent before a "seen" is stale
        fetch(toggle.dataset.unseenUrl, { cache: 'no-store' })
            .then(function (res) {
                return res.ok ? res.json() : null;
            })
            .then(function (data) {
                if (!data || request !== dotsRequest) {
                    return;
                }
                setDot(toggle, data.areas.length > 0);
                if (tabButton) {
                    setDot(tabButton, data.areas.includes(tabButton.dataset.activityArea));
                }
            })
            .catch(function () {});     // only the dots depend on it, so they stay as they were
    }
    refreshDots();

    // ---------- The Activity Log tab (Masterlist, Calendar and Linkage/Files only) ----------
    const pane = document.getElementById('activityTab');
    if (!pane || !tabButton) {
        return;
    }
    const details = pane.querySelector('[data-activity-details]');
    const tab = bootstrap.Tab.getOrCreateInstance(tabButton);

    // The entry a link pointed at (#activity-<id>), if it is on the first page
    function highlightEntry() {
        const row = /^#activity-\d+$/.test(location.hash) && document.getElementById(location.hash.slice(1));
        if (row) {
            row.classList.add('is-highlighted');
            row.scrollIntoView({ block: 'center' });
        }
    }

    function loadDetails() {
        loadInto(details, pane.dataset.url, function () {
            highlightEntry();
            refreshDots();
        });
    }

    // Adds the next page's rows under the table
    function showOlder(more) {
        const request = latest.get(details);
        more.disabled = true;
        more.textContent = 'Loading...';
        fetchHtml(pane.dataset.url + '?before=' + encodeURIComponent(more.dataset.before))
            .then(function (html) {
                if (latest.get(details) !== request) {
                    return;     // the tab was reloaded meanwhile, so these rows no longer follow on
                }
                const page = new DOMParser().parseFromString(html, 'text/html');
                details.querySelector('.activity-table tbody').append(...page.querySelectorAll('.activity-table tbody tr'));
                const next = page.querySelector('[data-activity-more]');
                if (next) {
                    more.replaceWith(next);
                } else {
                    more.remove();
                }
            })
            .catch(function () {
                more.disabled = false;
                more.textContent = 'Could not load. Try again';
            });
    }

    // The address keeps the open tab (#activity), so a reload or the Back button comes back to it
    tabButton.addEventListener('shown.bs.tab', function () {
        if (!location.hash.startsWith('#activity')) {
            history.replaceState(null, '', '#activity');
        }
        loadDetails();
    });
    document.getElementById('mainTabButton').addEventListener('shown.bs.tab', function () {
        history.replaceState(null, '', location.pathname + location.search);
    });

    details.addEventListener('click', function (event) {
        const more = event.target.closest('[data-activity-more]');
        if (more) {
            showOlder(more);
        } else if (event.target.closest('[data-activity-retry]')) {
            loadDetails();
        }
    });

    // #activity or #activity-<id> opens the tab: on arrival, from the Back button or from a card entry
    function followHash() {
        if (!/^#activity(-\d+)?$/.test(location.hash)) {
            return;
        }
        if (tabButton.classList.contains('active')) {
            loadDetails();
        } else {
            tab.show();
        }
    }
    window.addEventListener('hashchange', followHash);

    // A link to the address already showing changes nothing, so there is no hashchange to follow
    document.addEventListener('click', function (event) {
        const link = event.target.closest('a[href]');
        if (link && link.href === location.href && /^#activity/.test(link.hash)) {
            event.preventDefault();
            followHash();
        }
    });
    followHash();
});
