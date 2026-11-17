// A student's grade files: checks a chosen or dropped file before it is uploaded, and asks (in the shared
// confirmation toast, confirm-toast.js) before a stored file is replaced. Delete asks through its form's data-confirm-toast.
document.addEventListener('DOMContentLoaded', function () {
    const MAX_BYTES = 10 * 1024 * 1024;     // MAX_FILE_SIZE in routes.py

    function showError(level, message) {
        const error = level.querySelector('.sg-error');
        error.textContent = message;
        error.hidden = !message;
    }

    function setBusy(level, text) {
        level.querySelector('.sg-busy-text').textContent = text;
        level.classList.add('is-busy');
    }

    // Checked here too, so a wrong or oversized file is caught before it is sent
    function sendFile(input) {
        const file = input.files[0];
        const level = input.closest('.sg-level');
        if (!file) {
            return;
        }

        let problem = '';
        if (!/\.xlsx$/i.test(file.name)) {
            problem = 'Only Excel (.xlsx) files can be uploaded.';
        } else if (file.size === 0) {
            problem = 'The selected file is empty.';
        } else if (file.size > MAX_BYTES) {
            problem = 'The file must be 10 MB or smaller.';
        }
        showError(level, problem);
        if (problem) {
            input.value = '';
            return;
        }

        function upload() {
            setBusy(level, 'Uploading ' + file.name + '...');
            input.form.submit();
        }

        const replacing = input.dataset.replace;
        if (!replacing) {
            upload();
            return;
        }
        // Replacing overwrites the stored file (it does not go to the Archives), so the toast says so
        confirmToast.ask({
            title: 'Replace “' + replacing + '” with “' + file.name + '”?',
            note: 'The current file is replaced for good. It does not go to the Archives.',
            yes: 'Replace file',
            busy: 'Uploading...',
            icon: 'replace',
            opener: input,
            onYes: function () {
                upload();
                return Promise.resolve();   // the toast closes; the level's own "Uploading..." cover takes over
            },
            onCancel: function () {
                input.value = '';
            },
        });
    }

    function hasFiles(event) {
        return event.dataTransfer.types.includes('Files');
    }

    document.querySelectorAll('.sg-level').forEach(function (level) {
        const input = level.querySelector('.sg-file-input');
        if (!input) {   // a role that only views grades gets no upload field
            return;
        }
        input.addEventListener('change', function () {
            sendFile(input);
        });

        // A file dropped on a level goes to that level's upload or replace
        let depth = 0;      // dragenter and dragleave also fire for each child the pointer crosses
        level.addEventListener('dragenter', function (event) {
            if (hasFiles(event) && !level.classList.contains('is-busy')) {
                depth += 1;
                level.classList.add('is-dragover');
            }
        });
        level.addEventListener('dragleave', function () {
            depth = Math.max(0, depth - 1);
            if (!depth) {
                level.classList.remove('is-dragover');
            }
        });
        level.addEventListener('dragover', function (event) {
            if (hasFiles(event)) {
                event.preventDefault();
                event.dataTransfer.dropEffect = 'copy';
            }
        });
        level.addEventListener('drop', function (event) {
            event.preventDefault();
            depth = 0;
            level.classList.remove('is-dragover');
            if (level.classList.contains('is-busy') || !event.dataTransfer.files.length) {
                return;
            }
            const picked = new DataTransfer();
            picked.items.add(event.dataTransfer.files[0]);
            input.files = picked.files;
            sendFile(input);
        });
    });

    // A file dropped beside the levels would otherwise open in the browser and leave this page
    window.addEventListener('dragover', function (event) {
        if (!event.target.closest('.sg-level')) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'none';
        }
    });
    window.addEventListener('drop', function (event) {
        event.preventDefault();
    });

    // The Back button can bring this page back exactly as it was left, still showing "Uploading..."
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            document.querySelectorAll('.sg-level.is-busy').forEach(function (level) {
                level.classList.remove('is-busy');
            });
        }
    });
});
