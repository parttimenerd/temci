#! /bin/sh
# Generates the documentation for temci

SPHINXDOC=True sphinx-apidoc -o doc -F -H "temci" -A "Johannes Bechberger" -V `temci version` temci -d 100
cd doc; make html; rm README_.rst
