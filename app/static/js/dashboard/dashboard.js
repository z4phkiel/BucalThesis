document.addEventListener('DOMContentLoaded', function () {
            const toggleBtn = document.getElementById('toggleMetricBtn');
            const metricsCard = document.getElementById('metricsCard');


            if (toggleBtn && metricsCard ) {
                toggleBtn.addEventListener('click', function () {
                // Toggle the 'd-none' Bootstrap class to show/hide
                metricsCard.classList.toggle('d-none');

                // Optionally update button text based on state
                if (metricsCard.classList.contains('d-none')) {
                    toggleBtn.textContent = 'Show Yearly Metric';
                } else {
                    toggleBtn.textContent = 'Hide Yearly Metric';
                }
            });
            }
            

            function setRowMode(row, mode) {
                // mode is either 'edit' or 'display'
                row.querySelectorAll('.metric-edit-group').forEach(function (group) {
                    group.classList.toggle('d-none', mode === 'display');
                });
                row.querySelectorAll('.metric-display').forEach(function (span) {
                    span.classList.toggle('d-none', mode === 'edit');
                    if (mode === 'display') {
                        const field = span.dataset.field;
                        const input = row.querySelector(`.metric-input[data-field="${field}"]`);
                        const isPercent = field !== 'enrollee_count';
                        span.textContent = input.value === '' ? '—' : (input.value + (isPercent ? '%' : ''));
                    }
                });
            }

            document.querySelectorAll('.save-row-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    const row = btn.closest('tr');

                    
                    if (btn.dataset.mode === 'edit') {
                        setRowMode(row, 'edit');
                        btn.textContent = 'Save';
                        btn.dataset.mode = 'save';
                        btn.classList.remove('btn-outline-success');
                        btn.classList.add('btn-success');
                        return;
                    }

                    const updateUrl = row.dataset.updateUrl;
                    const payload = {};
                    row.querySelectorAll('.metric-input').forEach(function (input) {
                        payload[input.dataset.field] = parseFloat(input.value) || 0;
                    });

                    btn.disabled = true;
                    btn.textContent = 'Saving...';

                    fetch(updateUrl, {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                         },
                        
                        body: JSON.stringify(payload)
                    })
                        .then(res => res.json().then(data => ({ status: res.status, body: data })))
                        .then(({ status, body }) => {
                            btn.disabled = false;
                            if (status === 200 && body.success) {
                                setRowMode(row, 'display');
                                btn.textContent = 'Edit';
                                btn.dataset.mode = 'edit';
                                btn.classList.remove('btn-success');
                                btn.classList.add('btn-outline-success');
                            } else {
                                console.error('Save failed:', status, body);
                                alert(body.error || `Save failed (status ${status}).`);
                                btn.textContent = 'Save';
                            }
                        })
                        .catch(err => {
                            console.error('Network/parse error:', err);
                            alert('Something went wrong while saving — check the browser console for details.');
                            btn.disabled = false;
                            btn.textContent = 'Save';
                        });
                });
            });

        });