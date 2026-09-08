/**
 * Renders the chart specifications that ChartSpecBuilder (dao/lib/da_chartjs.py)
 * produces. One specification can hold several graphs; every graph gets its own
 * canvas inside the given container.
 */

import {Chart} from 'chart.js'

/**
 * Centres a y-axis on zero, the way the matplotlib GraphBuilder does. The
 * specification switches this on for every axis of a graph at once as soon as
 * any of them goes negative, so an axis that only holds positive values is
 * centred along with the others and both zero lines end up at the same height.
 */
const alignZeroPlugin = {
    id: 'daoAlignZero',
    afterDataLimits(chart, args) {
        const scale = args.scale

        if (!scale.options.daoAlignZero) {
            return
        }

        const limit = Math.max(Math.abs(scale.min), Math.abs(scale.max))
        scale.min = -limit
        scale.max = limit
    },
}

function buildScales(graph, haxisTitle) {
    const scales = {
        x: {
            stacked: graph.axes.some(axis => axis.stacked),
            title: {
                display: Boolean(haxisTitle),
                text: haxisTitle || '',
            },
            ticks: {
                autoSkip: true,
                maxRotation: 45,
            },
        },
    }

    graph.axes.forEach(axis => {
        scales[axis.id] = {
            position: axis.position,
            stacked: axis.stacked,
            beginAtZero: axis.begin_at_zero,
            daoAlignZero: axis.align_zero,
            title: {
                display: Boolean(axis.title),
                text: axis.title || '',
            },
            grid: {
                // Only the first axis draws grid lines, otherwise the two grids
                // would overlap in a confusing way.
                drawOnChartArea: axis.position === 'left',
            },
        }
    })

    return scales
}

function formatValue(value, unit) {
    if (value === null || value === undefined) {
        return ''
    }

    const formatted = value.toLocaleString('nl-NL', {
        maximumFractionDigits: 3,
    })

    return unit ? `${formatted} ${unit}` : formatted
}

function tooltipLabel(context) {
    const dataset = context.dataset
    const label = dataset.label || ''

    // A waterfall bar is drawn as a range; show the step itself, not the range.
    const value = dataset.waterfall
        ? dataset.amounts[context.dataIndex]
        : context.parsed.y

    return `${label}: ${formatValue(value, dataset.unit)}`
}

function buildConfig(graph, spec) {
    return {
        type: 'bar',
        data: {
            labels: graph.labels,
            datasets: graph.datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            scales: buildScales(graph, spec.haxis_title),
            plugins: {
                title: {
                    display: Boolean(spec.title),
                    text: spec.title || '',
                },
                tooltip: {
                    callbacks: {
                        label: tooltipLabel,
                    },
                },
                legend: {
                    position: 'top',
                },
            },
        },
        plugins: [alignZeroPlugin],
    }
}

/**
 * @param {HTMLElement} container element the canvases are appended to
 * @param {object} spec specification as built by ChartSpecBuilder
 * @returns {Chart[]} the created charts
 */
export function renderChartSpec(container, spec) {
    container.innerHTML = ''

    if (!spec || !spec.graphs || spec.graphs.length === 0) {
        return []
    }

    return spec.graphs.map(graph => {
        const wrapper = document.createElement('div')
        wrapper.className = 'dao-chart'
        container.appendChild(wrapper)

        const canvas = document.createElement('canvas')
        wrapper.appendChild(canvas)

        return new Chart(canvas, buildConfig(graph, spec))
    })
}
