// Fills the shared "Delete permanently?" popup with the row whose button was clicked
document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('deleteForeverModal');
    modal.addEventListener('show.bs.modal', function (event) {
        const button = event.relatedTarget;
        modal.querySelector('form').action = button.dataset.action;
        document.getElementById('deleteForeverName').textContent = button.dataset.name;
    });
});
