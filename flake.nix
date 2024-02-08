{
  description = "SVSM";

  nixConfig.extra-substituters = [ "https://cache.garnix.io" ];

  nixConfig.extra-trusted-public-keys =
    [ "cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g=" ];

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-2211.url = "github:NixOS/nixpkgs/nixos-22.11";
    nixpkgs-2111.url = "github:NixOS/nixpkgs/nixos-21.11";
    nixpkgs-2305.url = "github:NixOS/nixpkgs/nixos-23.05";
    nixpkgs-2311.url = "github:NixOS/nixpkgs/nixos-23.11";
    nixpkgs-unstable.url =
      "github:NixOS/nixpkgs/269028fe51e7832507cd33afa1891bccbf32be48";
    flake-utils.url = "github:numtide/flake-utils";
    rust-overlay.url = "github:Sabanic-P/rust-overlay";
    nixos-generators = {
      url = "github:nix-community/nixos-generators";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    bpftrace.url = "github:mmisono/bpftrace/kvm_module_btf";
    qemu-coconut-src = {
      url =
        "git+https://github.com/coconut-svsm/qemu.git?ref=svsm-v8.0.0&submodules=1";
      flake = false;
    };
  };

  outputs =
    { self, nixpkgs, flake-utils, nixos-generators, rust-overlay, bpftrace, ... }@args:
    (flake-utils.lib.eachSystem [ "x86_64-linux" ] (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pkgs2211 = args.nixpkgs-2211.legacyPackages.${system};
        pkgs2111 = args.nixpkgs-2111.legacyPackages.${system};
        pkgs2305 = args.nixpkgs-2305.legacyPackages.${system};
        pkgs2311 = args.nixpkgs-2311.legacyPackages.${system};
        pkgsunstable = args.nixpkgs-unstable.legacyPackages.${system};
        flakepkgs = self.packages.${system};
        selfpkgs = self.packages.${system};
        overlays = [ (import rust-overlay) ];
        pkgsrust = import nixpkgs {
          inherit system overlays;
        };
      in 
      {
        packages = {
          rustdev = pkgsrust.rust-bin.nightly."2024-01-10".default.override {targets = [ "x86_64-unknown-none" ];};
          qemu-coconut = pkgs2311.qemu.overrideAttrs (new: old: {
            src = self.inputs.qemu-coconut-src;
            version = "8.0.0";
            configureFlags = old.configureFlags ++ [
              "--target-list=x86_64-softmmu"
              "--disable-gtk"
              "--disable-sdl"
              "--disable-sdl-image"
            ];
          });
          vmplguest-image = pkgs.callPackage ./nix/vmplguest-image.nix { };
          bpftrace = bpftrace.packages.x86_64-linux.default;
        };

        devShells = let
          common_deps = with pkgs; [
            just
            nixos-generators.packages.${system}.nixos-generate
            ccls # c lang serv
            meson
            ninja
            gdb
            bridge-utils
            cloud-utils
          ];
        in {
          # use clang over gcc because it has __builtin_dump_struct()
          default = pkgs.stdenv.mkDerivation {
            name = "devshell";
            buildInputs = with pkgs;
              [
                # dependencies for libvfio-user
                meson
                ninja
                cmake
                json_c
                cmocka
                pkg-config
                libuuid
                nasm
                coreboot-toolchain.x64
                guestfs-tools
                libguestfs-with-appliance
                flex
                bison
                perf-tools
                llvmPackages.bintools
                man
                git-lfs
              ] ++ common_deps ++ [ self.packages.x86_64-linux.qemu-coconut ]
              ++ [ self.packages.x86_64-linux.rustdev ] ++ [ self.packages.x86_64-linux.bpftrace ];
            hardeningDisable = [ "all" ];
            # prevent clangStdenv from overriding the fixed clang-tools binaries from nixos
            shellHook = ''
              PATH="${pkgs.clang-tools}/bin:$PATH"
            '';
          };

        };
      }));
}
