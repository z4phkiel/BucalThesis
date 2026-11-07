// Masterlist: search, page controls, and fitting the rows to the screen so the page doesn't need scrolling
document.addEventListener('DOMContentLoaded', function () {
    const MIN_ROWS = 5;

    const rows = Array.from(document.querySelectorAll('.student-row'));
    if (!rows.length) {
        return;
    }

    const search = document.getElementById('studentSearch');
    const frame = document.getElementById('studentTable');
    const content = document.getElementById('pageContent');
    const noResults = document.getElementById('noSearchResults');
    const pager = document.getElementById('studentPager');
    const pagerList = document.getElementById('studentPagerList');
    const pagerSummary = document.getElementById('studentPagerSummary');
    const rowHeight = rows[0].getBoundingClientRect().height;

    let matches = rows;
    let pageSize = MIN_ROWS;
    let currentPage = 1;
    let anchorRow = 0;      // first row of the page the user chose. Resizing keeps this row on screen.

    function pageCount() {
        return Math.max(1, Math.ceil(matches.length / pageSize));
    }

    // Always 7 slots once there are many pages, so the Next button stays put. null is a gap: 1 ... 4 5 6 ... 20
    function pageSlots() {
        const total = pageCount();
        if (total <= 7) {
            return Array.from({ length: total }, function (_, i) { return i + 1; });
        }
        if (currentPage <= 4) {
            return [1, 2, 3, 4, 5, null, total];
        }
        if (currentPage >= total - 3) {
            return [1, null, total - 4, total - 3, total - 2, total - 1, total];
        }
        return [1, null, currentPage - 1, currentPage, currentPage + 1, null, total];
    }

    function pagerItem(label, page, isDisabled) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'page-link';
        button.textContent = label;
        button.dataset.page = page;
        button.disabled = isDisabled;

        const item = document.createElement('li');
        item.className = 'page-item';
        item.classList.toggle('disabled', isDisabled);
        if (page === currentPage) {
            item.classList.add('active');
            button.setAttribute('aria-current', 'page');
        }
        item.appendChild(button);
        return item;
    }

    function drawPager() {
        pagerList.replaceChildren(
            pagerItem('Previous', 'previous', currentPage === 1),
            ...pageSlots().map(function (slot) {
                return slot ? pagerItem(String(slot), slot, false) : pagerItem('...', 'gap', true);
            }),
            pagerItem('Next', 'next', currentPage === pageCount())
        );
        pagerList.hidden = pageCount() < 2;

        if (!matches.length) {
            pagerSummary.textContent = '';
            return;
        }
        const first = (currentPage - 1) * pageSize + 1;
        const last = Math.min(currentPage * pageSize, matches.length);
        const noun = (search.value.trim() ? 'matching ' : '') + (matches.length === 1 ? 'student' : 'students');
        pagerSummary.textContent = `Showing ${first} to ${last} of ${matches.length} ${noun}`;
    }

    function drawPage(page) {
        currentPage = Math.min(Math.max(page, 1), pageCount());
        const first = (currentPage - 1) * pageSize;
        const shown = new Set(matches.slice(first, first + pageSize));
        rows.forEach(function (row) {
            row.hidden = !shown.has(row);
        });
        noResults.hidden = matches.length > 0;
        drawPager();
    }

    function showPage(page) {
        drawPage(page);
        anchorRow = (currentPage - 1) * pageSize;
    }

    // Shows as many rows as fit above the bottom of the screen. The table keeps that height on a shorter
    // page, so the page controls don't move while searching or changing pages.
    function fitToScreen() {
        if (!frame.offsetHeight) {
            return;     // hidden behind the loading placeholder
        }
        const tableChrome = frame.querySelector('thead').getBoundingClientRect().height +
            frame.offsetHeight - frame.clientHeight;
        const above = frame.getBoundingClientRect().top + window.scrollY;
        const below = pager.offsetHeight + parseFloat(getComputedStyle(pager).marginTop) +
            parseFloat(getComputedStyle(content).paddingBottom);
        const size = Math.max(MIN_ROWS, Math.floor((window.innerHeight - above - tableChrome - below) / rowHeight));

        if (size !== pageSize) {
            // An open menu would lose its row if that row moves to another page
            frame.querySelectorAll('.student-actions.show').forEach(function (button) {
                bootstrap.Dropdown.getOrCreateInstance(button).hide();
            });
            pageSize = size;
            drawPage(Math.floor(anchorRow / size) + 1);
        }
        frame.style.minHeight = `${tableChrome + Math.min(rows.length, size) * rowHeight}px`;
    }

    search.addEventListener('input', function () {
        const term = this.value.trim().toLowerCase();
        matches = rows.filter(function (row) {
            const name = row.querySelector('.student-name').textContent.toLowerCase();
            const lrn = row.querySelector('.student-lrn').textContent.toLowerCase();
            return name.includes(term) || lrn.includes(term);
        });
        showPage(1);
    });

    pagerList.addEventListener('click', function (event) {
        const button = event.target.closest('button[data-page]');
        if (!button || button.disabled) {
            return;
        }
        const target = button.dataset.page;
        if (target === 'previous') {
            showPage(currentPage - 1);
        } else if (target === 'next') {
            showPage(currentPage + 1);
        } else {
            showPage(Number(target));
        }
        // The buttons were redrawn, so focus goes back to the same one, or the current page if it is now disabled
        const again = pagerList.querySelector(`[data-page="${target}"]:not(:disabled)`);
        (again || pagerList.querySelector('[aria-current]')).focus();
    });

    window.addEventListener('resize', fitToScreen);

    pager.hidden = false;
    showPage(1);        // draws the page controls first, because fitToScreen measures them
    fitToScreen();
});
