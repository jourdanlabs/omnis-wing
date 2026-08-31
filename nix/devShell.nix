# nix/devShell.nix — Dev shell that delegates setup to each package
#
# Each npm workspace package exposes passthru.packageJsonPath (e.g.
# "ui-tui/package.json").  This file collects them all and passes the
# list to mkNpmDevShellHook, which stamps all package.jsons at once,
# then runs a single `npm i --package-lock-only` if any changed and
# `npm ci` if the lockfile changed.
{ ... }:
{
  perSystem =
    { pkgs, self', ... }:
    let
      packages = builtins.attrValues self'.packages;
      wingNpmLib = self'.packages.default.passthru.wingNpmLib;

      # Collect all packageJsonPath values from npm workspace packages.
      npmPackageJsonPaths = builtins.filter (p: p != null) (
        map (p: p.passthru.packageJsonPath or null) packages
      );

      # Non-npm packages may have their own devShellHook (e.g. omnis-wing
      # stamps pyproject.toml + uv.lock for Python venv setup).
      nonNpmHooks = map (p: p.passthru.devShellHook or "") packages;
      combinedNonNpm = pkgs.lib.concatStringsSep "\n" (builtins.filter (h: h != "") nonNpmHooks);
    in
    {
      devShells.default = pkgs.mkShell {
        inputsFrom = packages;
        packages = with pkgs; [
          uv
        ];
        shellHook = ''
          echo "OMNIS WING dev shell"
          ${combinedNonNpm}
          ${wingNpmLib.mkNpmDevShellHook npmPackageJsonPaths}
          echo "Ready. Run 'wing' to start."
        '';
      };
    };
}
