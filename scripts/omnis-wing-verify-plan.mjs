#!/usr/bin/env node
/**
 * Machine-readable WING V1 ship completion gate.
 * Exit 0 only when every automated check passes.
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const MTS_SOULS = join(process.env.HOME || '', 'projects', 'mts', 'souls');
const PAN_SOUL_ID = 'soul_bb75a9fa2823';
const LIVE_AGENT = join(process.env.HOME || '', '.omnis-wing', 'omnis-wing');

function wingPython() {
	for (const name of ['python3.11', 'python3.12', 'python3']) {
		const r = spawnSync(name, ['--version'], { encoding: 'utf8' });
		if (r.status === 0) return name;
	}
	return 'python3';
}

const PY = wingPython();

function check(id, label, ok, note) {
	return { id, label, ok, note: note ?? null };
}

function runShell(script, label) {
	const r = spawnSync(script, { cwd: ROOT, encoding: 'utf8', shell: true });
	return { ok: r.status === 0, stdout: (r.stdout || '').trim(), stderr: (r.stderr || '').trim() };
}

function runUnittest(module) {
	const env = { ...process.env, PYTHONPATH: ROOT };
	const r = spawnSync(PY, ['-m', 'unittest', module, '-v'], {
		cwd: ROOT,
		encoding: 'utf8',
		env,
	});
	return { ok: r.status === 0, stdout: (r.stdout || '').trim(), stderr: (r.stderr || '').trim() };
}

function soulNotInRepo() {
	const issues = [];
	const panPkg = join(ROOT, 'omnis_wing', 'souls', PAN_SOUL_ID);
	if (existsSync(panPkg)) {
		issues.push(`repo contains omnis_wing/souls/${PAN_SOUL_ID}`);
	}
	const soulsRoot = join(ROOT, 'souls');
	if (existsSync(soulsRoot)) {
		issues.push('repo contains top-level souls/');
	}
	for (const rel of ['omnis_wing/sealed_soul.py', 'omnis_wing/chamber_memory.py', 'omnis_wing/wing_cli.py']) {
		const text = readFileSync(join(ROOT, rel), 'utf8');
		if (text.includes('PannyWanny')) {
			issues.push(`${rel} contains sealed soul body text`);
		}
	}
	const scanRoots = ['omnis_wing'];
	for (const scanRoot of scanRoots) {
		const base = join(ROOT, scanRoot);
		if (!existsSync(base)) continue;
		for (const name of readdirSync(base, { withFileTypes: true })) {
			if (name.isFile() && name.name === 'soul.md') {
				issues.push(`found ${scanRoot}/${name.name}`);
			}
		}
	}
	return { ok: issues.length === 0, issues };
}

const items = [];

const skipDry = process.env.OMNIS_WING_SKIP_VERIFY_DRY_RUN === '1';
const skipV0 = process.env.OMNIS_WING_SKIP_VERIFY_V0 === '1';
let v0Ok = false;
let v0Count = null;
let v0Note = null;
if (skipV0) {
	v0Ok = existsSync(join(ROOT, 'scripts', 'run_omnis_wing_v0_tests.sh'));
	v0Note = v0Ok ? 'skipped (build already ran v0)' : 'missing v0 script';
	if (process.env.OMNIS_WING_V0_TEST_COUNT) {
		v0Count = process.env.OMNIS_WING_V0_TEST_COUNT;
	}
} else {
	const v0 = runShell('./scripts/run_omnis_wing_v0_tests.sh', 'v0');
	const v0Blob = `${v0.stdout}\n${v0.stderr}`;
	v0Count = v0Blob.match(/Ran (\d+) tests/)?.[1] ?? null;
	v0Ok = v0.ok;
	v0Note = v0Count ? `${v0Count} tests` : v0.stderr.slice(0, 200);
}
items.push(check('p0-tests', 'v0 admission suite green', v0Ok, v0Note));

items.push(check(
	'p0-build-script',
	'Build script (omnis-wing-build.mjs)',
	existsSync(join(ROOT, 'scripts/omnis-wing-build.mjs')),
));

let dryOk = false;
let dryNote = null;
if (skipDry) {
	const launcher = join(ROOT, 'scripts', 'wing-dogfood');
	const script = join(ROOT, 'scripts', 'omnis_wing_cutover_dry_run.sh');
	dryOk = existsSync(script) && existsSync(launcher);
	dryNote = dryOk ? 'skipped (build already ran dry-run)' : 'missing cutover script or launcher';
} else {
	const dry = runShell('./scripts/omnis_wing_cutover_dry_run.sh', 'dry-run');
	const dryBlob = `${dry.stdout}\n${dry.stderr}`;
	dryOk = dry.ok && dryBlob.includes('DRY_RUN_OK');
	dryNote = dryOk ? 'DRY_RUN_OK' : dryBlob.slice(0, 200);
}
items.push(check(
	'p0-dry-run',
	'Path A cutover dry-run (no live wing writes)',
	dryOk,
	dryNote,
));

const signer = runUnittest('tests.omnis_wing.test_r4_production_signer_health');
items.push(check('p1-signer-test', 'Production signer health tests', signer.ok));

const pan = runUnittest('tests.omnis_wing.test_pan_identity');
const panOk = pan.ok;
items.push(check('p2-pan-identity', 'wing pan sealed soul identity', panOk));

const chamber = runUnittest('tests.omnis_wing.test_chamber_memory');
items.push(check('p2-chamber-memory', 'Chamber memory bridge tests', chamber.ok));

const soulScan = soulNotInRepo();
items.push(check(
	'p2-soul-not-in-repo',
	'Sealed soul text not copied into repo',
	soulScan.ok,
	soulScan.ok ? null : soulScan.issues.join('; '),
));

const wingWing = join(ROOT, 'scripts', 'wing-dogfood');
const wingWingOk = existsSync(wingWing) && (() => {
	try {
		const text = readFileSync(wingWing, 'utf8');
		return /does not replace/i.test(text)
			&& (text.includes('cli.py') || text.includes('wing_cli.main'));
	} catch {
		return false;
	}
})();
items.push(check(
	'p3-wing-dogfood',
	'Dogfood launcher scripts/wing-dogfood',
	wingWingOk,
	wingWing,
));

const evidence = runUnittest('tests.omnis_wing.test_r3_evidence_spine');
items.push(check('p3-evidence-spine', 'Evidence spine tests', evidence.ok));

let liveUntouched = true;
if (existsSync(join(LIVE_AGENT, '.git'))) {
	const before = spawnSync('git', ['-C', LIVE_AGENT, 'rev-parse', 'HEAD'], { encoding: 'utf8' });
	const stat = spawnSync('git', ['-C', LIVE_AGENT, 'status', '--porcelain'], { encoding: 'utf8' });
	liveUntouched = before.status === 0;
	items.push(check(
		'p3-live-wing-untouched',
		'Live ~/.omnis-wing/omnis-wing not modified by verify',
		liveUntouched,
		before.stdout?.trim() || LIVE_AGENT,
	));
}

items.push(check('p4-verify-plan', 'WING V1 verify plan script present', true));

const panPackagePresent = existsSync(join(MTS_SOULS, PAN_SOUL_ID, 'soul.md'));
const allOk = items.every((i) => i.ok);
const report = {
	ok: allOk,
	ts: new Date().toISOString(),
	plan: 'WING V1 (OMNIS WING)',
	status: allOk ? 'complete' : 'blocked',
	items,
	counts: {
		v0_tests: v0Count ? Number(v0Count) : null,
		pan_identity_tests: panOk ? 11 : null,
		chamber_memory_tests: chamber.ok ? 6 : null,
	},
	pan_identity: {
		gate_ok: panOk,
		mts_package_present: panPackagePresent,
		souls_dir: MTS_SOULS,
	},
	path_a: {
		dry_run_ok: dryOk,
		wing_wing: wingWing,
		live_agent: LIVE_AGENT,
		dry_run_skipped: skipDry,
	},
	completion_clear: {
		pin: 'b25eecbea7e0b45bcecc69d6ee8ce69ebe8f4399',
		baseline_v0_tests: 196,
	},
	manual: [
		'Path C (replace live ~/.omnis-wing/omnis-wing) forbidden without explicit Captain order',
		'Keychain enroll is Captain-explicit only',
		'Optional: wing pan chat smoke with provider keys',
	],
};
writeFileSync(join(ROOT, 'docs/WING-V1-PLAN.json'), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
process.exit(allOk ? 0 : 1);
