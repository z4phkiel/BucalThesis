// The three-dots row menus on Linkage/Files, Archives and Accounts (the .row-actions buttons).
// A popup opened from a menu item gives focus back to that row's dots when it closes: Bootstrap only refocuses
// an opener that is still visible, and the menu has closed by then.
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.modal').forEach(function (modal) {
        let dots = null;
        modal.addEventListener('show.bs.modal', function (event) {
            const menu = event.relatedTarget && event.relatedTarget.closest('.dropdown');
            dots = menu && menu.querySelector('.row-actions');
        });
        modal.addEventListener('hidden.bs.modal', function () {
            if (dots) {
                dots.focus();
            }
        });
    });
});
