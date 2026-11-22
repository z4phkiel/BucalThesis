document.addEventListener('DOMContentLoaded', function () {
    
    // ----------------------------------------------------
    // 1. Populate "Last School Year Completed" Dropdown
    //    (the School Year box is filled by the server, which turns the year over on June 1)
    // ----------------------------------------------------
    const lastSchoolYearSelect = document.getElementById('last_school_year_completed');
    if (lastSchoolYearSelect) {
        // The newest completed school year ends in the year the current one began, as the server checks
        const maxEndYear = Number(lastSchoolYearSelect.dataset.maxEndYear);
        const minStartYear = 2001;

        lastSchoolYearSelect.innerHTML = '<option value="" disabled selected>Select School Year</option>';

        for (let endYear = maxEndYear; endYear > minStartYear; endYear--) {
            const startYear = endYear - 1;
            const schoolYearText = `${startYear}-${endYear}`;

            const option = document.createElement('option');
            option.value = schoolYearText;
            option.textContent = schoolYearText;

            lastSchoolYearSelect.appendChild(option);
        }
    }

    // ----------------------------------------------------
    // 1.2 Auto-fill Date Answered (YYYY-MM-DD)
    // ----------------------------------------------------
    const dateAnsweredInput = document.getElementById('date_answered');
    if (dateAnsweredInput) {
        const today = new Date();
        // Formats to YYYY-MM-DD
        dateAnsweredInput.value = today.toISOString().split('T')[0];
    }

    // ----------------------------------------------------
    // 2. Auto-compute Age from Birthdate
    // ----------------------------------------------------
    const birthdateInput = document.getElementById('birthdate');
    const ageInput = document.getElementById('age');

    function calculateAge() {
        if (!birthdateInput || !ageInput || !birthdateInput.value) return;

        const [y, m, d] = birthdateInput.value.split('-').map(Number);
        const birthDate = new Date(y, m - 1, d);

        if (!isNaN(birthDate.getTime())) {
            // A saved form shows the age on the day it was signed, the same as the server works out
            const today = ageInput.dataset.asOf ? new Date(`${ageInput.dataset.asOf}T00:00:00`) : new Date();
            let age = today.getFullYear() - birthDate.getFullYear();
            const monthDiff = today.getMonth() - birthDate.getMonth();

            if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
                age--;
            }

            ageInput.value = age >= 0 ? age : 0;
        } else {
            ageInput.value = '';
        }
    }

    if (birthdateInput) {
        birthdateInput.addEventListener('change', calculateAge);
        birthdateInput.addEventListener('input', calculateAge);

        calculateAge();
    }

});