// Bootstrap
import * as bootstrap from 'bootstrap'
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

    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
});

document.body.addEventListener("htmx:responseError", function (event) {
    const errorElement = document.getElementById("htmx-error");
    const messageElement = document.getElementById("htmx-error-message");

    const response = event.detail.xhr.responseText;
    const status = event.detail.xhr.status;

    messageElement.textContent =
        response || `Er is een fout opgetreden (${status}).`;

    errorElement.classList.remove("d-none");
});

document.body.addEventListener("htmx:sendError", function () {
    const errorElement = document.getElementById("htmx-error");
    const messageElement = document.getElementById("htmx-error-message");

    messageElement.textContent =
        "De server kon niet worden bereikt.";

    errorElement.classList.remove("d-none");
});

import TomSelect from "tom-select";
import "tom-select/dist/css/tom-select.bootstrap5.css";

document.querySelectorAll('.tom-select').forEach((el)=>{
	let settings = {};
 	new TomSelect(el,settings);
});


// Eigen styling als laatste
import './main.scss'
