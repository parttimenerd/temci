# generated using pypi2nix tool (version: 2.0.0)
# See more at: https://github.com/garbas/pypi2nix
#
# COMMAND:
#   pypi2nix -V python37 -e 'https://github.com/parttimenerd/cpuset/archive/master.tar.gz#egg=cpuset-py3' -e rainbow-logging-handler==2.2.2
#

{ pkgs ? import <nixpkgs> {},
  overrides ? ({ pkgs, python }: self: super: {})
}:

let

  inherit (pkgs) makeWrapper;
  inherit (pkgs.stdenv.lib) fix' extends inNixShell;

  pythonPackages =
  import "${toString pkgs.path}/pkgs/top-level/python-packages.nix" {
    inherit pkgs;
    inherit (pkgs) stdenv;
    python = pkgs.python37;
  };

  commonBuildInputs = [];
  commonDoCheck = false;

  withPackages = pkgs':
    let
      pkgs = builtins.removeAttrs pkgs' ["__unfix__"];
      interpreterWithPackages = selectPkgsFn: pythonPackages.buildPythonPackage {
        name = "python3-interpreter";
        buildInputs = [ makeWrapper ] ++ (selectPkgsFn pkgs);
        buildCommand = ''
          mkdir -p $out/bin
          ln -s ${pythonPackages.python.interpreter} \
              $out/bin/${pythonPackages.python.executable}
          for dep in ${builtins.concatStringsSep " "
              (selectPkgsFn pkgs)}; do
            if [ -d "$dep/bin" ]; then
              for prog in "$dep/bin/"*; do
                if [ -x "$prog" ] && [ -f "$prog" ]; then
                  ln -s $prog $out/bin/`basename $prog`
                fi
              done
            fi
          done
          for prog in "$out/bin/"*; do
            wrapProgram "$prog" --prefix PYTHONPATH : "$PYTHONPATH"
          done
          pushd $out/bin
          ln -s ${pythonPackages.python.executable} python
          ln -s ${pythonPackages.python.executable} \
              python3
          popd
        '';
        passthru.interpreter = pythonPackages.python;
      };

      interpreter = interpreterWithPackages builtins.attrValues;
    in {
      __old = pythonPackages;
      inherit interpreter;
      inherit interpreterWithPackages;
      mkDerivation = args: pythonPackages.buildPythonPackage (args // {
        nativeBuildInputs = (args.nativeBuildInputs or []) ++ args.buildInputs;
      });
      packages = pkgs;
      overrideDerivation = drv: f:
        pythonPackages.buildPythonPackage (
          drv.drvAttrs // f drv.drvAttrs // { meta = drv.meta; }
        );
      withPackages = pkgs'':
        withPackages (pkgs // pkgs'');
    };

  python = withPackages {};

  generated = self: {
    "colorama" = python.mkDerivation {
      name = "colorama-0.4.1";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/76/53/e785891dce0e2f2b9f4b4ff5bc6062a53332ed28833c7afede841f46a5db/colorama-0.4.1.tar.gz";
        sha256 = "05eed71e2e327246ad6b38c540c4a3117230b19679b875190486ddd2d721422d";
};
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/tartley/colorama";
        license = licenses.bsdOriginal;
        description = "Cross-platform colored terminal text.";
      };
    };

    "cpuset-py3" = python.mkDerivation {
      name = "cpuset-py3-1.0";
      src = pkgs.fetchurl {
        url = "https://github.com/parttimenerd/cpuset/archive/master.tar.gz";
        sha256 = "1d05ry7iyjqarmm6gdzkv3l2q3blwrav0kdbwvvrs2c86m9v0gkz";
};
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/parttimenerd/cpuset";
        license = "UNKNOWN";
        description = "Fork of cpuset (https://github.com/lpechacek/cpuset) by Alex Tsariounov that works with python3";
      };
    };

    "logutils" = python.mkDerivation {
      name = "logutils-0.3.5";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/49/b2/b57450889bf73da26027f8b995fd5fbfab258ec24ef967e4c1892f7cb121/logutils-0.3.5.tar.gz";
        sha256 = "bc058a25d5c209461f134e1f03cab637d66a7a5ccc12e593db56fbb279899a82";
};
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://code.google.com/p/logutils/";
        license = "Copyright (C) 2010-2017 by Vinay Sajip. All Rights Reserved. See LICENSE.txt for license.";
        description = "Logging utilities";
      };
    };

    "rainbow-logging-handler" = python.mkDerivation {
      name = "rainbow-logging-handler-2.2.2";
      src = pkgs.fetchurl {
        url = "https://files.pythonhosted.org/packages/3d/15/aa3cd5c46c709b2bc45e3f8612b6484bbc869d43f92dfc4a86b65e6a240a/rainbow_logging_handler-2.2.2.zip";
        sha256 = "a504c20f1e074cc7f5a5b986c08eb6fb495c9153cffb36b5fa0a587de3a8db63";
};
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs ++ [ ];
      propagatedBuildInputs = [
        self."colorama"
        self."logutils"
      ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/laysakura/rainbow_logging_handler";
        license = "LICENSE.txt";
        description = "Ultimate Python colorized logger with user-custom color";
      };
    };
  };
  localOverridesFile = ./requirements_override.nix;
  localOverrides = import localOverridesFile { inherit pkgs python; };
  commonOverrides = [
    
  ];
  paramOverrides = [
    (overrides { inherit pkgs python; })
  ];
  allOverrides =
    (if (builtins.pathExists localOverridesFile)
     then [localOverrides] else [] ) ++ commonOverrides ++ paramOverrides;

in python.withPackages
   (fix' (pkgs.lib.fold
            extends
            generated
            allOverrides
         )
   )
