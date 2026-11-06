document.addEventListener('DOMContentLoaded', function () {
    const toggleBtn = document.getElementById('toggleMetricBtn');
    const metricsCard = document.getElementById('metricsCard');
    const fab = document.getElementById('metricEditFab');

    // Pages that extend this template load this script too, but don't have the dashboard's controls
    if (!toggleBtn || !metricsCard || !fab) {
        return;
    }

    const TYPING_PAUSE_MS = 700;    // how long after the last keystroke the save prompt starts
    const LOADING_BAR_MS = 600;     // matches the metric-loading-fill animation in index.css
    const SAVED_NOTICE_MS = 1800;
    const PANEL_MS = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 300;   // matches .metrics-panel in index.css

    const fabLabel = document.getElementById('metricEditFabLabel');
    const loadingBar = document.getElementById('metricLoadingBar');
    const saveModal = document.getElementById('metricSaveModal');
    const saveSummary = document.getElementById('metricSaveSummary');
    const saveNote = document.getElementById('metricSaveNote');
    const saveError = document.getElementById('metricSaveError');
    const saveProgress = document.getElementById('metricSaveProgress');
    const discardBtn = document.getElementById('metricDiscardBtn');
    const saveBtn = document.getElementById('metricSaveBtn');
    const savedNotice = document.getElementById('metricSavedNotice');
    const forecastCard = document.getElementById('forecastCard');
    const metricsPanel = document.getElementById('metricsPanel');
    const metricsTable = document.getElementById('metricsTable');
    const forecastPlaceholder = forecastCard.innerHTML;
    const tablePlaceholder = metricsTable.innerHTML;

    let editableRows = [];      // filled in once the table has loaded
    let tableOpen = false;
    let panelTimer = null;
    let editing = false;
    let typingTimer = null;
    let loadingTimer = null;
    let savedTimer = null;
    let latestForecastRequest = 0;

    // The pencil belongs to the table, so it only shows while the table is open and has something to edit
    function updateFab() {
        fab.hidden = !(tableOpen && editableRows.length);
    }

    // The table drops down when opened and folds back up when closed
    function setTableOpen(open) {
        tableOpen = open;
        clearTimeout(panelTimer);
        toggleBtn.textContent = open ? 'Hide Yearly Metric' : 'Show Yearly Metric';
        metricsPanel.classList.remove('is-settled');

        if (open) {
            metricsCard.classList.remove('d-none');
            void metricsPanel.offsetHeight;     // starts the animation from the closed height
        }
        metricsPanel.classList.toggle('is-open', open);

        panelTimer = setTimeout(function () {
            metricsPanel.classList.toggle('is-settled', open);
            metricsCard.classList.toggle('d-none', !open);
        }, PANEL_MS);
        updateFab();
    }

    function rowInputs(row) {
        return Array.from(row.querySelectorAll('.metric-input'));
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

    // defaultValue holds the last value the server has, so it is what edits are compared with
    function inputChanged(input) {
        if (input.value === '' || input.defaultValue === '') {
            return input.value !== input.defaultValue;
        }
        return Number(input.value) !== Number(input.defaultValue);
    }

    function changedRows() {
        return editableRows.filter(function (row) {
            return rowInputs(row).some(inputChanged);
        });
    }

    function refreshChanges() {
        editableRows.forEach(function (row) {
            let rowChanged = false;
            rowInputs(row).forEach(function (input) {
                const changed = inputChanged(input);
                input.classList.toggle('is-changed', changed);
                rowChanged = rowChanged || changed;
            });
            row.classList.toggle('is-changed', rowChanged);
            if (!rowChanged) {
                row.classList.remove('has-error');
            }
        });

        const rows = changedRows();
        const years = rows.map(function (row) { return row.dataset.schoolYear; });
        saveSummary.textContent = `${years.length === 1 ? 'School year' : 'School years'} changed: ${years.join(', ')}`;
        saveNote.hidden = !rows.some(function (row) {
            return rowInputs(row).some(function (input) { return input.value === ''; });
        });
        return rows;
    }

    function clearError() {
        saveError.textContent = '';
        saveError.hidden = true;
    }

    function hidePrompt() {
        clearTimeout(typingTimer);
        clearTimeout(loadingTimer);
        typingTimer = null;
        loadingTimer = null;
        loadingBar.hidden = true;
        saveModal.hidden = true;
        clearError();
    }

    function showLoadingThenModal() {
        typingTimer = null;
        savedNotice.hidden = true;
        loadingBar.hidden = false;
        loadingTimer = setTimeout(function () {
            loadingTimer = null;
            loadingBar.hidden = true;
            saveModal.hidden = false;
        }, LOADING_BAR_MS);
    }

    function promptToSave(delay) {
        // Once the bar or the modal is showing, further edits only update the modal's text
        if (!saveModal.hidden || loadingTimer) {
            return;
        }
        clearTimeout(typingTimer);
        typingTimer = setTimeout(showLoadingThenModal, delay);
    }

    function setEditing(on) {
        editing = on;
        metricsCard.classList.toggle('is-editing', on);
        fab.classList.toggle('is-editing', on);
        fab.setAttribute('aria-pressed', String(on));
        fab.setAttribute('aria-label', on ? 'Finish editing yearly metrics' : 'Edit yearly metrics');
        fabLabel.textContent = on ? 'Done editing' : 'Edit metrics';
        editableRows.forEach(function (row) {
            setRowMode(row, on ? 'edit' : 'display');
        });
    }

    function setSaving(saving) {
        saveProgress.hidden = !saving;
        saveProgress.firstElementChild.style.width = '0%';
        saveBtn.textContent = saving ? 'Saving...' : 'Save changes';
        [saveBtn, discardBtn, fab].forEach(function (control) {
            control.disabled = saving;
        });
        editableRows.forEach(function (row) {
            rowInputs(row).forEach(function (input) {
                input.readOnly = saving;
            });
        });
    }

    // Resolves to null when the row saved, or to the message explaining why it didn't
    function saveRow(row) {
        const payload = {};
        rowInputs(row).forEach(function (input) {
            payload[input.dataset.field] = parseFloat(input.value) || 0;    // a blank field counts as 0
        });

        return fetch(row.dataset.updateUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify(payload)
        })
            .then(function (res) {
                return res.json().then(function (body) {
                    return { status: res.status, body: body };
                });
            })
            .then(function (result) {
                if (result.status === 200 && result.body.success) {
                    rowInputs(row).forEach(function (input) {
                        input.value = payload[input.dataset.field];
                        input.defaultValue = input.value;
                    });
                    return null;
                }
                console.error('Save failed:', result.status, result.body);
                return result.body.error || `Save failed (status ${result.status}).`;
            })
            .catch(function (err) {
                console.error('Network/parse error:', err);
                return 'Could not reach the server. Your changes are still here, so please try again.';
            });
    }

    function showForecastRefreshError() {
        if (forecastCard.querySelector('.forecast-refresh-note')) {
            return;
        }
        const note = document.createElement('p');
        note.className = 'forecast-refresh-note small mt-3 mb-0';
        note.textContent = 'Your changes were saved, but the forecast could not be updated. Reload the page to see the latest forecast.';
        forecastCard.querySelector('.card-body').appendChild(note);
    }

    // Resolves to the table and forecast from the server
    function requestDashboardData() {
        return fetch(forecastCard.dataset.url, { cache: 'no-store' })
            .then(function (res) {
                if (res.status === 401) {
                    // Logged out in the meantime: reloading goes to the login page, so this never resolves
                    window.location.reload();
                    return new Promise(function () {});
                }
                if (!res.ok) {
                    throw new Error(`status ${res.status}`);
                }
                return res.text();
            })
            .then(function (html) {
                const page = new DOMParser().parseFromString(html, 'text/html');
                const table = page.getElementById('metricsTable');
                const forecast = page.getElementById('forecastCard');
                if (!table || !forecast) {
                    throw new Error('the response has no dashboard data');
                }
                return { table: table, forecast: forecast };
            });
    }

    function showLoadError() {
        forecastCard.innerHTML = `<div class="card-body dashboard-load-error">
            <p class="mb-3">The forecast could not be loaded.</p>
            <button type="button" class="btn btn-primary btn-sm" data-retry-dashboard>Try again</button>
        </div>`;
        metricsTable.innerHTML = '<div class="dashboard-load-error p-4">The yearly metrics could not be loaded.</div>';
    }

    function loadDashboard() {
        forecastCard.innerHTML = forecastPlaceholder;
        metricsTable.innerHTML = tablePlaceholder;
        forecastCard.setAttribute('aria-busy', 'true');

        requestDashboardData()
            .then(function (data) {
                metricsTable.innerHTML = data.table.innerHTML;
                forecastCard.innerHTML = data.forecast.innerHTML;
                editableRows = Array.from(metricsTable.querySelectorAll('tr')).filter(function (row) {
                    return row.querySelector('.metric-input');
                });
                updateFab();
            })
            .catch(function (err) {
                console.error('Dashboard data failed to load:', err);
                showLoadError();
            })
            .finally(function () {
                forecastCard.removeAttribute('aria-busy');
            });
    }

    // If saves overlap, only the newest response is used, so an older forecast can't replace a newer one
    function refreshForecast() {
        const request = ++latestForecastRequest;
        forecastCard.classList.add('is-updating');
        forecastCard.setAttribute('aria-busy', 'true');

        requestDashboardData()
            .then(function (data) {
                if (request === latestForecastRequest) {
                    forecastCard.innerHTML = data.forecast.innerHTML;
                }
            })
            .catch(function (err) {
                console.error('Forecast refresh failed:', err);
                if (request === latestForecastRequest) {
                    showForecastRefreshError();
                }
            })
            .finally(function () {
                if (request === latestForecastRequest) {
                    forecastCard.classList.remove('is-updating');
                    forecastCard.removeAttribute('aria-busy');
                }
            });
    }

    async function saveChanges() {
        const rows = refreshChanges();
        if (!rows.length) {
            hidePrompt();
            return;
        }

        clearError();
        setSaving(true);

        const failures = [];
        for (let i = 0; i < rows.length; i++) {
            const error = await saveRow(rows[i]);
            rows[i].classList.toggle('has-error', Boolean(error));
            if (error) {
                failures.push(`${rows[i].dataset.schoolYear}: ${error}`);
            }
            saveProgress.firstElementChild.style.width = `${((i + 1) / rows.length) * 100}%`;
        }

        setSaving(false);
        refreshChanges();

        // Any year that saved can change the forecast, even if another year in this save was rejected
        if (failures.length < rows.length) {
            refreshForecast();
        }

        if (failures.length) {
            saveError.textContent = failures.join(' ');
            saveError.hidden = false;
            return;
        }

        hidePrompt();
        setEditing(false);
        savedNotice.hidden = false;
        clearTimeout(savedTimer);
        savedTimer = setTimeout(function () {
            savedNotice.hidden = true;
        }, SAVED_NOTICE_MS);
    }

    function discardChanges() {
        editableRows.forEach(function (row) {
            rowInputs(row).forEach(function (input) {
                input.value = input.defaultValue;
            });
        });
        refreshChanges();
        hidePrompt();
        setEditing(false);
    }

    function pulseModal() {
        saveModal.classList.remove('is-pulsing');
        void saveModal.offsetWidth;     // restarts the animation if it is already running
        saveModal.classList.add('is-pulsing');
    }

    toggleBtn.addEventListener('click', function () {
        setTableOpen(!tableOpen);
        if (tableOpen || !editing) {
            return;
        }

        // Closing the table ends editing, unless there are edits left to save or discard
        if (changedRows().length) {
            promptToSave(0);
        } else {
            hidePrompt();
            setEditing(false);
        }
    });

    fab.addEventListener('click', function () {
        if (!editing) {
            setEditing(true);
            rowInputs(editableRows[0])[0].focus();
            return;
        }

        // Unsaved edits are never dropped by leaving edit mode: they must be saved or discarded
        if (changedRows().length) {
            promptToSave(0);
            pulseModal();
            return;
        }
        hidePrompt();
        setEditing(false);
    });

    metricsCard.addEventListener('input', function (event) {
        if (!event.target.matches('.metric-input')) {
            return;
        }
        event.target.closest('tr').classList.remove('has-error');
        if (refreshChanges().length) {
            promptToSave(TYPING_PAUSE_MS);
        } else {
            hidePrompt();
        }
    });

    // Leaving a field or pressing Enter means the edit is finished, so there's no need to wait
    metricsCard.addEventListener('change', function (event) {
        if (event.target.matches('.metric-input') && changedRows().length) {
            promptToSave(0);
        }
    });

    metricsCard.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && event.target.matches('.metric-input') && changedRows().length) {
            event.preventDefault();
            promptToSave(0);
        }
    });

    saveBtn.addEventListener('click', saveChanges);
    discardBtn.addEventListener('click', discardChanges);

    forecastCard.addEventListener('click', function (event) {
        if (event.target.matches('[data-retry-dashboard]')) {
            loadDashboard();
        }
    });

    window.addEventListener('beforeunload', function (event) {
        if (changedRows().length) {
            event.preventDefault();
            event.returnValue = '';
        }
    });

    loadDashboard();
});
