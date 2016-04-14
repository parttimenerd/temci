#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <iterator>
#include <memory.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <tuple>


bool starts_with(char* base, char* str) {
    // Source: http://ben-bai.blogspot.de/2013/03/c-string-startswith-endswith-indexof.html
    return (strstr(base, str) - base) == 0;
}

bool ends_with(char* base, char* str) {
    // Source: http://ben-bai.blogspot.de/2013/03/c-string-startswith-endswith-indexof.html
    int blen = strlen(base);
    int slen = strlen(str);
    return (blen >= slen) && (0 == strcmp(base + blen - slen, str));
}

template <typename T>
std::ostream& operator<< (std::ostream& out, const std::vector<T>& v) {
    // Source: http://stackoverflow.com/a/10758845
    if ( !v.empty() ) {
        out << '[';
        std::copy (v.begin(), v.end(), std::ostream_iterator<T>(out, ", "));
        out << "\b\b]";
    }
    return out;
}

bool is_randomizable(char* arg){
    return starts_with(arg, "-L") or ends_with(arg, ".o");
}

typedef std::vector<std::tuple<bool, std::vector<char*>>>  groups_t;

groups_t group(std::vector<char*> args){
    groups_t ret;
    for (auto& arg : args){
        bool r = is_randomizable(arg);
        if (ret.empty() or std::get<0>(ret.back()) == r){
            std::vector<char*> a = {arg};
            ret.push_back(std::make_tuple(r, a));
        } else {
            std::get<1>(ret.back()).push_back(arg);
        }
    }
    return ret;
}

std::vector<char *> join(groups_t& groups){
    std::vector<char *> ret;
    for (auto& t : groups){
        ret.insert(ret.end(), std::get<1>(t).begin(), std::get<1>(t).end());
    }
    return ret;
}

void randomize(groups_t& groups){
    for (auto& t : groups){
        if (std::get<0>(t)){
            random_shuffle(std::get<1>(t).begin(), std::get<1>(t).end());
        }
    }
}

void link(groups_t groups, char* used_ld, int tries){
    std::cout << "hi\n";
    if (tries == 0){
        return;
    }
    randomize(groups);
    auto args = join(groups);
    char** argv = (char**)malloc(sizeof(char*)*(args.size() + 2));
    argv[0] = used_ld;
    argv[args.size() + 1] = NULL;
    //std::cout << "hi\n";
    pid_t pid = fork();
    if (pid == -1) {
        std::cerr << "fork\n";
        exit(EXIT_FAILURE);
    }

    if (pid == 0){
        execvp(used_ld, argv);
    } else {
        int status;
        //std::cout << "hi\n";
        if (waitpid(pid, &status, 0) == -1){
            std::cerr << "waitpid\n";
            exit(EXIT_FAILURE);
        }
        //std::cout << "status " << status << "\n";
        if (status > 0){
            //std::cout << "hi  dsfg\n";
            link(groups, used_ld, tries - 1);
        }
    }
}

int main(int argc, char* argv[]){
    std::vector<char*> args;
    for (int i = 1; i < argc; i++){
        args.push_back(argv[i]);
    }
    //std::cout << args;
    bool randomize = getenv("RANDOMIZATION_linker") != NULL and strcmp(getenv("RANDOMIZATION_linker"), "true");
    //std::cout << randomize << "\n";
    char* used_ld = getenv("RANDOMIZATION_used_ld");
    if (!used_ld){
        used_ld = "/usr/bin/ld";
    }
    if (randomize){
        link(group(args), used_ld, 1);
    }
    execvp(used_ld, argv);
    return 0;
}
