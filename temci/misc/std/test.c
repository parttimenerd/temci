#include <stdio.h>
#include <stdlib.h>

int main(int argc, char* argv[]){
	long long num = atoll(argv[1]);
	long long ret = 0;
	for (long long i = 0; i < num; i++){
		ret = ret * num % (ret - 1);
	}
	printf("%d", (int)ret);
}
