{
  description = " An advanced benchmarking tool";

  inputs.nixpkgs.url = github:NixOS/nixpkgs/nixpkgs-unstable;
  inputs.flake-utils.url = github:numtide/flake-utils;

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in
      with pkgs.python3Packages; let
        python = import ./requirements.nix {inherit pkgs;};
        pypi = python.packages;
      in {
        packages.default = buildPythonApplication rec {
          name = "temci-${version}";
          version = "local";
          src = ./.;
          checkInputs = [pytest pytestrunner];
          propagatedBuildInputs =
            [
              click
              humanfriendly
              fn
              pytimeparse
              pypi.cpuset-py3
              wcwidth
              pypi.rainbow-logging-handler
              tablib
              unicodecsv
              scipy
              seaborn
              pyyaml
              psutil
            ]
            ++ pkgs.lib.optional pkgs.stdenv.isLinux pkgs.linuxPackages.perf;
          postInstall = ''
            $out/bin/temci setup
          '';
          postPatch = ''
            substituteInPlace temci/run/cpuset.py --replace python3 ${pkgs.python3.withPackages (ps: [pypi.cpuset-py3])}/bin/python3
            substituteInPlace temci/run/run_driver.py \
              --replace /usr/bin/time ${pkgs.time}/bin/time \
              --replace gtime ${pkgs.time}/bin/time
          '';
          makeWrapperArgs = ["--prefix PATH ':' ${pkgs.git}/bin"];
          preCheck = ''export PATH=$PATH:$out/bin'';
        };
      });
}
