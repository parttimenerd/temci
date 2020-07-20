/**
 * A simple wrapper around exec that reports the resource usage for a given program.
 * "#####" separates the program output from the appended resource usage report.
 * Each line of the report has the following structure:
 * [measured var name] [int value]
 */

#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <unistd.h>
#include <memory.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <errno.h>
#include "header.c"

void print_rusage(struct rusage *_ru){
    struct rusage ru = *_ru;
    printf("%s\n", header);
    char *f = "%s %li\n";
    fprintf(stderr, "%s %ld.%06ld\n", "utime", ru.ru_utime.tv_sec, ru.ru_utime.tv_usec); /* user CPU time used */
    fprintf(stderr, "%s %ld.%06ld\n", "stime", ru.ru_stime.tv_sec, ru.ru_stime.tv_usec); /* system CPU time used */
    fprintf(stderr, f, "maxrss", ru.ru_maxrss);   /* maximum resident set size */
    fprintf(stderr, f, "ixrss", ru.ru_ixrss);     /* integral shared memory size */
    fprintf(stderr, f, "idrss", ru.ru_idrss);     /* integral unshared data size */
    fprintf(stderr, f, "isrss", ru.ru_isrss);     /* integral unshared stack size */
    fprintf(stderr, f, "nswap", ru.ru_nswap);     /* swaps */
    fprintf(stderr, f, "minflt", ru.ru_minflt);   /* page reclaims (soft page faults) */
    fprintf(stderr, f, "majflt", ru.ru_majflt);   /* page faults (hard page faults) */
    fprintf(stderr, f, "inblock", ru.ru_inblock); /* block input operations */
    fprintf(stderr, f, "oublock", ru.ru_oublock); /* block output operations */
    fprintf(stderr, f, "msgsnd", ru.ru_msgsnd);   /* IPC messages sent */
    fprintf(stderr, f, "msgrcv", ru.ru_msgrcv);   /* IPC messages received */
    fprintf(stderr, f, "nsignals", ru.ru_nsignals); /* signals received */
    fprintf(stderr, f, "nvcsw", ru.ru_nvcsw);     /* voluntary context switches */
    fprintf(stderr, f, "nivcsw", ru.ru_nivcsw);   /* involuntary context switches */
    fprintf(stderr, "%s\n", header);
}

void with_exec(int argc, char** argv){
  id_t pid = fork();

  if (pid == 0){ // as child
    char** arr = malloc(sizeof(char*) * argc);
    int i = 0;
    for (i = 0; i < argc - 1; i++){
      arr[i] = argv[i + 1];
    }
    arr[argc - 1] = 0;
    if (execvp(argv[1], arr) == -1){
      exit(errno);
    } else {
      exit(0);
    }
  } else {
    int status;
    struct rusage ru;
    wait3(&status, 0, &ru);
    if (status > 0){
      exit(1);
    }
    print_rusage(&ru);
    exit(status);
  }
}

void with_system(int argc, char** argv){
    int ret = system(argv[1]);
    struct rusage ru;
    getrusage(RUSAGE_CHILDREN, &ru);
    print_rusage(&ru);
    if (ret != 0){
        exit(ret);
    }
    exit(0);
}

int main(int argc, char** argv) {
    with_system(argc, argv);
}
