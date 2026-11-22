    document.addEventListener('DOMContentLoaded', function () {
        // Each picture loads separately from the database, so it shimmers until it arrives
        document.querySelectorAll('.picture-thumb img').forEach(function (img) {
            if (img.complete) {
                return;
            }
            const thumb = img.closest('.picture-thumb');
            const finish = function () {
                thumb.classList.remove('is-loading');
            };
            thumb.classList.add('is-loading');
            img.addEventListener('load', finish, { once: true });
            img.addEventListener('error', finish, { once: true });
        });

        // Search filters the links, files and pictures already on the page
        const sections = document.querySelectorAll('[data-search-section]');
        document.getElementById('linkageSearch').addEventListener('input', function () {
            const term = this.value.trim().toLowerCase();
            sections.forEach(function (section) {
                const items = section.querySelectorAll('.search-item');
                let count = 0;
                items.forEach(function (item) {
                    const match = item.dataset.search.toLowerCase().includes(term);
                    item.classList.toggle('d-none', !match);
                    if (match) count++;
                });
                section.querySelector('.search-empty').classList.toggle('d-none', items.length === 0 || count > 0);
            });
        });

        // Required fields are checked here, so the browser's own "Please fill out this field" bubbles never show
        // (the forms are novalidate). The message sits under the field, in brick; the server checks again.
        function errorFor(field) {
            let error = field.parentElement.querySelector('.invalid-feedback');
            if (!error) {
                error = document.createElement('div');
                error.className = 'invalid-feedback';
                error.id = 'error-' + Math.random().toString(36).slice(2);
                field.after(error);
            }
            return error;
        }

        function unmark(field) {
            if (!field.classList || !field.classList.contains('is-invalid')) return;
            field.classList.remove('is-invalid');
            field.removeAttribute('aria-invalid');
            field.removeAttribute('aria-describedby');
        }

        function unmarkAll(form) {
            form.querySelectorAll('.is-invalid').forEach(unmark);
        }

        document.querySelectorAll('form[novalidate]').forEach(function (form) {
            form.addEventListener('submit', function (event) {
                unmarkAll(form);
                const missing = Array.from(form.querySelectorAll('[required]')).filter(function (field) {
                    return field.type === 'file' ? !field.files.length : !field.value.trim();
                });
                if (!missing.length) return;

                event.preventDefault();
                missing.forEach(function (field) {
                    const error = errorFor(field);
                    error.textContent = field.dataset.required || 'Fill in this field.';
                    field.classList.add('is-invalid');
                    field.setAttribute('aria-invalid', 'true');
                    field.setAttribute('aria-describedby', error.id);
                });
                missing[0].focus();
            });
            // The message goes as soon as the field is filled in
            form.addEventListener('input', function (event) { unmark(event.target); });
            form.addEventListener('change', function (event) { unmark(event.target); });
        });

        // Fill the shared "Edit Link" popup with the row that was clicked
        const linkModal = document.getElementById('editLinkModal');
        linkModal.addEventListener('show.bs.modal', function (event) {
            const btn = event.relatedTarget;
            unmarkAll(linkModal);
            linkModal.querySelector('form').action = btn.dataset.action;
            linkModal.querySelector('[name="title"]').value = btn.dataset.title;
            linkModal.querySelector('[name="url"]').value = btn.dataset.url;
        });

        // Same for the "Edit File" popup
        const fileModal = document.getElementById('editFileModal');
        fileModal.addEventListener('show.bs.modal', function (event) {
            const btn = event.relatedTarget;
            unmarkAll(fileModal);
            fileModal.querySelector('form').action = btn.dataset.action;
            fileModal.querySelector('[name="title"]').value = btn.dataset.title;
            fileModal.querySelector('[name="file"]').value = '';
            document.getElementById('editFileCurrent').textContent = btn.dataset.filename;
        });
    });