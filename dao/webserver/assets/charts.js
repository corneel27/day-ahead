import {
    Chart,
    LineController,
    BarController,
    PieController,
    DoughnutController,
    LineElement,
    BarElement,
    ArcElement,
    PointElement,
    LinearScale,
    CategoryScale,
    Tooltip,
    Legend
} from 'chart.js'

Chart.register(
    LineController,
    BarController,
    PieController,
    DoughnutController,
    LineElement,
    BarElement,
    ArcElement,
    PointElement,
    LinearScale,
    CategoryScale,
    Tooltip,
    Legend
)

window.Chart = Chart