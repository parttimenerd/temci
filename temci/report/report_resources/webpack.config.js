// Source: http://docs.mathjax.org/en/latest/web/webpack.html

const PACKAGE = require('mathjax-full/components/webpack.common.js');

module.exports = PACKAGE(
  'custom-mathjax',                     // the name of the package to build
  '../node_modules/mathjax-full/js',    // location of the mathjax library
  [],                                   // packages to link to
  __dirname,                            // our directory
  '.'                                   // where to put the packaged component
);
