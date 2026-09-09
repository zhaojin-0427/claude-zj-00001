import { defineComponent, h, PropType } from 'vue'
import { Bar, Line, Doughnut } from 'vue-chartjs'
import {
  Chart as ChartJS,
  Title, Tooltip, Legend,
  BarElement, LineElement, PointElement,
  CategoryScale, LinearScale, ArcElement,
} from 'chart.js'

ChartJS.register(
  Title, Tooltip, Legend,
  BarElement, LineElement, PointElement,
  CategoryScale, LinearScale, ArcElement,
)

function makeProps(kind: string) {
  return {
    chartData: { type: Object as PropType<any>, required: true },
    options: {
      type: Object as PropType<any>,
      default: () => ({ responsive: true, maintainAspectRatio: false }),
    },
  }
}

export const BarChart = defineComponent({
  name: 'BarChart',
  props: makeProps('bar'),
  setup(props) {
    return () => h(Bar, { data: props.chartData, options: props.options })
  },
})

export const LineChart = defineComponent({
  name: 'LineChart',
  props: makeProps('line'),
  setup(props) {
    return () => h(Line, { data: props.chartData, options: props.options })
  },
})

export const DoughnutChart = defineComponent({
  name: 'DoughnutChart',
  props: makeProps('doughnut'),
  setup(props) {
    return () => h(Doughnut, { data: props.chartData, options: props.options })
  },
})
