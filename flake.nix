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
    nixpkgs-2505.url = "github:NixOS/nixpkgs/nixos-25.05";
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

  outputs = { self, nixpkgs, flake-utils, nixos-generators, rust-overlay
    , bpftrace, ... }@args:
    (flake-utils.lib.eachSystem [ "x86_64-linux" ] (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pkgs2211 = args.nixpkgs-2211.legacyPackages.${system};
        pkgs2111 = args.nixpkgs-2111.legacyPackages.${system};
        pkgs2305 = args.nixpkgs-2305.legacyPackages.${system};
        pkgs2311 = args.nixpkgs-2311.legacyPackages.${system};
        pkgs2505 = args.nixpkgs-2505.legacyPackages.${system};
        flakepkgs = self.packages.${system};
        selfpkgs = self.packages.${system};
        overlays = [ (import rust-overlay) ];
        pkgsrust = import nixpkgs { inherit system overlays; };
      in {
        packages = {
          rustdev = pkgsrust.rust-bin.stable."1.77.2".default.override {
            targets = [ "x86_64-unknown-none" ];
            extensions = [ "rust-docs" "rustfmt" "clippy" ];
          };
          igvm = pkgs.callPackage ./nix/igvm.nix { };
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
          qemu-coconut-igvm = pkgs.qemu.overrideAttrs (new: old: {
            src = builtins.fetchurl {
              url =
                "https://github.com/Sabanic-P/qemu/releases/download/v8.2.0-igvm/qemu8.2.0.tar.gz";
              sha256 =
                "sha256:15cmwlkiwd001hhbv8rcvdnsdgr092x2jvy15m9c3k4s7g36a7yh";
            };
            version = "8.2.0";
            buildInputs = old.buildInputs ++ [ self.packages.${system}.igvm ];
            igvm = self.packages.${system}.igvm;
            patches = old.patches ++ [ ./patches/qemu_cvm_vhost.patch ];
            configureFlags = old.configureFlags ++ [
              "--target-list=x86_64-softmmu"
              "--disable-gtk"
              "--disable-sdl"
              "--disable-sdl-image"
              "--enable-igvm"
            ];
          });
          vmplguest-image = pkgs.callPackage ./nix/vmplguest-image.nix { };
          bpftrace = bpftrace.packages.x86_64-linux.default;
          dpdk = pkgs2505.dpdk.overrideAttrs (final: prev: let
            debug = false;
          in {
            # Github only allows to fetch this from a browser right now, but not from bash. Check out manually for now.
            # src = pkgs2505.fetchFromGitHub {
            #   owner = "TUM-DSE";
            #   repo = "dpdk-cvms";
            #   rev = "2e60199505e22493ec1afb56dc8e192fac13b06b"; # branch wallet-vfio-snp 2026-02-19
            #   sha256 = "";
            # };
            src = /scratch/okelmann/dpdk-cvms;
            dontFixup = debug;
            dontStrip = debug;
          });
          pktgen-dpdk = pkgs2505.pktgen.overrideAttrs (final: prev: {
		        postPatch = prev.postPatch + ''
              substituteInPlace lib/lua/lua_dpdk.c --replace "__rte_weak" "__my_weak"
            '';

            # lua users have to require("Pktgen") so they need Pktgen.lua (although it won't be found automatically yet)
            postInstall = ''
              mkdir -p $out/lib/lua/5.3/
              cp $src/Pktgen.lua $out/lib/lua/5.3/
            '';

		        mesonFlags = [ "-Denable_lua=true" ];
		      });
          test = pkgs.callPackage ./node/pkg.nix { };
        };
        pkgs = nixpkgs.legacyPackages.${system};
        devShells = let
          common_deps = with pkgs; [
            nixos-generators.packages.${system}.nixos-generate
            ccls # c lang serv
            meson
            ninja
            gdb
            bridge-utils
            cloud-utils
          ];
        in {
          default = pkgs.stdenv.mkDerivation {
            name = "devshell";
            buildInputs = with pkgs;
              [
                meson
                ninja
                cmake
                json_c
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
                zstd
                yq
                autoconf
                automake
                libtool
                openssl
                autoconf-archive
                rust-bindgen
                rust-cbindgen
                cunit
                pkg-config
                gcc
                gccgo
                zip
                inotify-tools
                cargo-depgraph
                cloc
                cargo-cache
                libcgroup
                python3
                python311Packages.requests
                python311Packages.matplotlib
                python311Packages.seaborn
                python311Packages.pandas
                python311Packages.tqdm
                python311Packages.scikit-learn
                python311Packages.pybind11
                python311Packages.pytest
                python311Packages.fire
                python311Packages.requests
                python311Packages.setuptools
                unzip
                numactl
                python311Packages.docker
                python311Packages.invoke
                python311Packages.lxml
                python311Packages.psutil
                python311Packages.pip
                python311Packages.numpy
                python311Packages.click
                python311Packages.voluptuous
                python311Packages.jinja2
                python311Packages.tomli
                python311Packages.tomli-w
                python311Packages.matplotlib
                python311Packages.seaborn
                python311Packages.pandas
                python311Packages.bottle
		python311Packages.igraph
		            python311Packages.netaddr
		            python311Packages.colorlog
		            python311Packages.argcomplete
                texliveMedium
		stdenv.cc.cc.lib
		            selfpkgs.dpdk
		            selfpkgs.pktgen-dpdk
		            # (dpdk.overrideAttrs (final: prev: let
              #       debug = false;
              #     in {
              #     src = /scratch/okelmann/dpdk;
              #     mesonFlags = prev.mesonFlags ++ lib.optional debug "--buildtype=debug";
              #     outputs= ["out"];
              #     dontFixup = debug;
              #     dontStrip = debug;
              #   }))

              ] ++ common_deps ++ [
                self.packages.${system}.qemu-coconut-igvm
                self.packages.${system}.igvm
              ] ++ [ self.packages.${system}.rustdev ]
              ++ [ self.packages.${system}.bpftrace ] ++ [ pkgs2311.docker ];
            hardeningDisable = [ "all" ];
            shellHook = ''
              PATH="${pkgs.clang-tools}/bin:$PATH"
              if [ ! -f "./container/99_config.yaml" ]; then
                ./container/netconf.sh 2> /dev/null
              fi;
	      LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib/"
            '';
          };
        };
      }));
}
