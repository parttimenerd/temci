#! /bin/sh
sphinx-apidoc -o doc -F -H "temci" -A "Johannes Bechberger" -V 0.1 temci -d 100
cd doc; make html
