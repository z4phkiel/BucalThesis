document.addEventListener('DOMContentLoaded', function () {
    // Status messages float over the page, so good news closes itself.
    // Errors and warnings stay until they are closed, so they can't be missed.
    const AUTO_CLOSE_MS = 5000;

    document.querySelectorAll('.flash-stack .alert-success, .flash-stack .alert-info').forEach(function (message) {
        setTimeout(function () {
            bootstrap.Alert.getOrCreateInstance(message).close();
        }, AUTO_CLOSE_MS);
    });
});
