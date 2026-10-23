#include <ngx_config.h>
#include <ngx_core.h>

static ngx_pool_t *volatile  ngx_cache_purge_lsan_bootstrap_pool;

ngx_cycle_t *__real_ngx_init_cycle(ngx_cycle_t *old_cycle);
ngx_cycle_t *__wrap_ngx_init_cycle(ngx_cycle_t *old_cycle);

ngx_cycle_t *
__wrap_ngx_init_cycle(ngx_cycle_t *old_cycle)
{
    ngx_cycle_t  *cycle;

    cycle = __real_ngx_init_cycle(old_cycle);

    if (cycle == NULL && ngx_is_init_cycle(old_cycle)) {
        ngx_cache_purge_lsan_bootstrap_pool = old_cycle->pool;
    }

    return cycle;
}
