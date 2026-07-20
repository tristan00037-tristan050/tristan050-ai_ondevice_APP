#include <stddef.h>
#include <sys/ptrace.h>

void butler_secure_zero(void *pointer, size_t length) {
    volatile unsigned char *cursor = (volatile unsigned char *)pointer;
    while (length-- > 0) {
        *cursor++ = 0;
    }
    __asm__ __volatile__("" : : "r"(pointer) : "memory");
}

int butler_deny_debugger(void) {
    return ptrace(PT_DENY_ATTACH, 0, 0, 0);
}
