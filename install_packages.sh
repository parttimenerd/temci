#! /bin/sh

# Install all needed packages
# Currently supports fedora (and similar) and debian/ubuntu based systems

install_msg="Install the required system packages"
sudo=`which sudo || echo ""`

if which apt > /dev/null; then  # debian or ubuntu based system
  echo $install_msg
  $sudo apt-get install python3-pandas python3-cffi python3-cairo python3-cairocffi python3-matplotlib python3-numpy python3-scipy time linux-tools-`uname -r` gcc make
elif (which yum || which dnf) > /dev/null; then # fedora based system
  echo $install_msg
  cmd=`(which yum > /dev/null && echo yum) || (which dnf > /dev/null && echo dnf)`
  $sudo $cmd install python3-pandas python3-cffi python3-cairo python3-cairocffi python3-matplotlib python3-numpy python3-scipy perf gcc make
fi