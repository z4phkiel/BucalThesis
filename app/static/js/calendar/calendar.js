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
        // Navigation range: January of this year -> December of next year (rolls forward each Jan 1).
        const bounds = () => {
            const y = new Date().getFullYear();
            return { min: y * 12, max: (y + 1) * 12 + 11 };
        };
        
        const now = new Date();
        let view = { y: now.getFullYear(), m: now.getMonth() };
        let events = [];
        let selectedDate = null;
        let editingId = null;
        
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
        
        function byDate() {
            const map = {};
            events.forEach(e => { (map[e.date] = map[e.date] || []).push(e); });
            return map;
        }
        
        function render() {
            renderGrid();
            renderSide();
        }
        
        function renderGrid() {
            const map = byDate();
            const today = todayKey();
            const b = bounds();
            const idx = view.y * 12 + view.m;
        
            $('calTitle').textContent = `${MONTHS[view.m]} ${view.y}`;
            $('calPrev').disabled = idx <= b.min;
            $('calNext').disabled = idx >= b.max;
        
            let html = DOW.map(d => `<div class="cal-dow">${d}</div>`).join('');
            const first = new Date(view.y, view.m, 1).getDay();
            const days = new Date(view.y, view.m + 1, 0).getDate();
        
            for (let i = 0; i < first; i++) html += '<div class="cal-empty"></div>';
        
            for (let d = 1; d <= days; d++) {
            const k = key(view.y, view.m, d);
            const list = map[k] || [];
            const chips = list.slice(0, 2).map(e =>
                `<span class="chip ${esc(e.tag)}" title="${esc(e.description)}">${esc(TAG_LABEL[e.tag] || e.tag)}${e.description ? ': ' + esc(e.description) : ''}</span>`
            ).join('');
            const more = list.length > 2 ? `<div class="chip-more">+${list.length - 2} more</div>` : '';
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
            const current = events.filter(e => e.date === today);
            $('sideCurrent').innerHTML = current.length
            ? current.map(e => sideItem(e, 'Today')).join('')
            : '<div class="side-empty">Nothing happening today</div>';
        
            const t0 = parseKey(today);
            const upcoming = events
            .filter(e => e.date > today)
            .sort((a, b) => a.date.localeCompare(b.date))
            .slice(0, 10);
        
            $('sideUpcoming').innerHTML = upcoming.length
            ? upcoming.map(e => {
                const dt = parseKey(e.date);
                const diff = Math.round((dt - t0) / 86400000);
                const label = dt.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
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
        
        function resetForm() {
            editingId = null;
            $('fTag').value = 'event';
            $('fDesc').value = '';
            $('fLink').value = '';
            $('formError').textContent = '';
            $('btnSave').textContent = 'Add';
            $('btnCancelEdit').style.display = 'none';
        }
        
        function renderEntries() {
            const list = events.filter(e => e.date === selectedDate);
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
            $('formError').textContent = '';
            const body = { date: selectedDate, tag: $('fTag').value, description: $('fDesc').value.trim(), link_url: $('fLink').value.trim() };
            try {
            if (editingId) {
                const updated = await api(`${API}/${editingId}`, 'PUT', body);
                events = events.map(e => e.id === editingId ? updated : e);
            } else {
                events.push(await api(API, 'POST', body));
            }
            resetForm();
            renderEntries();
            render();
            } catch (err) {
            $('formError').textContent = err.message;
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
            $('fTag').value = ev.tag;
            $('fDesc').value = ev.description || '';
            $('fLink').value = ev.link_url || '';
            $('btnSave').textContent = 'Save changes';
            $('btnCancelEdit').style.display = '';
            } else if (del) {
            remove(Number(del.dataset.del));
            }
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
        
        load().catch(err => { $('sideCurrent').innerHTML = `<div class="side-empty">${esc(err.message)}</div>`; });
});