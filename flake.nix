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
            zellij
            herdr
            jq
          ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt-rfc-style);
    };
}
