import { parseHealthReport, summarizeHealth } from './health-parse.mjs';

const els = {
  json: document.getElementById('health-json'),
  parse: document.getElementById('btn-parse'),
  status: document.getElementById('status'),
  summary: document.getElementById('summary'),
};

function renderSummary(summary) {
  els.summary.innerHTML = '';
  for (const [label, value] of summarizeHealth(summary)) {
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value;
    els.summary.appendChild(dt);
    els.summary.appendChild(dd);
  }
}

els.parse.addEventListener('click', () => {
  try {
    const summary = parseHealthReport(els.json.value.trim());
    renderSummary(summary);
    els.status.textContent = summary.ready ? 'WING reports ready' : 'WING not ready — check desktop';
    els.status.className = `status ${summary.ready ? 'ok' : 'warn'}`;
  } catch (error) {
    els.status.textContent = `Parse error: ${error.message}`;
    els.status.className = 'status warn';
  }
});
