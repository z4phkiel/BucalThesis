// Draws the predicted vs actual chart and keeps the chart, summary tiles and table on the selected year
document.addEventListener('DOMContentLoaded', function () {
    const chart = document.getElementById('statChart');
    if (!chart) {
        return;
    }

    const MARGIN = { top: 26, right: 24, bottom: 30, left: 52 };
    const AXIS_LABEL_WIDTH = 58;    // pixels one school year label needs along the x-axis
    const BAND_MAX_WIDTH = 64;
    const BAND_OVERHANG = 10;       // how far the selected year's band rises above the plot
    const MIN_GAP_FOR_LABEL = 30;   // pixels between the two dots before the difference fits beside them
    const SVG_NS = 'http://www.w3.org/2000/svg';

    const years = JSON.parse(document.getElementById('statisticsData').textContent);
    const hasData = function (item) { return item.actual !== null || item.predicted !== null; };
    const selectable = years.flatMap(function (item, i) { return hasData(item) ? [i] : []; });
    const forecastIndex = years.findIndex(function (item) { return item.is_forecast; });

    const tooltip = document.getElementById('statTooltip');
    const yearSelect = document.getElementById('statYear');
    const prevBtn = document.getElementById('statPrev');
    const nextBtn = document.getElementById('statNext');
    const tableBody = document.querySelector('#statTable tbody');
    const yearHead = document.getElementById('statYearHead');
    const sortBtn = document.getElementById('statSort');

    const scale = niceScale(years.flatMap(function (item) {
        return [item.actual, item.predicted].filter(function (value) { return value !== null; });
    }));

    let selected = defaultYear();
    let view = null;    // what the latest draw needs: positions, layers and the axis labels

    function defaultYear() {
        // The latest year that has both values, since that is a real comparison
        const compared = selectable.filter(function (i) { return years[i].difference !== null; });
        return compared.length ? compared[compared.length - 1] : selectable[selectable.length - 1];
    }

    // Clean axis numbers. A label below a dot would hit the x-axis, so the bottom gets more room than the top
    function niceScale(values) {
        const min = Math.min.apply(null, values);
        const max = Math.max.apply(null, values);
        const rough = (max - min || Math.max(max, 10)) / 4;
        const power = Math.pow(10, Math.floor(Math.log10(rough)));
        const step = [1, 2, 2.5, 5, 10].find(function (m) { return m * power >= rough; }) * power;
        let low = Math.floor((min - step / 2) / step) * step;
        if (min >= 0 && low < 0) {
            low = 0;
        }
        const high = Math.ceil((max + step / 4) / step) * step;
        const ticks = [];
        for (let tick = low; tick <= high + step / 2; tick += step) {
            ticks.push(tick);
        }
        return { low: low, high: high, ticks: ticks };
    }

    function number(value) {
        return value.toLocaleString('en-US');
    }

    function signed(value) {
        return (value > 0 ? '+' : '') + number(value);
    }

    function shortYear(year) {
        const parts = year.split('-');
        return `${parts[0]}-${parts[1].slice(-2)}`;
    }

    function add(parent, tag, attributes, text) {
        const element = document.createElementNS(SVG_NS, tag);
        Object.keys(attributes).forEach(function (name) {
            element.setAttribute(name, attributes[name]);
        });
        if (text !== undefined) {
            element.textContent = text;
        }
        parent.appendChild(element);
        return element;
    }

    // One path per unbroken run of values, so a missing year shows as a gap instead of a false line
    function linePath(key, x, y) {
        let path = '';
        let drawing = false;
        years.forEach(function (item, i) {
            if (item[key] === null) {
                drawing = false;
                return;
            }
            path += `${drawing ? 'L' : 'M'}${x(i)} ${y(item[key])} `;
            drawing = true;
        });
        return path;
    }

    function draw() {
        const width = chart.clientWidth;
        const height = chart.clientHeight;
        const plotWidth = width - MARGIN.left - MARGIN.right;
        const plotHeight = height - MARGIN.top - MARGIN.bottom;
        const slot = plotWidth / years.length;
        const x = function (i) { return MARGIN.left + slot * (i + 0.5); };
        const y = function (value) {
            return MARGIN.top + plotHeight * (1 - (value - scale.low) / (scale.high - scale.low));
        };

        if (view) {
            view.svg.remove();
        }
        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('class', 'stat-svg');
        svg.setAttribute('width', width);
        svg.setAttribute('height', height);
        svg.setAttribute('aria-hidden', 'true');
        chart.prepend(svg);

        const bandWidth = Math.min(slot, BAND_MAX_WIDTH);
        const band = add(svg, 'rect', {
            class: 'stat-band', x: 0, y: MARGIN.top - BAND_OVERHANG, rx: 10,
            width: bandWidth, height: plotHeight + BAND_OVERHANG,
        });

        scale.ticks.forEach(function (tick) {
            add(svg, 'line', { class: 'stat-grid', x1: MARGIN.left, x2: width - MARGIN.right, y1: y(tick), y2: y(tick) });
            add(svg, 'text', { class: 'stat-tick', x: MARGIN.left - 10, y: y(tick) + 4, 'text-anchor': 'end' }, number(tick));
        });

        const labelEvery = Math.max(1, Math.ceil(AXIS_LABEL_WIDTH / slot));
        const axisLabels = years.map(function (item, i) {
            return add(svg, 'text', {
                class: 'stat-tick', x: x(i), y: height - MARGIN.bottom + 20, 'text-anchor': 'middle',
            }, shortYear(item.year));
        });

        const crosshair = add(svg, 'line', {
            class: 'stat-crosshair', y1: MARGIN.top - BAND_OVERHANG, y2: height - MARGIN.bottom, visibility: 'hidden',
        });

        add(svg, 'path', { class: 'stat-line stat-line-actual', d: linePath('actual', x, y) });
        add(svg, 'path', { class: 'stat-line stat-line-predicted', d: linePath('predicted', x, y) });

        years.forEach(function (item, i) {
            if (item.predicted !== null) {
                add(svg, 'circle', { class: 'stat-dot stat-dot-predicted', cx: x(i), cy: y(item.predicted), r: 4 });
            }
            if (item.actual !== null) {
                add(svg, 'circle', { class: 'stat-dot stat-dot-actual', cx: x(i), cy: y(item.actual), r: 4 });
            }
        });

        const overlay = add(svg, 'g', {});

        view = {
            svg: svg, width: width, height: height, slot: slot, x: x, y: y, band: band, bandWidth: bandWidth,
            overlay: overlay, crosshair: crosshair, axisLabels: axisLabels, labelEvery: labelEvery,
        };
        drawSelection();
    }

    function pointLabel(cx, cy, text, above) {
        return add(view.overlay, 'text', {
            class: 'stat-point-label', x: cx, y: above ? cy - 12 : cy + 21, 'text-anchor': 'middle',
        }, text);
    }

    function boxesOverlap(a, b) {
        return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
    }

    // A label near the edge of the chart slides inward, so it isn't cut off and stays clear of the y-axis numbers
    function keepInside(label) {
        const box = label.getBBox();
        const shift = Math.max(MARGIN.left - box.x, 0) + Math.min(view.width - 2 - (box.x + box.width), 0);
        if (shift) {
            label.setAttribute('x', Number(label.getAttribute('x')) + shift);
        }
    }

    function drawSelection() {
        const item = years[selected];
        const cx = view.x(selected);
        const overlay = view.overlay;
        overlay.replaceChildren();

        view.band.style.transform = `translateX(${cx - view.bandWidth / 2}px)`;

        // Every few years gets an axis label, and the selected year always does
        view.axisLabels.forEach(function (label, i) {
            const onSchedule = (years.length - 1 - i) % view.labelEvery === 0;
            const tooClose = i !== selected && Math.abs(i - selected) < view.labelEvery;
            label.style.display = i === selected || (onSchedule && !tooClose) ? '' : 'none';
            label.classList.toggle('stat-tick-selected', i === selected);
        });

        const labels = [];
        if (item.difference !== null) {
            const yPredicted = view.y(item.predicted);
            const yActual = view.y(item.actual);
            add(overlay, 'line', { class: 'stat-gap', x1: cx, x2: cx, y1: yPredicted, y2: yActual });
            if (Math.abs(yPredicted - yActual) >= MIN_GAP_FOR_LABEL) {
                labels.push(add(overlay, 'text', {
                    class: 'stat-gap-label', x: cx + 10, y: (yPredicted + yActual) / 2 + 4,
                }, signed(item.difference)));
            }
        }

        if (item.predicted !== null) {
            const cy = view.y(item.predicted);
            add(overlay, 'circle', { class: 'stat-dot stat-dot-predicted', cx: cx, cy: cy, r: 6 });
            const above = item.actual === null || item.predicted >= item.actual;
            const name = item.is_forecast ? 'Forecast' : 'Predicted';
            labels.push(pointLabel(cx, cy, `${name} ${number(item.predicted)}`, above));
        }
        if (item.actual !== null) {
            const cy = view.y(item.actual);
            add(overlay, 'circle', { class: 'stat-dot stat-dot-actual', cx: cx, cy: cy, r: 6 });
            const above = item.predicted === null || item.actual > item.predicted;
            labels.push(pointLabel(cx, cy, `Actual ${number(item.actual)}`, above));
        }
        labels.forEach(keepInside);

        // The forecast is worth naming even when another year is selected, as long as it has room
        if (forecastIndex !== -1 && forecastIndex !== selected) {
            const forecast = years[forecastIndex];
            const label = pointLabel(view.x(forecastIndex), view.y(forecast.predicted), `Forecast ${number(forecast.predicted)}`, true);
            keepInside(label);
            const box = label.getBBox();
            if (labels.some(function (other) { return boxesOverlap(box, other.getBBox()); })) {
                label.remove();
            }
        }
    }

    function showTooltip(i, left, top) {
        const item = years[i];
        tooltip.replaceChildren();

        const title = document.createElement('div');
        title.className = 'stat-tooltip-title';
        title.textContent = `S.Y. ${item.year}`;
        tooltip.appendChild(title);

        function row(value, name, lineClass) {
            const line = document.createElement('div');
            line.className = lineClass ? 'stat-tooltip-row' : 'stat-tooltip-row stat-tooltip-row-plain';
            if (lineClass) {
                const key = document.createElementNS(SVG_NS, 'svg');
                key.setAttribute('class', 'stat-key');
                key.setAttribute('viewBox', '0 0 22 10');
                add(key, 'line', { class: `stat-line ${lineClass}`, x1: 0, y1: 5, x2: 22, y2: 5 });
                line.appendChild(key);
            }
            const strong = document.createElement('strong');
            strong.textContent = value;
            const label = document.createElement('span');
            label.textContent = name;
            line.append(strong, label);
            tooltip.appendChild(line);
        }

        row(item.predicted === null ? '—' : number(item.predicted), item.is_forecast ? 'Forecast' : 'Predicted', 'stat-line-predicted');
        row(item.actual === null ? '—' : number(item.actual), 'Actual', 'stat-line-actual');
        if (item.difference !== null) {
            row(signed(item.difference), `difference, ${item.percent_off}% off`);
        }

        tooltip.hidden = false;
        const flip = left + 16 + tooltip.offsetWidth > view.width;
        tooltip.style.left = `${flip ? left - 16 - tooltip.offsetWidth : left + 16}px`;
        tooltip.style.top = `${Math.max(0, Math.min(top - tooltip.offsetHeight / 2, view.height - tooltip.offsetHeight))}px`;
    }

    function indexAtPointer(event) {
        const left = event.clientX - view.svg.getBoundingClientRect().left;
        const i = Math.floor((left - MARGIN.left) / view.slot);
        return Math.max(0, Math.min(years.length - 1, i));
    }

    function hideHover() {
        tooltip.hidden = true;
        view.crosshair.setAttribute('visibility', 'hidden');
    }

    chart.addEventListener('pointermove', function (event) {
        const i = indexAtPointer(event);
        if (!hasData(years[i])) {
            hideHover();
            return;
        }
        view.crosshair.setAttribute('x1', view.x(i));
        view.crosshair.setAttribute('x2', view.x(i));
        view.crosshair.setAttribute('visibility', 'visible');
        showTooltip(i, view.x(i), event.clientY - view.svg.getBoundingClientRect().top);
    });

    chart.addEventListener('pointerleave', hideHover);

    chart.addEventListener('click', function (event) {
        const i = indexAtPointer(event);
        if (hasData(years[i])) {
            select(i);
        }
    });

    chart.addEventListener('keydown', function (event) {
        const position = selectable.indexOf(selected);
        const targets = {
            ArrowLeft: position - 1,
            ArrowRight: position + 1,
            Home: 0,
            End: selectable.length - 1,
        };
        if (!(event.key in targets)) {
            return;
        }
        event.preventDefault();
        const target = selectable[targets[event.key]];
        if (target !== undefined) {
            select(target);
        }
    });

    function updateTiles(item) {
        document.getElementById('statFocusYear').textContent = `Difference, S.Y. ${item.year}`;
        document.getElementById('statPredicted').textContent = item.predicted === null ? '—' : number(item.predicted);
        document.getElementById('statActual').textContent = item.actual === null ? 'Pending' : number(item.actual);
        document.getElementById('statDifference').textContent = item.difference === null ? '—' : signed(item.difference);

        let predictedNote = 'Too few earlier years to predict this one';
        if (item.is_forecast) {
            predictedNote = `Current forecast, expect roughly ${number(item.range[0])} to ${number(item.range[1])}`;
        } else if (item.predicted !== null) {
            predictedNote = `Trained on ${item.trained_on} earlier years`;
        }
        document.getElementById('statPredictedNote').textContent = predictedNote;
        document.getElementById('statActualNote').textContent = item.actual === null ? 'Not yet submitted' : 'Submitted count';

        let differenceNote = 'Needs both a predicted and an actual value';
        if (item.difference === 0) {
            differenceNote = 'The prediction matched the actual count';
        } else if (item.difference !== null) {
            differenceNote = `Predicted too ${item.difference > 0 ? 'high' : 'low'}, ${item.percent_off}% off`;
        }
        document.getElementById('statDifferenceNote').textContent = differenceNote;
    }

    function select(i) {
        selected = i;
        const item = years[i];
        const position = selectable.indexOf(i);

        yearSelect.value = item.year;
        prevBtn.disabled = position === 0;
        nextBtn.disabled = position === selectable.length - 1;

        chart.setAttribute('aria-valuemin', 0);
        chart.setAttribute('aria-valuemax', selectable.length - 1);
        chart.setAttribute('aria-valuenow', position);
        chart.setAttribute('aria-valuetext', `School year ${item.year}`);

        Array.from(tableBody.rows).forEach(function (row) {
            const isSelected = row.dataset.year === item.year;
            row.classList.toggle('is-selected', isSelected);
            if (isSelected) {
                row.setAttribute('aria-current', 'true');
            } else {
                row.removeAttribute('aria-current');
            }
        });

        updateTiles(item);
        drawSelection();
    }

    yearSelect.addEventListener('change', function () {
        select(years.findIndex(function (item) { return item.year === yearSelect.value; }));
    });

    prevBtn.addEventListener('click', function () {
        select(selectable[selectable.indexOf(selected) - 1]);
    });

    nextBtn.addEventListener('click', function () {
        select(selectable[selectable.indexOf(selected) + 1]);
    });

    tableBody.addEventListener('click', function (event) {
        const row = event.target.closest('tr[data-year]');
        if (row) {
            select(years.findIndex(function (item) { return item.year === row.dataset.year; }));
            chart.scrollIntoView({ block: 'center' });
        }
    });

    sortBtn.addEventListener('click', function () {
        const newestFirst = yearHead.getAttribute('aria-sort') === 'descending';
        tableBody.append.apply(tableBody, Array.from(tableBody.rows).reverse());
        yearHead.setAttribute('aria-sort', newestFirst ? 'ascending' : 'descending');
        sortBtn.textContent = newestFirst ? 'Oldest first' : 'Newest first';
    });

    // The size is 0 while the loading placeholder hides this page on the way to another one
    new ResizeObserver(function () {
        const resized = chart.clientWidth !== view.width || chart.clientHeight !== view.height;
        if (chart.clientWidth && resized) {
            draw();
        }
    }).observe(chart);

    draw();
    select(selected);
});
