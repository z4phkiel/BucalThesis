// this is where all script for grade is stored.


document.addEventListener('DOMContentLoaded', function () {
  const search = document.getElementById('studentSearch');
  if (!search) return;
  const rows = document.querySelectorAll('.student-row');
  const noResults = document.getElementById('noSearchResults');
  search.addEventListener('input', function () {
    const term = this.value.trim().toLowerCase();
    let count = 0;
    rows.forEach(function (row) {
      const name = row.querySelector('.student-name').textContent.toLowerCase();
      const lrn = row.querySelector('.student-lrn').textContent.toLowerCase();
      const match = name.includes(term) || lrn.includes(term);
      row.style.display = match ? '' : 'none';
      if (match) count++;
    });
    if (noResults) noResults.style.display = count === 0 && rows.length > 0 ? '' : 'none';
  });
});