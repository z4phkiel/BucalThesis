    document.addEventListener('DOMContentLoaded', function () {
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