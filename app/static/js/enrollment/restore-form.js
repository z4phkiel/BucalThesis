document.addEventListener('DOMContentLoaded', function () {

    // ====================================================
    // 12. REFILL THE FORM AFTER THE SERVER REJECTS IT
    // ====================================================
    // Runs after form-init.js (dropdown options exist) and before conditional-fields.js
    // and address-sync.js, so those set up the Yes/No sections from the restored answers.
    const source = document.getElementById('enrollment_form_data');
    if (!source) return;

    const data = JSON.parse(source.textContent);

    Object.keys(data).forEach(name => {
        const values = data[name];

        document.querySelectorAll(`[name="${CSS.escape(name)}"]`).forEach(field => {
            if (field.type === 'radio' || field.type === 'checkbox') {
                field.checked = values.includes(field.value);
            } else {
                field.value = values[0];
            }
        });
    });

    // Age is worked out from the birthdate in form-init.js
    const birthdate = document.getElementById('birthdate');
    if (birthdate) birthdate.dispatchEvent(new Event('change'));

    // The signature only comes back if the server accepted it
    const signature = document.getElementById('signature_data');
    const preview = document.getElementById('signature_preview');
    const sigBtn = document.getElementById('open_sig_modal_btn');
    if (signature && signature.value && preview) {
        const img = document.createElement('img');
        img.src = signature.value;
        img.alt = 'Signature Preview';
        img.style.maxWidth = '100%';
        img.style.height = 'auto';
        preview.appendChild(img);
        if (sigBtn) sigBtn.textContent = 'Change Signature';
    }

});
