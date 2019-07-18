/**
    Adapted from http://www.linuxquestions.org/questions/linux-kernel-70/disabling-cpu-caches-936077/
    and memtest86++ source code.
    http://www.spinics.net/lists/newbies/msg40952.html was helpful too.
*/

#include <linux/init.h>
#include <linux/module.h>

static int flush_cache_init(void)
{
        printk(KERN_ALERT "Flush cpu caches\n");
        __asm__("wbinvd");
        return 0;
}

static void flush_cache_exit(void)
{
}

module_init(flush_cache_init);
module_exit(flush_cache_exit);
