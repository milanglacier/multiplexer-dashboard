{
  description = "multiplexer-dashboard: a fullscreen dashboard of tmux, zellij and herdr sessions and the coding agents in them";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # zellij 0.46 is the first release that reports the status of coding
      # agents. While nixpkgs has an older zellij, the devShell takes
      # zellij's release binary, which is statically linked on Linux.
      zellijRelease =
        pkgs:
        let
          version = "0.46.0";
          targets = {
            x86_64-linux = {
              target = "x86_64-unknown-linux-musl";
              hash = "sha256-qO5ZnrNXthQkQ8kVBqTs46qIEct13PKyjRlL1mhTx50=";
            };
            aarch64-linux = {
              target = "aarch64-unknown-linux-musl";
              hash = "sha256-xBaz0p7Jxxuvh1T+ZmY6/k9hU5WJXj+bi2470PcEJCc=";
            };
            x86_64-darwin = {
              target = "x86_64-apple-darwin";
              hash = "sha256-47YZevBLKG9096n19RnlqM8Ei+ZfA3GjKw1gq6yXOEo=";
            };
            aarch64-darwin = {
              target = "aarch64-apple-darwin";
              hash = "sha256-cWoceIe+g8yBOQABKhVqTY4O4UaKxWxYopnJ2ImM3JA=";
            };
          };
          t = targets.${pkgs.stdenv.hostPlatform.system};
        in
        if nixpkgs.lib.versionAtLeast pkgs.zellij.version version then
          pkgs.zellij
        else
          pkgs.stdenvNoCC.mkDerivation {
            pname = "zellij";
            inherit version;
            src = pkgs.fetchurl {
              url = "https://github.com/zellij-org/zellij/releases/download/v${version}/zellij-${t.target}.tar.gz";
              inherit (t) hash;
            };
            sourceRoot = ".";
            dontConfigure = true;
            dontBuild = true;
            dontStrip = true;
            installPhase = "install -Dm755 zellij $out/bin/zellij";
          };
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            python3
            uv # Python 3.9 for the unit tests (nixpkgs no longer has it)
            ruff
            pyrefly
            gnumake
            tmux # end-to-end harness, and a multiplexer under test
            (zellijRelease pkgs)
            herdr
            jq
          ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);
    };
}
