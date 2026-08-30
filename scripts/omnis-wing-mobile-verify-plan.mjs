#!/usr/bin/env node
/**
 * OMNIS WING Mobile V1 plan completion gate.
 * Writes docs/WING-MOBILE-V1-PLAN.json (OmnisSurfaceVerifyReceiptV1).
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SIBLING_PLAN = '/Users/sokpyeon/projects/omnis-code-ide/docs/WING-MOBILE-V1-PLAN.json';

function check(id, label, ok, note) {
	return { id, label, ok, note: note ?? null };
}

function fileIncludes(path, needle) {
	return existsSync(path) && readFileSync(path, 'utf8').includes(needle);
}

const items = [];

const tests = spawnSync(process.execPath, ['--test', 'tests/mobile-health.test.mjs'], {
	cwd: ROOT,
	encoding: 'utf8',
});
const testSummary = `${tests.stdout || ''}\n${tests.stderr || ''}`;
const pass = Number(testSummary.match(/ℹ pass (\d+)/)?.[1] ?? 0);
items.push(check('p0-mobile-tests', 'mobile-health.test.mjs exit 0', tests.status === 0, tests.status === 0 ? `${pass} pass` : 'see tests'));

items.push(check('p0-build-script', 'scripts/omnis-wing-build.mjs (parent WING)', existsSync(join(ROOT, 'scripts/omnis-wing-build.mjs'))));

items.push(check(
	'p1-health-parse',
	'health-parse.mjs — operator_cli JSON parser',
	existsSync(join(ROOT, 'mobile/health-parse.mjs'))
		&& fileIncludes(join(ROOT, 'mobile/health-parse.mjs'), 'parseHealthReport'),
));

const manifestPath = join(ROOT, 'mobile/manifest.webmanifest');
let manifestOk = false;
if (existsSync(manifestPath)) {
	try {
		const m = JSON.parse(readFileSync(manifestPath, 'utf8'));
		manifestOk = Boolean(m.name && m.display === 'standalone');
	} catch { /* no */ }
}
items.push(check('p1-pwa-manifest', 'PWA manifest (standalone)', manifestOk));

items.push(check(
	'p1-mobile-ui',
	'mobile/index.html — health paste + summary UI',
	fileIncludes(join(ROOT, 'mobile/index.html'), 'health-json')
		&& fileIncludes(join(ROOT, 'mobile/index.html'), 'viewport'),
));

items.push(check(
	'p2-offline-honest',
	'No fake live wire — paste-only health (honest gate)',
	!fileIncludes(join(ROOT, 'mobile/app.mjs'), 'fetch('),
));

items.push(check(
	'p2-operator-cli-doc',
	'Documents operator_cli health command',
	fileIncludes(join(ROOT, 'mobile/index.html'), 'operator_cli health'),
));

items.push(check('p3-parent-wing', 'Parent omnis_wing.operator_cli exists', existsSync(join(ROOT, 'omnis_wing/operator_cli.py'))));

items.push(check('p4-probe-script', 'scripts/omnis-wing-mobile-probe.mjs', existsSync(join(ROOT, 'scripts/omnis-wing-mobile-probe.mjs'))));

const probe = spawnSync(process.execPath, [join(ROOT, 'scripts/omnis-wing-mobile-probe.mjs')], { cwd: ROOT, encoding: 'utf8' });
items.push(check('p4-probe-exit-0', 'omnis-wing-mobile-probe exits 0', probe.status === 0));

items.push(check('p4-verify-plan', 'omnis-wing-mobile-verify-plan.mjs → WING-MOBILE-V1-PLAN.json', true));

const allOk = items.every((i) => i.ok);
const report = {
	ok: allOk,
	ts: new Date().toISOString(),
	schema: 'OmnisSurfaceVerifyReceiptV1',
	surface: 'WING-MOBILE',
	repo: ROOT,
	plan: 'WING Mobile V1 — offline health paste shell for Hermes transport',
	status: allOk ? 'complete' : 'in-progress',
	items,
	manual: [
		'Desktop: python -m omnis_wing.operator_cli health --ledger <path>',
		'Paste JSON into mobile shell — no live fetch (honest offline gate)',
		'Serve: python -m http.server 8877 --directory mobile',
	],
};

writeFileSync(join(ROOT, 'docs/WING-MOBILE-V1-PLAN.json'), `${JSON.stringify(report, null, 2)}\n`);
writeFileSync(SIBLING_PLAN, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
process.exit(allOk ? 0 : 1);
