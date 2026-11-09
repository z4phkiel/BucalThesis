// While the server works on a page, the browser keeps showing the old one. So when a link to one of the
// main pages is clicked, this shows a placeholder of that page until the new page arrives and replaces it.
document.addEventListener('DOMContentLoaded', function () {
    const SHOW_DELAY_MS = 120;      // pages that respond quickly never flash a placeholder
    const GIVE_UP_MS = 20000;       // brings the current page back if loading was stopped or never finishes

    // Ctrl, Shift or middle clicks open a new tab or window, so they never replace this page
    function isPlainClick(event) {
        return event.button === 0 && !(event.ctrlKey || event.metaKey || event.shiftKey || event.altKey);
    }

    // The sidebar link to the page already open would only reload it and lose a half-filled form,
    // a search or a sort, so a plain click (or Enter) on it does nothing. Registered first, so the
    // placeholder below sees it as handled.
    document.addEventListener('click', function (event) {
        if (isPlainClick(event) && event.target.closest('.sidebar a[aria-current="page"]')) {
            event.preventDefault();
        }
    });

    const host = document.getElementById('pageSkeleton');
    if (!host) {
        return;
    }

    // Unclosed tags in a page's template can leave this nested inside the content it replaces, which would hide it too
    document.querySelector('.main-content').appendChild(host);

    const body = document.body;
    const skeletons = new Map();
    document.querySelectorAll('template[data-skeleton-path]').forEach(function (template) {
        skeletons.set(template.dataset.skeletonPath, template);
    });

    let showTimer = null;
    let giveUpTimer = null;
    let highlighted = null;
    let scrollBefore = 0;

    function clearTimers() {
        clearTimeout(showTimer);
        clearTimeout(giveUpTimer);
    }

    function highlight(path) {
        if (highlighted) {
            highlighted.classList.remove('is-navigation-target');
        }
        highlighted = Array.from(document.querySelectorAll('.sidebar .nav-link')).find(function (link) {
            return new URL(link.href).pathname === path;
        }) || null;
        if (highlighted) {
            highlighted.classList.add('is-navigation-target');
        }
    }

    // Bootstrap makes scrolling smooth by default, but these jumps happen as the content swaps
    function jumpTo(top) {
        window.scrollTo({ top: top, behavior: 'instant' });
    }

    function showSkeleton(template) {
        host.replaceChildren(template.content.cloneNode(true));
        host.hidden = false;
        if (!body.classList.contains('is-page-loading')) {
            scrollBefore = window.scrollY;
            body.classList.add('is-page-loading');
        }
        jumpTo(0);
    }

    function restorePage() {
        const wasShowing = body.classList.contains('is-page-loading');
        clearTimers();
        body.classList.remove('is-navigating', 'is-page-loading');
        if (highlighted) {
            highlighted.classList.remove('is-navigation-target');
            highlighted = null;
        }
        host.hidden = true;
        host.replaceChildren();
        if (wasShowing) {
            jumpTo(scrollBefore);
        }
    }

    // A page with unsaved work asks before leaving, and the user may choose to stay on it
    function pageWillAskToStay() {
        const check = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(check);
        return check.defaultPrevented;
    }

    function skeletonForClick(event) {
        if (event.defaultPrevented || !isPlainClick(event)) {
            return null;
        }

        const link = event.target.closest('a[href]');
        if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) {
            return null;
        }

        const url = new URL(link.href);
        if (url.origin !== window.location.origin) {
            return null;
        }
        if (url.hash && url.pathname === window.location.pathname) {
            return null;
        }
        return skeletons.get(url.pathname) || null;
    }

    document.addEventListener('click', function (event) {
        const template = skeletonForClick(event);
        if (!template || pageWillAskToStay()) {
            return;
        }

        clearTimers();
        body.classList.add('is-navigating');
        highlight(template.dataset.skeletonPath);

        // Clicking another link while a placeholder is showing swaps it right away
        if (body.classList.contains('is-page-loading')) {
            showSkeleton(template);
        } else {
            showTimer = setTimeout(function () {
                showSkeleton(template);
            }, SHOW_DELAY_MS);
        }
        giveUpTimer = setTimeout(restorePage, GIVE_UP_MS);
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && body.classList.contains('is-navigating')) {
            restorePage();
        }
    });

    // The Back button can restore this page exactly as it was left, placeholder included
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            restorePage();
        }
    });
});
