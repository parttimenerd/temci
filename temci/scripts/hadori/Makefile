# Modifications by Johannes Bechberger (2015)
#
# Copyright (C) 2011 Timo Weingärtner <timo@tiwe.de>
#
# This file is part of hadori.
#
# hadori is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# hadori is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with hadori.  If not, see <http://www.gnu.org/licenses/>.

LDLIBS= -lstdc++
CXXFLAGS?=-O2 -Wall
CXXFLAGS+=-std=c++11

all: hadori

hadori: hadori.o
hadori.o: hadori.C

clean:
	rm -f hadori hadori.o hadori.1
