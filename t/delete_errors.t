# t/delete_errors.t -- a purge that could not delete a file answers 500
use File::Temp qw(tempdir);

our $tmp;

BEGIN {
    $tmp = tempdir(CLEANUP => 1);
    chmod 0755, $tmp;

    system("cc", "-shared", "-fPIC", "-O2", "-o", "$tmp/undeletable.so",
           "t/lib/undeletable.c", "-ldl") == 0
        or die "could not build t/lib/undeletable.c\n";

    $ENV{LD_PRELOAD} = "$tmp/undeletable.so";
}

use Test::Nginx::Socket 'no_plan';

my $port = server_port();

our $HttpConfig = qq{
    proxy_cache_path $tmp/undeletable levels=1:2 keys_zone=undel:1m;
    upstream backend {
        server 127.0.0.1:$port;
    }
};

our $Location = q{
    location /cache {
        proxy_pass        http://backend/origin;
        proxy_cache       undel;
        proxy_cache_key   "$uri";
        proxy_cache_valid 200 1h;
        proxy_cache_purge PURGE from 127.0.0.1;
    }
    location /origin {
        add_header Vary Accept-Encoding;
        return 200 "ok";
    }
};

$ENV{TEST_NGINX_SERVROOT} = server_root();
no_shuffle();
no_long_string();
run_tests();

__DATA__

=== TEST 1: exact purge of a file that cannot be deleted
--- http_config eval: $::HttpConfig
--- config eval: $::Location
--- request eval
["GET /cache/exact", "PURGE /cache/exact"]
--- error_code eval
[200, 500]

=== TEST 2: synchronous wildcard purge of files that cannot be deleted
--- http_config eval: $::HttpConfig
--- config eval: $::Location
--- request eval
["GET /cache/wild/1", "PURGE /cache/wild/*"]
--- error_code eval
[200, 500]

=== TEST 3: synchronous purge_all of files that cannot be deleted
--- http_config eval: $::HttpConfig
--- config eval
my $l = $::Location;
$l =~ s/PURGE from/PURGE purge_all from/;
$l
--- request eval
["GET /cache/all", "PURGE /cache/all"]
--- error_code eval
[200, 500]

=== TEST 4: vary-aware purge whose variant walk cannot delete what it found
--- http_config eval: $::HttpConfig . "    cache_purge_vary_aware on;\n"
--- config eval: $::Location
--- request eval
["GET /cache/vary", "PURGE /cache/vary"]
--- more_headers eval
["Accept-Encoding: gzip", ""]
--- error_code eval
[200, 500]
