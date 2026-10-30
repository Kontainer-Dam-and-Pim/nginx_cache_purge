#include <fcntl.h>

int
posix_fadvise(int fd, off_t offset, off_t len, int advice)
{
    (void) fd;
    (void) offset;
    (void) len;
    (void) advice;

    return 0;
}

int
posix_fadvise64(int fd, off_t offset, off_t len, int advice)
{
    return posix_fadvise(fd, offset, len, advice);
}
