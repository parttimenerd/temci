{ pkgs ? import <nixpkgs> {} }:
with pkgs.python3Packages;
let
  python = import ./requirements.nix { inherit pkgs; };
  pypi = python.packages;
in buildPythonApplication rec {
  name = "temci-${version}";
  version = "local";
  src = ./.;
  MINIMAL_TEMCI = 1;
  propagatedBuildInputs = [
    click
    pypi.humanfriendly
    fn
    pytimeparse
    pypi.cpuset-py3
    wcwidth
    pypi.rainbow-logging-handler
    tablib unicodecsv
    scipy seaborn
    pyyaml
  ];
  doCheck = false;
}
