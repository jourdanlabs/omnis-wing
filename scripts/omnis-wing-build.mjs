#!/usr/bin/env node
/**
 * Full OMNIS WING ship build: v0 tests → Path A cutover dry-run → plan verify.
 */
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

function run(cmd, args, label, cwd = ROOT) {
	console.error(`\n== ${label} ==`);
	const r = spawnSync(cmd, args, { cwd, stdio: 'inherit', env: process.env, shell: false });
	if (r.status !== 0) {
		process.exit(r.status ?? 1);
	}
}

run('./scripts/run_omnis_wing_v0_tests.sh', [], 'v0-tests');
run('./scripts/omnis_wing_cutover_dry_run.sh', [], 'cutover-dry-run');
const verifyEnv = {
	...process.env,
	OMNIS_WING_SKIP_VERIFY_DRY_RUN: '1',
	OMNIS_WING_SKIP_VERIFY_V0: '1',
	OMNIS_WING_V0_TEST_COUNT: '196',
};
console.error('\n== verify-plan ==');
const verify = spawnSync(process.execPath, [join(ROOT, 'scripts/omnis-wing-verify-plan.mjs')], {
	cwd: ROOT,
	stdio: 'inherit',
	env: verifyEnv,
});
if (verify.status !== 0) {
	process.exit(verify.status ?? 1);
}
console.error('\n✓ omnis-wing-build complete — see docs/WING-V1-PLAN.json');
