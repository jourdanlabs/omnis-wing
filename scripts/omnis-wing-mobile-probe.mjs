#!/usr/bin/env node
/**
 * Post-build smoke probe for OMNIS WING Mobile.
 */
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const failures = [];
const notes = [];

const required = [
	'mobile/index.html',
	'mobile/manifest.webmanifest',
	'mobile/styles.css',
	'mobile/app.mjs',
	'mobile/health-parse.mjs',
];

for (const rel of required) {
	if (!existsSync(join(ROOT, rel))) failures.push(`missing ${rel}`);
}

const html = readFileSync(join(ROOT, 'mobile/index.html'), 'utf8');
if (!html.includes('viewport') || !html.includes('health-json')) {
	failures.push('mobile index missing viewport or health paste UI');
}

const tests = spawnSync(process.execPath, ['--test', 'tests/mobile-health.test.mjs'], {
	cwd: ROOT,
	encoding: 'utf8',
});
if (tests.status !== 0) failures.push('mobile-health tests failed');

const report = {
	ok: failures.length === 0,
	ts: new Date().toISOString(),
	schema: 'OmnisWingMobileProbeV1',
	surface: 'WING-MOBILE',
	repo: ROOT,
	failures,
	notes,
};
console.log(JSON.stringify(report, null, 2));
process.exit(failures.length === 0 ? 0 : 1);
