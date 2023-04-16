# To use this file, install Nix: https://nixos.org/download.html#download-nix
# and enable flakes: https://nixos.wiki/wiki/Flakes#Enable_flakes
# Then install direnv: https://direnv.net/
{
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem
      (system: let
        pkgs = import nixpkgs {
          inherit system;
        };
        buildInputs = [
          pkgs.black
          pkgs.espeak
          pkgs.ffmpeg
          pkgs.imagemagick
          pkgs.pkg-config
          pkgs.python3Packages.pip-tools
          pkgs.zlib
        ];
      in {
        devShell = pkgs.mkShell {
          inherit buildInputs;
          shellHook = ''
              export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath buildInputs}:$LD_LIBRARY_PATH"
              export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib.outPath}/lib:$LD_LIBRARY_PATH"
              export FONTCONFIG_FILE="${pkgs.fontconfig.out}/etc/fonts/fonts.conf"
          '';
        };
      });
}
