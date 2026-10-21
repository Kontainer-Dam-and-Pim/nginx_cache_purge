{ self, ... }:
{
  perSystem =
    { lib, pkgs, ... }:
    let
      cachePurge = pkgs.nginxModules.cache-purge.overrideAttrs {
        version = "0-unstable-${self.lastModifiedDate or "0"}";
        src = lib.fileset.toSource {
          root = ../.;
          fileset = lib.fileset.unions [
            ../config
            ../ngx_cache_purge_module.c
          ];
        };
      };
    in
    {
      packages.default = pkgs.nginxMainline.override { modules = [ cachePurge ]; };
    };
}
