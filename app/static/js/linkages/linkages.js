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

        // Fill the shared "Edit Link" popup with the row that was clicked
        const linkModal = document.getElementById('editLinkModal');
        linkModal.addEventListener('show.bs.modal', function (event) {
            const btn = event.relatedTarget;
            linkModal.querySelector('form').action = btn.dataset.action;
            linkModal.querySelector('[name="title"]').value = btn.dataset.title;
            linkModal.querySelector('[name="url"]').value = btn.dataset.url;
        });

        // Same for the "Edit File" popup
        const fileModal = document.getElementById('editFileModal');
        fileModal.addEventListener('show.bs.modal', function (event) {
            const btn = event.relatedTarget;
            fileModal.querySelector('form').action = btn.dataset.action;
            fileModal.querySelector('[name="title"]').value = btn.dataset.title;
            fileModal.querySelector('[name="file"]').value = '';
            document.getElementById('editFileCurrent').textContent = btn.dataset.filename;
        });
    });