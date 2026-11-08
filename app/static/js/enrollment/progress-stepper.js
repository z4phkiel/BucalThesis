document.addEventListener('DOMContentLoaded', function () {
    const sections = [...document.querySelectorAll('.form-part')];
    const nodes = [...document.querySelectorAll('.step-node')];
    const fill = document.getElementById('stepFill');
    const prevBtn = document.getElementById('prev_part_btn');
    const nextBtn = document.getElementById('next_part_btn');
    const submitBtn = document.getElementById('submit_btn');
    const sigBtn = document.getElementById('open_sig_modal_btn');
    const wrap = fill.closest('.stepper-wrap');
    const captionStep = document.getElementById('stepCurrentStep');
    const captionName = document.getElementById('stepCurrentName');
    const scrollFill = document.getElementById('stepScroll');
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

            if (f.value.trim() === '') {
                return { el: f, msg: f.tagName === 'SELECT' ? 'Please choose an option.' : 'Please fill out this field.' };
            }
            if (!f.checkValidity()) return { el: f };
        }

        
        if (sec.contains(document.getElementById('signature_data')) && !filled('signature_data')) {
            return { sig: true };
        }
        return null;
    }

    // ---------- A step that can't be finished yet ----------
    // Instead of the browser's warning bubble, a small panel slides up from the bottom naming the field,
    // the field gets a red ring, and Next (or Submit) shows a lock until the field is done.
    const alertBox = document.getElementById('stepAlert');
    const alertTitle = document.getElementById('stepAlertTitle');
    const alertMessage = document.getElementById('stepAlertMessage');
    let blocked = null;     // what is holding up a step: { part, target, message, marks, button }
    let alertTimer = null;

    const GROUP_NAMES = { distance_learning_modalities: 'Distance learning preference' };   // no question just before it
    const clean = text => text.replace(/\s+/g, ' ').trim().replace(/^\d+\.\s*/, '').replace(/:$/, '');
    const targetOf = p => (p.sig ? sigBtn : p.el);
    const isGroup = el => el.type === 'radio' || el.type === 'checkbox';

    // The field's label, or for a radio or checkbox group, the question just before it
    function fieldName(p) {
        if (p.sig) return 'Signature';
        const el = p.el;
        if (GROUP_NAMES[el.name]) return GROUP_NAMES[el.name];
        if (!isGroup(el)) return clean(el.labels[0]?.textContent || el.getAttribute('aria-label') || el.placeholder || el.name);
        for (let node = el.closest('.form-check') || el; node && node !== form; node = node.parentElement) {
            for (let prev = node.previousElementSibling; prev; prev = prev.previousElementSibling) {
                const text = clean(prev.textContent);
                if (text && !prev.querySelector('input, select, textarea')) return text;
            }
        }
        return 'This question';
    }

    function problemMessage(p) {
        if (p.sig) return 'Please add a signature.';
        if (p.msg) return p.msg;
        const text = p.el.validity.patternMismatch && p.el.title ? p.el.title : p.el.validationMessage;
        return /[.!?]$/.test(text) ? text : text + '.';
    }

    function setMessage(p) {
        const name = document.createElement('strong');
        name.textContent = fieldName(p);
        alertMessage.replaceChildren(name, ' ' + problemMessage(p));
    }

    function goToProblem() {
        blocked.target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        blocked.target.focus({ preventScroll: true });
    }

    function unmark() {
        if (!blocked) return;
        blocked.marks.forEach(m => {
            m.classList.remove('is-blocked');
            m.removeAttribute('aria-invalid');
        });
        blocked.button.classList.remove('is-locked');
    }

    function closeAlert() {
        clearTimeout(alertTimer);
        alertBox.classList.remove('is-open', 'is-nudged');
    }

    function clearBlock() {
        unmark();
        blocked = null;
        closeAlert();
    }

    function block(i, p, action) {
        const target = targetOf(p);
        const isOpen = alertBox.classList.contains('is-open') && !alertBox.classList.contains('is-resolved');
        const again = isOpen && blocked && blocked.target === target;
        unmark();
        blocked = {
            part: i,
            target,
            message: problemMessage(p),
            marks: p.sig ? [sigBtn]
                : isGroup(p.el) ? [...sections[i].querySelectorAll(`input[name="${p.el.name}"]:not(:disabled)`)]
                : [p.el],
            button: current === sections.length - 1 ? submitBtn : nextBtn,     // the one on screen
        };
        blocked.marks.forEach(m => {
            m.classList.add('is-blocked');
            m.setAttribute('aria-invalid', 'true');
        });
        blocked.button.classList.add('is-locked');

        clearTimeout(alertTimer);
        alertBox.classList.remove('is-resolved');
        alertBox.classList.add('is-open');      // visible before its text changes, so screen readers announce it
        alertTitle.textContent = action === 'submit' ? 'Complete this to submit' : 'Complete this to continue';
        setMessage(p);
        if (again) {                            // tried again without fixing it: shake the panel
            alertBox.classList.remove('is-nudged');
            void alertBox.offsetWidth;
            alertBox.classList.add('is-nudged');
        }
        goToProblem();
    }

    // Runs on every change: the field holding up the step may be done now
    function checkBlocked() {
        if (!blocked) return;
        const p = findProblem(blocked.part);
        if (p && targetOf(p) === blocked.target) {
            const message = problemMessage(p);
            if (message !== blocked.message) {  // e.g. an LRN that has digits now, but not 12
                blocked.message = message;
                setMessage(p);
            }
            return;
        }

        const { part } = blocked;
        const wasOpen = alertBox.classList.contains('is-open');
        unmark();
        blocked = null;
        if (!wasOpen) return;
        alertBox.classList.add('is-resolved');
        alertTitle.textContent = p ? 'Done' : `Step ${part + 1} complete`;
        alertMessage.textContent = p ? 'Continue to check the rest of this step.'
            : part === sections.length - 1 ? 'You can submit now.' : 'You can continue now.';
        alertTimer = setTimeout(closeAlert, 2200);
    }

    document.getElementById('stepAlertShow').addEventListener('click', () => blocked && goToProblem());
    document.getElementById('stepAlertClose').addEventListener('click', closeAlert);
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && alertBox.classList.contains('is-open')) closeAlert();
    });

    // Checks one part; if it isn't finished, opens it and points at the problem
    function validatePart(i, action) {
        const p = findProblem(i);
        if (!p) return true;
        show(i);
        block(i, p, action);
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
        captionStep.textContent = `Step ${current + 1} of ${nodes.length}`;
        captionName.textContent = nodes[current].querySelector('.step-label').textContent;

        prevBtn.hidden = current === 0;
        nextBtn.hidden = current === sections.length - 1;
        submitBtn.hidden = current !== sections.length - 1;
        updateScrollFill();     // the part, or its height, may have changed
        checkBlocked();
    }

    // How far the part on screen has been scrolled through: 0 while its top is below the bar,
    // 1 once its end is in view
    function updateScrollFill() {
        const part = sections[current].getBoundingClientRect();
        const barBottom = wrap.getBoundingClientRect().bottom;
        const distance = part.height - (window.innerHeight - barBottom);
        const progress = distance > 0 ? (barBottom - part.top) / distance : 1;
        scrollFill.style.transform = `scaleX(${Math.min(Math.max(progress, 0), 1)})`;
    }

    let fillQueued = false;     // at most one update per frame while scrolling
    window.addEventListener('scroll', () => {
        if (fillQueued) return;
        fillQueued = true;
        requestAnimationFrame(() => {
            fillQueued = false;
            updateScrollFill();
        });
    }, { passive: true });
    window.addEventListener('resize', updateScrollFill);

    function show(i) { current = i; render(); }

    function goTo(target) {
        // Going forward: every part from here up to the target must be complete
        for (let i = current; i < target; i++) {
            if (!validatePart(i, 'continue')) return;
        }
        clearBlock();
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
            if (!validatePart(i, 'submit')) { e.preventDefault(); return; }
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

    // The bar docks once it has stuck to the top of the window.
    // This marker sits just above it and takes up no space, so it scrolls away at that moment.
    const stickyTop = parseFloat(getComputedStyle(wrap).top);
    const marker = document.createElement('div');
    marker.setAttribute('aria-hidden', 'true');
    wrap.before(marker);
    new IntersectionObserver(
        ([entry]) => wrap.classList.toggle('is-stuck', !entry.isIntersecting),
        { rootMargin: `-${stickyTop}px 0px 0px 0px` }
    ).observe(marker);
});