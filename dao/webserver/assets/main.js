// Bootstrap
import * as bootstrap from 'bootstrap'
import 'bootstrap-icons/font/bootstrap-icons.css'

// HTMX
import htmx from 'htmx.org'

window.htmx = htmx

if (document.getElementById('data-chart')) {
    import('./charts.js')
}

if (document.querySelector('code-input')) {
    import('./code-editor.js')
    import('./code-editor.scss')
}


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

document.querySelectorAll('.tom-select').forEach((el) => {
    let settings = {plugins: ['change_listener'],};
    new TomSelect(el, settings);
});


// Eigen styling als laatste
import './main.scss'

window.toDatetimeLocalValue = (date, withTime = true) => {
    const pad = n => String(n).padStart(2, '0');

    return [
        date.getFullYear(),
        pad(date.getMonth() + 1),
        pad(date.getDate()),
    ].join('-') + (withTime ? 'T' + [
        pad(date.getHours()),
        pad(date.getMinutes()),
    ].join(':') : '');
}