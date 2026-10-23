#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#define UNDELETABLE  "/undeletable/"

int
unlink(const char *path)
{
    static int (*real)(const char *);

    if (strstr(path, UNDELETABLE) != NULL) {
        errno = EACCES;
        return -1;
    }

    if (real == NULL) {
        real = (int (*)(const char *)) dlsym(RTLD_NEXT, "unlink");
    }

    return real(path);
}

int
unlinkat(int dirfd, const char *path, int flags)
{
    static int (*real)(int, const char *, int);
    char        link[64], dir[4096];
    ssize_t     n;

    if (strstr(path, UNDELETABLE) != NULL) {
        errno = EACCES;
        return -1;
    }

    snprintf(link, sizeof(link), "/proc/self/fd/%d", dirfd);
    n = readlink(link, dir, sizeof(dir) - 2);

    if (n > 0) {
        dir[n] = '/';
        dir[n + 1] = '\0';

        if (strstr(dir, UNDELETABLE) != NULL) {
            errno = EACCES;
            return -1;
        }
    }

    if (real == NULL) {
        real = (int (*)(int, const char *, int)) dlsym(RTLD_NEXT, "unlinkat");
    }

    return real(dirfd, path, flags);
}
