{ pkgs ? import (fetchTarball {
    # Commit hash from `git ls-remote https://github.com/NixOS/nixpkgs nixpkgs-unstable`
    url = https://github.com/nixos/nixpkgs/archive/3e0ce8c5d478d06b37a4faa7a4cc8642c6bb97de.tar.gz;
    # Hash obtained using `nix-prefetch-url --unpack <url>`
    sha256 = "16l1576d5km2847z4hmc6kr03qzwmi1w45njj9y7my666xkwwqrz";
  }) {},
  # ignore untracked files in local checkout
  src ? if builtins.pathExists ./.git then builtins.fetchGit { url = ./.; } else ./. }:
with pkgs.python37Packages;
let
  python = import ./requirements.nix { inherit pkgs; };
  pypi = python.packages;
  click_git = click.overrideAttrs (attrs: {
    postPatch = "";
    src = builtins.fetchGit { url = https://github.com/pallets/click.git; rev = "baea6233ea2f5b6c40f40edde6e297e25e3d2b94"; };
  });
in buildPythonApplication rec {
  name = "temci-${version}";
  version = "local";
  inherit src;
  checkInputs = [ pytest pytestrunner ];
  propagatedBuildInputs = [
    click
    humanfriendly
    fn
    pytimeparse
    pypi.cpuset-py3
    wcwidth
    pypi.rainbow-logging-handler
    tablib unicodecsv
    scipy seaborn
    pyyaml
    psutil
  ] ++ pkgs.lib.optional pkgs.stdenv.isLinux pkgs.linuxPackages.perf;
  postInstall = ''
    $out/bin/temci setup
  '';
  postPatch = ''
    substituteInPlace temci/run/cpuset.py --replace python3 ${pkgs.python37.withPackages (ps: [ pypi.cpuset-py3 ])}/bin/python3
    substituteInPlace temci/run/run_driver.py \
      --replace /usr/bin/time ${pkgs.time}/bin/time \
      --replace gtime ${pkgs.time}/bin/time
  '';
  makeWrapperArgs = ["--prefix PATH ':' ${pkgs.git}/bin"];
  preCheck = ''export PATH=$PATH:$out/bin'';
}
