# t/status.t -- cache_purge_status: the queue and the key indexes as JSON
use Test::Nginx::Socket 'no_plan';
use File::Temp qw(tempdir);

our $tmp = tempdir(CLEANUP => 1);
chmod 0755, $tmp;

my $port = server_port();

our $Upstream = qq{
    upstream backend {
        server 127.0.0.1:$port;
    }
};

$ENV{TEST_NGINX_SERVROOT} = server_root();
no_long_string();
run_tests();

__DATA__

=== TEST 1: no queue and no index
--- http_config eval
"    proxy_cache_path " . $::tmp . "/plain keys_zone=plain:1m;\n" . $::Upstream
--- config
    location /status {
        cache_purge_status;
    }
--- request
GET /status
--- error_code: 200
--- response_headers
Content-Type: application/json
Cache-Control: no-store
--- response_body chomp
{"queue":null,"indexes":[]}

=== TEST 2: only GET and HEAD
--- http_config eval
"    proxy_cache_path " . $::tmp . "/plain keys_zone=plain:1m;\n" . $::Upstream
--- config
    location /status {
        cache_purge_status;
    }
--- request
POST /status
--- error_code: 405

=== TEST 3: a queued wildcard is counted
--- http_config eval
"    proxy_cache_path " . $::tmp . "/queued keys_zone=queued:1m;
    cache_purge_background_queue on;
    cache_purge_throttle_ms      10ms;
" . $::Upstream
--- config
    location /cache {
        proxy_pass        http://backend/origin;
        proxy_cache       queued;
        proxy_cache_key   "$uri";
        proxy_cache_purge PURGE from 127.0.0.1;
    }
    location /status {
        cache_purge_status;
    }
--- request eval
["PURGE /cache/q/*", "GET /status"]
--- error_code eval
[202, 200]
--- response_body_like eval
["", qr/^\{"queue":\{"size":\d+,"max_size":1024,"in_progress":\d+,"backing_off":0,"enqueued":1,"coalesced":0,"rejected":0,"completed":\d+,"requeued":0,"dropped":0\},"indexes":\[\]\}$/]

=== TEST 4: a key index is listed with its state
--- http_config eval
"    proxy_cache_path " . $::tmp . "/indexed levels=1:2 keys_zone=indexed:1m;
    cache_purge_background_queue on;
    cache_purge_index            4m;
" . $::Upstream
--- config
    location /status {
        cache_purge_status;
    }
--- request
GET /status
--- error_code: 200
--- response_body_like eval
qr/"indexes":\[\{"zone":"indexed","state":"(pending|building|ready)","entries":0,"failures":0\}\]\}$/
