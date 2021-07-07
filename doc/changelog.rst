Changelog
=========

0.8.3
-----
- add `--watch`: prints console report continuously
- improve progressbar
- `perf` runner works on NixOS
- use new click version (temci is installable via pip click again)

0.8.2
-----
- improve HTML2 reporter
  - fix typos
  - change "error" into "severe warning"
  - support disabling warnings alltogether
  - clean up duplicates
  - further improve the summary section
  - support zoomed out graphs (make this the default)
  - use local copy of all JS and CSS (no works offline)
- record some information on the execution environment
- don't build kernel modules by default
- remove meta analysis code

0.8.1
-----
- fixed minor issues
- add new runner capabilities like output parsing or rusage

0.8.0
-----
- removed the randomization features from the builder
- removed the html reporter (use the html2 reporter instead)
