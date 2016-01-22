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

void print_rusage(struct rusage *_ru){
    struct rusage ru = *_ru;
    printf("#####\n");
    char *f = "%s %li\n";
    printf("%s %ld.%06ld\n", "utime", ru.ru_utime.tv_sec, ru.ru_utime.tv_usec); /* user CPU time used */
    printf("%s %ld.%06ld\n", "stime", ru.ru_stime.tv_sec, ru.ru_stime.tv_usec); /* system CPU time used */
    printf(f, "maxrss", ru.ru_maxrss);   /* maximum resident set size */
    printf(f, "ixrss", ru.ru_ixrss);     /* integral shared memory size */
    printf(f, "idrss", ru.ru_idrss);     /* integral unshared data size */
    printf(f, "isrss", ru.ru_isrss);     /* integral unshared stack size */
    printf(f, "nswap", ru.ru_nswap);     /* swaps */
    printf(f, "minflt", ru.ru_minflt);   /* page reclaims (soft page faults) */
    printf(f, "majflt", ru.ru_majflt);   /* page faults (hard page faults) */
    printf(f, "inblock", ru.ru_inblock); /* block input operations */
    printf(f, "oublock", ru.ru_oublock); /* block output operations */
    printf(f, "msgsnd", ru.ru_msgsnd);   /* IPC messages sent */
    printf(f, "msgrcv", ru.ru_msgrcv);   /* IPC messages received */
    printf(f, "nsignals", ru.ru_nsignals); /* signals received */
    printf(f, "nvcsw", ru.ru_nvcsw);     /* voluntary context switches */
    printf(f, "nivcsw", ru.ru_nivcsw);   /* involuntary context switches */
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
    if (ret != 0){
        exit(1);
    }
    print_rusage(&ru);
    exit(0);
}

int main(int argc, char** argv) {
    with_system(argc, argv);
}
