#! /bin/sh

# Downloads all JS and CSS files
# requires npm to be installed

set -e
target_dir=$(dirname $(readlink -f $0))
cd $target_dir

# build mathjax

collect_dir="$target_dir/tmp"
custom_folder="$collect_dir/custom-mathjax"
mkdir -p $collect_dir
mkdir -p $custom_folder
cp webpack.config.js $custom_folder
cp custom-mathjax.js $custom_folder
cd $collect_dir

npm install mathjax-full@3
npm uninstall webpack --save-dev || echo 1
npm install webpack --save-dev
npm install webpack-cli
npm install uglifyjs-webpack-plugin
npm install @babel/core
npm install @babel/preset-env
npm install babel-core
npm install babel-preset-env
npm install babel-loader

cd $custom_folder
npm install @babel/core                            
npm install @babel/preset-env
../node_modules/mathjax-full/components/bin/makeAll
echo "/*************************************************************
 *
 *  Copyright (c) 2017 The MathJax Consortium
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an \"AS IS\" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */" > $target_dir/js/custom-mathjax.min.js
cat custom-mathjax.min.js >> $target_dir/js/custom-mathjax.min.js

cd $target_dir


rm -r $collect_dir
cd css
wget https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css -O bootstrap.min.css
cd ../js
wget https://ajax.googleapis.com/ajax/libs/jquery/2.2.4/jquery.min.js -O jquery.min.js
wget https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/js/bootstrap.min.js -O bootstrap.min.js

