    document.addEventListener('DOMContentLoaded', function () {
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