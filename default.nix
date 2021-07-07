{ pkgs ? import (fetchTarball {
    # Commit hash from `git ls-remote https://github.com/NixOS/nixpkgs-channels nixpkgs-unstable`
    url = https://github.com/nixos/nixpkgs/archive/502845c3e31ef3de0e424f3fcb09217df2ce6df6.tar.gz;
    # Hash obtained using `nix-prefetch-url --unpack <url>`
    sha256 = "0fcqpsy6y7dgn0y0wgpa56gsg0b0p8avlpjrd79fp4mp9bl18nda";
  }) {},
  # ignore untracked files in local checkout
  src ? if builtins.pathExists ./.git then builtins.fetchGit { url = ./.; } else ./. }:
with pkgs.python37Packages;
let
  python = import ./requirements.nix { inherit pkgs; };
  pypi = python.packages;
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
