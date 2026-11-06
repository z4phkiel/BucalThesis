document.addEventListener('DOMContentLoaded', function () {
    const sections = [...document.querySelectorAll('.form-part')];
    const nodes = [...document.querySelectorAll('.step-node')];
    const fill = document.getElementById('stepFill');
    const prevBtn = document.getElementById('prev_part_btn');
    const nextBtn = document.getElementById('next_part_btn');
    const submitBtn = document.getElementById('submit_btn');
    const sigBtn = document.getElementById('open_sig_modal_btn');
    if (!sections.length || sections.length !== nodes.length) return;

    const form = sections[0].closest('form') || document.querySelector('form');
    form.noValidate = true;
    let current = 0;

    // Fields that may stay empty (matched by input name)
    const OPTIONAL_NAMES = [
        // Learner's information
        'psa_birth_cert_no', 'extension_name',
        // Senior high school
        'semester', 'track', 'strand',
    ];
    const OPTIONAL_PREFIXES = ['father_', 'mother_maiden_'];   // father and mother are optional

    const isOptional = name =>
        OPTIONAL_NAMES.includes(name) || OPTIONAL_PREFIXES.some(p => name.startsWith(p));

    const filled = id => {
        const el = document.getElementById(id);
        return !!el && el.value.trim() !== '';
    };
    const checkedValue = name => {
        const el = document.querySelector(`input[name="${name}"]:checked`);
        return el ? el.value : null;
    };

    // Returns the first problem in a part, or null if the part is complete
    function findProblem(i) {
        const sec = sections[i];
        const seen = new Set();

        for (const f of sec.querySelectorAll('input, select, textarea')) {
            if (f.disabled || f.readOnly) continue;                       // not applicable right now
            if (['hidden', 'button', 'submit'].includes(f.type)) continue;
            if (f.name === 'lrn_no' && checkedValue('has_lrn') === 'no') continue;

            const isGroup = f.type === 'radio' || f.type === 'checkbox';

            // Optional fields: may be empty, but if filled they must still be valid (e.g. phone format)
            if (isOptional(f.name)) {
                if (!isGroup && f.value.trim() !== '' && !f.checkValidity()) return { el: f };
                continue;
            }

            // Radio / checkbox groups: at least one must be chosen
            if (isGroup) {
                if (seen.has(f.name)) continue;
                seen.add(f.name);
                const group = [...sec.querySelectorAll(`input[name="${f.name}"]:not(:disabled)`)];
                if (!group.some(g => g.checked)) {
                    return {
                        el: group[0],
                        msg: f.name === 'disabilities'
                            ? 'Please specify the type of disability.'
                            : 'Please select at least one option.',
                    };
                }

                // Visual Impairment needs a sub-choice: blind or low vision
                if (f.name === 'disabilities') {
                    const visual = document.getElementById('dis_visual');
                    const subs = ['dis_blind', 'dis_low_vision'].map(id => document.getElementById(id));
                    if (visual && visual.checked && !subs.some(s => s && s.checked)) {
                        return {
                            el: subs.find(s => s && !s.disabled) || visual,
                            msg: 'Please choose blind or low vision.',
                        };
                    }
                }
                continue;
            }

            if (f.value.trim() === '') return { el: f, msg: 'Please fill out this field.' };
            if (!f.checkValidity()) return { el: f };
        }

        
        if (sec.contains(document.getElementById('signature_data')) && !filled('signature_data')) {
            return { sig: true };
        }
        return null;
    }

    function showSigError(on) {
        let note = document.getElementById('sig_error');
        if (on && !note && sigBtn) {
            note = document.createElement('div');
            note.id = 'sig_error';
            note.className = 'text-danger small mb-1';
            note.textContent = 'Please add a signature.';
            sigBtn.insertAdjacentElement('afterend', note);
        }
        if (!on && note) note.remove();
    }

    // Validates one part; on failure opens it and points at the problem
    function validatePart(i) {
        sections[i].querySelectorAll('input, select, textarea').forEach(f => f.setCustomValidity(''));
        showSigError(false);

        const p = findProblem(i);
        if (!p) return true;

        show(i);
        if (p.sig) {
            showSigError(true);
            sigBtn.focus();
        } else {
            if (p.msg) p.el.setCustomValidity(p.msg);
            p.el.reportValidity();
            const clear = () => p.el.setCustomValidity('');
            p.el.addEventListener('input', clear, { once: true });
            p.el.addEventListener('change', clear, { once: true });
        }
        return false;
    }

    function render() {
        sections.forEach((sec, i) => { sec.hidden = i !== current; });

        nodes.forEach((node, i) => {
            const done = !findProblem(i);
            node.classList.toggle('active', i === current);
            node.classList.toggle('done', done);
            if (i === current) {
                node.setAttribute('aria-current', 'step');
            } else {
                node.removeAttribute('aria-current');
            }
            node.querySelector('.step-dot').textContent = done ? '✓' : i + 1;
        });
        fill.style.width = (current / (nodes.length - 1)) * 100 + '%';

        prevBtn.hidden = current === 0;
        nextBtn.hidden = current === sections.length - 1;
        submitBtn.hidden = current !== sections.length - 1;
    }

    function show(i) { current = i; render(); }

    function goTo(target) {
        // Going forward: every part from here up to the target must be complete
        for (let i = current; i < target; i++) {
            if (!validatePart(i)) return;
        }
        show(target);
        sections[target].scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    nodes.forEach((node, i) => node.addEventListener('click', () => goTo(i)));
    prevBtn.addEventListener('click', () => goTo(current - 1));
    nextBtn.addEventListener('click', () => goTo(current + 1));

    // Enter moves to the next part instead of submitting early
    form.addEventListener('keydown', e => {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT' && current < sections.length - 1) {
            e.preventDefault();
            goTo(current + 1);
        }
    });

    // Submit: check all three parts, stop at the first one with a problem
    form.addEventListener('submit', e => {
        for (let i = 0; i < sections.length; i++) {
            if (!validatePart(i)) { e.preventDefault(); return; }
        }
    });

    document.addEventListener('input', render);
    document.addEventListener('change', render);
    document.addEventListener('click', () => setTimeout(render, 50));

    // The first render only sets the starting state, so it shouldn't animate
    const stepper = fill.closest('.stepper');
    stepper.classList.add('stepper-no-motion');
    render();
    void stepper.offsetWidth;   // applies the starting state before the transitions come back
    stepper.classList.remove('stepper-no-motion');

    // The bar gets its background once it has stuck to the top of the window.
    // This marker sits just above it and takes up no space, so it scrolls away at that moment.
    const wrap = stepper.closest('.stepper-wrap');
    const stickyTop = parseFloat(getComputedStyle(wrap).top);
    const marker = document.createElement('div');
    marker.setAttribute('aria-hidden', 'true');
    wrap.before(marker);
    new IntersectionObserver(
        ([entry]) => wrap.classList.toggle('is-stuck', !entry.isIntersecting),
        { rootMargin: `-${stickyTop}px 0px 0px 0px` }
    ).observe(marker);
});