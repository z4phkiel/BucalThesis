document.addEventListener('DOMContentLoaded', function(){
        const API = window.CALENDAR_API;
        const TAG_LABEL = { holiday: 'Holiday', event: 'Event', exam: 'Exam' };
        const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
        const DOW = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        
        const pad = n => String(n).padStart(2, '0');
        const key = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`;   // m is 0-based
        const todayKey = () => { const n = new Date(); return key(n.getFullYear(), n.getMonth(), n.getDate()); };
        const parseKey = k => { const [y, m, d] = k.split('-').map(Number); return new Date(y, m - 1, d); };
        const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        
        // The calendar is generated on the fly, so every year exists automatically.
        // Dates stay 4-digit years so they can be compared as strings (same limit as routes.py).
        const MIN_YEAR = 1000;
        const MAX_YEAR = 9999;
        const MAX_CHIPS = 2;   // tag bars shown per day before "+N more"

        const now = new Date();
        let view = { y: now.getFullYear(), m: now.getMonth() };
        let events = [];
        let selectedDate = null;
        let editingId = null;
        let saving = false;

        const $ = id => document.getElementById(id);
        
        async function api(url, method, body) {
            const csrfToken = document.querySelector(
            'meta[name="csrf-token"]'
        ).content;

        const headers = {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        };

        const r = await fetch(url, {
            method: method,
            headers: headers,
            body: body ? JSON.stringify(body) : undefined
        });

        if (!r.ok) {
            let msg = 'Request failed';

        try {
            msg = (await r.json()).error || msg;
        } catch (e) {}

        throw new Error(msg);
        }

        return r.json();
    }
        
        async function load() {
            events = await api(API, 'GET');
            render();
        }
        
        const isMultiDay = e => e.date !== e.end_date;
        const coversDate = (e, k) => e.date <= k && k <= e.end_date;
        const daysBetween = (a, b) => Math.round((parseKey(b) - parseKey(a)) / 86400000);
        const shortDate = k => parseKey(k).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
        const rangeLabel = e => `${shortDate(e.date)} &ndash; ${shortDate(e.end_date)}`;

        // Gives each event a fixed row, so a multi-day bar stays level across the days it covers.
        function assignLanes(list) {
            const laneEnds = [];
            const lanes = {};
            [...list]
            .sort((a, b) => a.date.localeCompare(b.date) || b.end_date.localeCompare(a.end_date) || a.id - b.id)
            .forEach(e => {
                let lane = laneEnds.findIndex(end => end < e.date);
                if (lane === -1) lane = laneEnds.length;
                laneEnds[lane] = e.end_date;
                lanes[e.id] = lane;
            });
            return lanes;
        }

        function renderChip(e, k, d, days, weekday) {
            const text = `${esc(TAG_LABEL[e.tag] || e.tag)}${e.description ? ': ' + esc(e.description) : ''}`;
            if (!isMultiDay(e)) {
                return `<span class="chip ${esc(e.tag)}" title="${esc(e.description)}">${text}</span>`;
            }

            // A bar is one chip per day, joined across the gaps. The bar breaks at the end of a week or month.
            const lastInRow = weekday === 6 || d === days;
            const classes = ['chip', 'chip-span', esc(e.tag)];
            if (k > e.date) classes.push('span-prev');
            if (k < e.end_date) classes.push(lastInRow ? 'span-next' : 'span-next span-join');

            // The label sits on the first day of each row and runs across the whole bar
            let label = '';
            if (k === e.date || weekday === 0 || d === 1) {
                const cells = Math.min(daysBetween(k, e.end_date) + 1, 7 - weekday, days - d + 1);
                label = `<span class="chip-label" style="--span:${cells}">${text}</span>`;
            }
            return `<span class="${classes.join(' ')}" title="${esc(e.description)}">${label}</span>`;
        }

        function render() {
            renderGrid();
            renderSide();
        }
        
        function renderGrid() {
            const today = todayKey();

            $('calTitle').textContent = `${MONTHS[view.m]} ${view.y}`;
            $('calMonth').value = view.m;
            $('calYear').value = view.y;
            $('calPrev').disabled = view.y === MIN_YEAR && view.m === 0;
            $('calNext').disabled = view.y === MAX_YEAR && view.m === 11;

            let html = DOW.map(d => `<div class="cal-dow">${d}</div>`).join('');
            const first = new Date(view.y, view.m, 1).getDay();
            const days = new Date(view.y, view.m + 1, 0).getDate();

            for (let i = 0; i < first; i++) html += '<div class="cal-empty"></div>';

            const visible = events.filter(e => e.date <= key(view.y, view.m, days) && e.end_date >= key(view.y, view.m, 1));
            const lanes = assignLanes(visible);

            for (let d = 1; d <= days; d++) {
            const k = key(view.y, view.m, d);
            const weekday = (first + d - 1) % 7;
            const list = visible.filter(e => coversDate(e, k));
            const shown = list.filter(e => lanes[e.id] < MAX_CHIPS);
            const rows = shown.reduce((max, e) => Math.max(max, lanes[e.id] + 1), 0);
            let chips = '';
            for (let lane = 0; lane < rows; lane++) {
                const e = shown.find(x => lanes[x.id] === lane);
                chips += e ? renderChip(e, k, d, days, weekday) : '<span class="chip-gap"></span>';
            }
            const hidden = list.length - shown.length;
            const more = hidden > 0 ? `<div class="chip-more">+${hidden} more</div>` : '';
            html += `<div class="cal-day${k === today ? ' today' : ''}" data-date="${k}">
                        <span class="num">${d}</span>${chips}${more}
                    </div>`;
            }
            $('calGrid').innerHTML = html;
        }
        
        function sideItem(e, extra) {
    return `<div class="side-item ${esc(e.tag)}">
        <div class="meta">
            ${esc(TAG_LABEL[e.tag] || e.tag)}
            ${extra ? ' &middot; ' + extra : ''}
        </div>

        <div class="desc">
            ${e.description ? esc(e.description) : '<em>No description</em>'}
        </div>

        ${e.link_url ? `
            <a href="${esc(e.link_url)}"
               target="_blank"
               rel="noopener noreferrer">
                <i class="bi bi-link-45deg"></i> Open link
            </a>
        ` : ''}
    </div>`;
}
        
        function renderSide() {
            const today = todayKey();
            const current = events.filter(e => coversDate(e, today));
            $('sideCurrent').innerHTML = current.length
            ? current.map(e => sideItem(e, isMultiDay(e) ? rangeLabel(e) : 'Today')).join('')
            : '<div class="side-empty">Nothing happening today</div>';
        
            const upcoming = events
            .filter(e => e.date > today)
            .sort((a, b) => a.date.localeCompare(b.date))
            .slice(0, 10);
        
            $('sideUpcoming').innerHTML = upcoming.length
            ? upcoming.map(e => {
                const diff = daysBetween(today, e.date);
                const label = isMultiDay(e) ? rangeLabel(e) : shortDate(e.date);
                return sideItem(e, `${label} (${diff === 1 ? 'tomorrow' : 'in ' + diff + ' days'})`);
                }).join('')
            : '<div class="side-empty">No upcoming items</div>';
        }
        
        // ---- Modal ----
        function openDay(k) {
            selectedDate = k;
            resetForm();
            $('modalDate').textContent = parseKey(k).toLocaleDateString(undefined,
            { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
            renderEntries();
            $('calModalBg').classList.add('open');
        }
        
        function closeModal() {
            $('calModalBg').classList.remove('open');
            selectedDate = null;
        }
        
        function setDates(start, end) {
            $('fStart').value = start;
            $('fEnd').value = end;
            $('fEnd').min = start || `${MIN_YEAR}-01-01`;
        }

        function resetForm() {
            editingId = null;
            setDates(selectedDate || '', selectedDate || '');
            $('fTag').value = 'event';
            $('fDesc').value = '';
            $('fLink').value = '';
            $('formError').textContent = '';
            $('btnSave').textContent = 'Add';
            $('btnCancelEdit').style.display = 'none';
        }
        
        function renderEntries() {
            const list = events.filter(e => coversDate(e, selectedDate));
            $('modalEntries').innerHTML = list.length
        ? list.map(e => `
            <div class="entry">
                <div class="txt">
                    <span class="chip ${esc(e.tag)}"
                        style="display:inline-block;margin:0 6px 0 0">
                        ${esc(TAG_LABEL[e.tag] || e.tag)}
                    </span>

                    ${e.description
                        ? esc(e.description)
                        : '<em>No description</em>'}

                    ${isMultiDay(e) ? `<div class="entry-range">${rangeLabel(e)}</div>` : ''}

                    ${e.link_url ? `
                        <div style="margin-top:6px;">
                            <a href="${esc(e.link_url)}"
                               target="_blank"
                               rel="noopener noreferrer">
                                <i class="bi bi-link-45deg"></i> Open link
                            </a>
                        </div>
                    ` : ''}
                </div>

                <div class="acts">
                    <button type="button" class="cal-btn"
                        data-edit="${e.id}">Edit</button>

                    <button type="button" class="cal-btn danger"
                        data-del="${e.id}">Delete</button>
                </div>
            </div>
        `).join('')
        : '<div class="side-empty">No tags on this day yet</div>';
        }
        
        async function save() {
            if (saving) return;   // ignore extra clicks while a request is running

            const start = $('fStart').value;
            const end = $('fEnd').value;
            if (!start || !end) {
                $('formError').textContent = 'Please enter a start and end date.';
                return;
            }
            if (end < start) {
                $('formError').textContent = 'End date cannot be before the start date.';
                return;
            }
            if (!$('fStart').validity.valid || !$('fEnd').validity.valid) {
                $('formError').textContent = 'Please enter a valid year.';
                return;
            }

            $('formError').textContent = '';
            const body = { date: start, end_date: end, tag: $('fTag').value, description: $('fDesc').value.trim(), link_url: $('fLink').value.trim() };
            const id = editingId;
            const btn = $('btnSave');
            const btnLabel = btn.textContent;
            saving = true;
            btn.disabled = true;
            btn.textContent = 'Saving...';
            try {
            if (id) {
                const updated = await api(`${API}/${id}`, 'PUT', body);
                events = events.map(e => e.id === id ? updated : e);
            } else {
                events.push(await api(API, 'POST', body));
            }
            resetForm();
            renderEntries();
            render();
            } catch (err) {
            btn.textContent = btnLabel;
            $('formError').textContent = err.message;
            } finally {
            saving = false;
            btn.disabled = false;
            }
        }
        
        async function remove(id) {
            if (!confirm('Delete this entry?')) return;
            try {
            await api(`${API}/${id}`, 'DELETE');
            events = events.filter(e => e.id !== id);
            if (editingId === id) resetForm();
            renderEntries();
            render();
            } catch (err) {
            $('formError').textContent = err.message;
            }
        }
        
        // ---- Events ----
        $('calGrid').addEventListener('click', e => {
            const cell = e.target.closest('.cal-day');
            if (cell) openDay(cell.dataset.date);
        });
        
        $('modalEntries').addEventListener('click', e => {
            const edit = e.target.closest('[data-edit]');
            const del = e.target.closest('[data-del]');
            if (edit) {
            const ev = events.find(x => x.id === Number(edit.dataset.edit));
            if (!ev) return;
            editingId = ev.id;
            setDates(ev.date, ev.end_date);
            $('fTag').value = ev.tag;
            $('fDesc').value = ev.description || '';
            $('fLink').value = ev.link_url || '';
            $('btnSave').textContent = 'Save changes';
            $('btnCancelEdit').style.display = '';
            } else if (del) {
            remove(Number(del.dataset.del));
            }
        });
        
        // The end date follows the start date when the start moves past it
        $('fStart').addEventListener('change', () => {
            const start = $('fStart').value;
            setDates(start, start && $('fEnd').value < start ? start : $('fEnd').value);
        });

        $('btnSave').addEventListener('click', save);
        $('btnClose').addEventListener('click', closeModal);
        $('btnCancelEdit').addEventListener('click', resetForm);
        $('calModalBg').addEventListener('click', e => { if (e.target === $('calModalBg')) closeModal(); });
        
        $('calPrev').addEventListener('click', () => {
            view.m--; if (view.m < 0) { view.m = 11; view.y--; }
            renderGrid();
        });
        $('calNext').addEventListener('click', () => {
            view.m++; if (view.m > 11) { view.m = 0; view.y++; }
            renderGrid();
        });
        $('calToday').addEventListener('click', () => {
            const n = new Date();
            view = { y: n.getFullYear(), m: n.getMonth() };
            renderGrid();
        });

        $('calMonth').innerHTML = MONTHS.map((name, i) => `<option value="${i}">${name}</option>`).join('');
        $('calMonth').addEventListener('change', e => {
            view.m = Number(e.target.value);
            renderGrid();
        });
        $('calYear').addEventListener('change', e => {
            const y = Number(e.target.value);
            if (Number.isInteger(y) && y >= MIN_YEAR && y <= MAX_YEAR) view.y = y;
            renderGrid();   // also puts back the current year if the value was rejected
        });

        load().catch(err => { $('sideCurrent').innerHTML = `<div class="side-empty">${esc(err.message)}</div>`; });
});