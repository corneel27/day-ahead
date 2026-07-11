// Bootstrap
import 'bootstrap'
import 'bootstrap-icons/font/bootstrap-icons.css'

// HTMX
import htmx from 'htmx.org'
window.htmx = htmx

// Chart.js
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

import Prism from 'prismjs'
import 'prismjs/components/prism-json'

import 'prismjs/themes/prism.css'
import 'prismjs/plugins/line-numbers/prism-line-numbers'
import 'prismjs/plugins/line-numbers/prism-line-numbers.css'

import {
  registerTemplate,
  Template,
} from '@webcoder49/code-input/code-input.mjs'

import Indent from '@webcoder49/code-input/plugins/indent.mjs'
import FindAndReplace from '@webcoder49/code-input/plugins/find-and-replace.mjs'

import '@webcoder49/code-input/code-input.css'
import '@webcoder49/code-input/plugins/prism-line-numbers.css'
import '@webcoder49/code-input/plugins/find-and-replace.css'

registerTemplate(
  'syntax-highlighted',
  new Template(
    (codeElement) => {
      Prism.highlightElement(codeElement)
    },
    true,  // preElementStyled
    true,  // isCode; zorgt voor language-* class
    false, // includeCodeInputInHighlightFunc
    [
      new Indent(true, 4, true),
      new FindAndReplace()
    ]
  )
)

function fillCurrentTimezoneFields(root = document) {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  root
    .querySelectorAll('input[data-current-tz], select[data-current-tz], textarea[data-current-tz]')
    .forEach((field) => {
      field.value = timezone;
    });
}

document.addEventListener('DOMContentLoaded', () => {
  fillCurrentTimezoneFields();
});

// Eigen styling als laatste
import './main.scss'
