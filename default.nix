{ pkgs ? import (fetchTarball {
    # Commit hash from `git ls-remote https://github.com/NixOS/nixpkgs-channels nixpkgs-unstable`
    url = https://github.com/nixos/nixpkgs/archive/3b4df94aeb6e215085d08e3d5b0edc1313b9f584.tar.gz;
    # Hash obtained using `nix-prefetch-url --unpack <url>`
    sha256 = "1z8fnqxi0zd3wmjnmc4l2s4nq812mx0h4r09zdqi5si2in6rksxs";
  }) {},
  # ignore untracked files in local checkout
  src ? if builtins.pathExists ./.git then builtins.fetchGit { url = ./.; } else ./. }:
with pkgs.python37Packages;
let
  python = import ./requirements.nix { inherit pkgs; };
  pypi = python.packages;
  click_git = click.overrideAttrs (attrs: {
    postPatch = "";
    src = builtins.fetchGit { url = https://github.com/pallets/click.git; rev = "f537a208591088499b388b06b2aca4efd5445119"; };
  });
in buildPythonApplication rec {
  name = "temci-${version}";
  version = "local";
  inherit src;
  checkInputs = [ pytest pytestrunner ];
  propagatedBuildInputs = [
    click_git
    humanfriendly
    fn
    pytimeparse
    pypi.cpuset-py3
    wcwidth
    pypi.rainbow-logging-handler
    tablib unicodecsv
    scipy seaborn
    pyyaml
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
