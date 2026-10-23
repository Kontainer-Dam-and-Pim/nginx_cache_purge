{
  perSystem =
    {
      lib,
      pkgs,
      self',
      ...
    }:
    let
      testNginx = pkgs.perlPackages.buildPerlPackage {
        pname = "Test-Nginx";
        version = "0.32";
        src = pkgs.fetchurl {
          url = "mirror://cpan/authors/id/A/AG/AGENT/Test-Nginx-0.32.tar.gz";
          hash = "sha256-i0esnTSJqyKJyy2Lvb8FmHi4/vIitv50rWFI4aKAptw=";
        };
        propagatedBuildInputs = with pkgs.perlPackages; [
          HTTPMessage
          IPCRun
          ListMoreUtils
          LWP
          TestBase
          TestLongString
          TextDiff
          URI
        ];
        doCheck = false;
        meta.license = with lib.licenses; [
          artistic1
          gpl1Plus
        ];
      };
    in
    {
      devShells.default = pkgs.mkShell {
        inputsFrom = [ self'.packages.default ];
        packages = [
          self'.packages.default
          (pkgs.perl.withPackages (_: [ testNginx ]))
          pkgs.actionlint
          pkgs.clang-tools
          pkgs.cppcheck
          pkgs.jq
          pkgs.gdb
          pkgs.python3
          pkgs.ruff
          pkgs.shellcheck
          pkgs.zizmor
        ]
        ++ lib.optional pkgs.stdenv.hostPlatform.isLinux pkgs.valgrind;
      };
    };
}
