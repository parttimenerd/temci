/*
 * Modifications by Johannes Bechberger (2015)
 *
 * Copyright (C) 2011 Timo Weingärtner <timo@tiwe.de>
 *
 * This file is part of hadori.
 *
 * hadori is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * hadori is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with hadori.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <string>
#include <vector>
#include <queue>
#include <unordered_map>
#include <iostream>
#include <sstream>
#include <fstream>
#include <algorithm>

#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <sys/types.h>
#include <sys/stat.h>
#include <dirent.h>
#include <sysexits.h>
#include <unistd.h>

#define DEBUG false
#define VERBOSE true
#define DRY_RUN false

std::ostream debug(std::clog.rdbuf()), verbose(std::clog.rdbuf()), error(std::clog.rdbuf());

struct inode {
	std::string const filename;
	struct stat const stat;
};

inline bool compare (inode const & l, inode const & r) {
	char lbuffer[1 << 14];
	char rbuffer[1 << 14];
	std::ifstream lf(l.filename.c_str());
	std::ifstream rf(r.filename.c_str());
	
	while (not lf.eof()) {
		lf.read(lbuffer, sizeof(lbuffer));
		rf.read(rbuffer, sizeof(rbuffer));
		if (lf.gcount() != rf.gcount())
			return false;
		if (memcmp(lbuffer, rbuffer, lf.gcount()))
			return false;
	}
	return true;
}

inline std::ostream& operator<< (std::ostream& os, inode const & i) {
	os << "Inode " << i.stat.st_ino << ", represented by " << i.filename;
	return os;
}

void do_link (inode const & i, std::string const & other) {
	if (!link(i.filename.c_str(), other.c_str())) {
		error << "linking " << i << " to " << other << " succeeded before unlinking (race condition)" << std::endl;
		exit(EX_UNAVAILABLE);
	}
	if (errno != EEXIST) {
		char const * const errstring = strerror(errno);
		error << "error linking " << i << " to " << other << ": " << errstring << ", nothing bad happened." << std::endl;
		exit(EX_UNAVAILABLE);
	}
	if (unlink(other.c_str())) {
		char const * const errstring = strerror(errno);
		error << "error unlinking " << other << " before linking " << i << " to it: " << errstring << std::endl;
		exit(EX_UNAVAILABLE);
	}
	if (link(i.filename.c_str(), other.c_str())) {
		char const * const errstring = strerror(errno);
		error << "error linking " << i << " to " << other << ": " << errstring << ", destination filename was already unlinked." << std::endl;
		exit(EX_UNAVAILABLE);
	}
}

void handle_file(std::string const & path, struct stat const & s) {
	static std::unordered_map<ino_t, inode const> kept;
	static std::unordered_map<ino_t, ino_t const> to_link;
	static std::unordered_multimap<off_t, ino_t const> sizes;
	
	debug << "examining " << path << std::endl;
	if (kept.count(s.st_ino)) {
		debug << "another link to inode " << s.st_ino << " that we keep" << std::endl;
		return;
	}
	if (to_link.count(s.st_ino)) {
		inode const & target = kept.find(to_link[s.st_ino])->second;
		debug << "another link to inode " << s.st_ino << " that we merge with " << target << std::endl;
		do_link(target, path);
		if (s.st_nlink == 1)
			to_link.erase(s.st_ino);
		return;
	}
	inode const f{path, s};
	debug << f << " is new to us" << std::endl;
        auto pair = sizes.equal_range(s.st_size);
        bool finished = false;
        std::for_each(pair.first,
                pair.second,
                [&](std::unordered_multimap<off_t, ino_t const>::value_type& it){
            if (finished) return;
            inode const & candidate = kept.find(it.second)->second;
            debug << "looking if it matches " << candidate << std::endl;
            if (candidate.stat.st_mode != s.st_mode)
                    return;
            if (candidate.stat.st_uid != s.st_uid)
                    return;
            if (candidate.stat.st_gid != s.st_gid)
                    return;
            if (candidate.stat.st_mtime != s.st_mtime)
                    return;
            if (!compare(candidate, f))
                    return;
            verbose << "linking " << candidate << " to " << path << std::endl;
            if (s.st_nlink > 1)
                    to_link.insert({s.st_ino, it.second});
            if (!DRY_RUN)
                    do_link(candidate, path);
            finished = true;
        }
        );
        if (finished) return;
	debug << "we keep " << f << std::endl;
	kept.insert({s.st_ino, std::move(f)});
	sizes.insert({s.st_size, s.st_ino});
}

void recurse (std::string const & dir, dev_t const dev) {
	DIR* D;
	struct dirent *d;
	struct stat s;
	std::queue<std::string> subdirs;
	
	if (!(D = opendir(dir.c_str()))) {
		char const * const errstring = strerror(errno);
		error << "opendir(\"" << dir << "\"): " << errstring << std::endl;
		return;
	}
	while ((d = readdir(D))) {
		std::string path(dir);
		path += '/';
		path += d->d_name;
		if (lstat(path.c_str(), &s)) {
			char const * const errstring = strerror(errno);
			error << "lstat(\"" << path << "\"): " << errstring << std::endl;
			continue;
		}
		if (s.st_dev != dev) {
			error << path << " resides on another file system, ignoring." << std::endl;
			continue;
		}
		if (S_ISDIR(s.st_mode))
			subdirs.push(d->d_name);
		if (S_ISREG(s.st_mode))
			handle_file(path, s);
	}
	closedir(D);
	// directories get handled after the parent dir is closed to prevent exhausting fds
	for (; !subdirs.empty(); subdirs.pop()) {
		if (subdirs.front() == "." || subdirs.front() == "..")
			continue;
		std::string subdir(dir);
		subdir += '/';
		subdir += subdirs.front();
		recurse(subdir, dev);
	}
}

void recurse_start (std::string const & dir) {
	struct stat s;

	if (lstat(dir.c_str(), &s)) {
		char const * const errstring = strerror(errno);
		error << "lstat(\"" << dir << "\"): " << errstring << std::endl;
		exit(EX_NOINPUT);
	}
	
	static dev_t const dev = s.st_dev;
	if (dev != s.st_dev) {
		error << dir << " resides on another file system, ignoring." << std::endl;
		return;
	}
	
	if (S_ISDIR(s.st_mode))
		recurse(dir, dev);
	if (S_ISREG(s.st_mode))
		handle_file(dir, s);
}

int main (int const argc, char const * const * const argv) {
	
        if (!DEBUG)
		debug.rdbuf(nullptr);
        if (!DEBUG && !VERBOSE && !DRY_RUN)
		verbose.rdbuf(nullptr);
	
        for (int i = 1; i < argc; i++){
            recurse_start(argv[i]);
        }

	return EX_OK;
}
