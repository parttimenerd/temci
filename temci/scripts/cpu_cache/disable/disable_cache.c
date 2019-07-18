/**
    Adapted from http://www.linuxquestions.org/questions/linux-kernel-70/disabling-cpu-caches-936077/
    and memtest86++ source code.
    http://www.spinics.net/lists/newbies/msg40952.html was helpful too.
*/

#include <linux/init.h>
#include <linux/module.h>

static int disable_cache_init(void)
{
        printk(KERN_ALERT "Disable cpu caches\n");
        __asm__("push   %rax\n\t"
                "mov    %cr0,%rax;\n\t"
                "or     $(1 << 30),%rax;\n\t"
                "mov    %rax,%cr0;\n\t"
                "wbinvd\n\t"
                "pop    %rax"
        );
        return 0;
}

static void disable_cache_exit(void)
{
        printk(KERN_ALERT "Enable cpu caches\n");
        __asm__("push   %rax\n\t"
                "mov    %cr0,%rax;\n\t"
                "and     $~(1 << 30),%rax;\n\t"
                "mov    %rax,%cr0;\n\t"
                "pop    %rax"
        );
}

module_init(disable_cache_init);
module_exit(disable_cache_exit);
