document.addEventListener('DOMContentLoaded', function () {

    // ====================================================
    // 10. SIGNATURE MODAL & CANVAS DRAWING LOGIC
    // ====================================================
    const openSigBtn = document.getElementById('open_sig_modal_btn');
    const sigModal = document.getElementById('sig_modal');
    const cancelSigBtn = document.getElementById('cancel_sig_btn');
    const clearSigBtn = document.getElementById('clear_sig_btn');
    const saveSigBtn = document.getElementById('save_sig_btn');
    const canvas = document.getElementById('sig_canvas');
    const sigInput = document.getElementById('signature_data');
    const sigPreview = document.getElementById('signature_preview');
    const dateInput = document.getElementById('date_signed');

    if (canvas && openSigBtn) {
        const ctx = canvas.getContext('2d');
        let isDrawing = false;

        function resetCanvasContext() {
            ctx.strokeStyle = '#000000';
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
        }

        openSigBtn.addEventListener('click', () => {
            sigModal.style.display = 'flex';
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            resetCanvasContext();
        });

        if (cancelSigBtn) {
            cancelSigBtn.addEventListener('click', () => sigModal.style.display = 'none');
        }

        if (clearSigBtn) {
            clearSigBtn.addEventListener('click', () => {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                resetCanvasContext();
            });
        }

        function getPos(e) {
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;

            return {
                x: (e.clientX - rect.left) * scaleX,
                y: (e.clientY - rect.top) * scaleY
            };
        }

        canvas.addEventListener('pointerdown', (e) => {
            isDrawing = true;
            canvas.setPointerCapture(e.pointerId);
            ctx.beginPath();
            const p = getPos(e);
            ctx.moveTo(p.x, p.y);
        });

        canvas.addEventListener('pointermove', (e) => {
            if (isDrawing) {
                const p = getPos(e);

                if (e.pointerType === 'pen' && e.pressure) {
                    ctx.lineWidth = Math.max(1, e.pressure * 5);
                }

                ctx.lineTo(p.x, p.y);
                ctx.stroke();
            }
        });

        canvas.addEventListener('pointerup', (e) => {
            isDrawing = false;
            canvas.releasePointerCapture(e.pointerId);
        });

        if (saveSigBtn) {
            saveSigBtn.addEventListener('click', () => {
                const dataUrl = canvas.toDataURL('image/png');
                if (sigInput) sigInput.value = dataUrl; // Store in hidden input for PHP submit

                if (sigPreview) {
                    sigPreview.innerHTML = `<img src="${dataUrl}" alt="Signature Preview" style="max-width:100%; height:auto;" />`;
                }
                openSigBtn.textContent = 'Change Signature';

                // Automatically capture the exact time the form was signed. A saved form keeps its original date.
                if (dateInput && !dateInput.hasAttribute('data-locked')) {
                    const now = new Date();
                    
                    // Format option 1: standard YYYY-MM-DD format (Best for database parsing)
                    const year = now.getFullYear();
                    const month = String(now.getMonth() + 1).padStart(2, '0');
                    const day = String(now.getDate()).padStart(2, '0');
                    dateInput.value = `${year}-${month}-${day}`;

                    /* 
                       Format option 2: Human readable format (e.g., September 6, 2026)
                       If you prefer readable text in the field, uncomment below:

                       dateInput.value = now.toLocaleDateString('en-US', {
                           year: 'numeric',
                           month: 'long',
                           day: 'numeric'
                       });
                    */
                }

                sigModal.style.display = 'none';
            });
        }
    }

});