{
  description = "SVSM";

  nixConfig.extra-substituters = [ "https://cache.garnix.io" ];

  nixConfig.extra-trusted-public-keys =
    [ "cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g=" ];

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-newer.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-2211.url = "github:NixOS/nixpkgs/nixos-22.11";
    nixpkgs-2111.url = "github:NixOS/nixpkgs/nixos-21.11";
    nixpkgs-2305.url = "github:NixOS/nixpkgs/nixos-23.05";
    nixpkgs-2311.url = "github:NixOS/nixpkgs/nixos-23.11";
    nixpkgs-2505.url = "github:NixOS/nixpkgs/nixos-25.05";
    nixpkgs-pktgen.url = "github:NixOS/nixpkgs/9cb344e96d5b6918e94e1bca2d9f3ea1e9615545";
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
    dpdk-cvms-src = {
      url = "github:TUM-DSE/dpdk-cvms/wallet-vfio-snp";
      flake = false;
    };
    fstack-playground.url = "github:pogoba/fstack-playground";
    fstack-playground.inputs.dpdk-cvms-src.follows = "dpdk-cvms-src";
  };

  outputs = { self, nixpkgs, flake-utils, nixos-generators, rust-overlay
    , bpftrace, ... }@args:
    (flake-utils.lib.eachSystem [ "x86_64-linux" ] (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pkgsnewer = args.nixpkgs-newer.legacyPackages.${system};
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
            patches = old.patches ++ [ ./patches/qemu_cvm_vhost.patch ./patches/qemu_cvm_vhost2.patch ];
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
          dpdk = pkgs2505.dpdk.overrideAttrs (final: prev: {
            src = self.inputs.dpdk-cvms-src;
            # src = /scratch/okelmann/dpdk-cvms;
          });
          dpdk-debug = selfpkgs.dpdk.overrideAttrs (final: prev: {
            outputs = [ "out" ];
            dontFixup = true;
            dontStrip = true;
            mesonFlags = prev.mesonFlags ++ [ "--buildtype=debug" "-Ddeveloper_mode=enabled" ];
            hardeningDisable = [ "all" ];
          });
          pktgen-dpdk = let
            pktgenpkgs = args.nixpkgs-pktgen.legacyPackages.${system};
            dpdk-for-pktgen = pktgenpkgs.dpdk.overrideAttrs (final: prev: {
              postPatch = prev.postPatch + ''
                substituteInPlace drivers/net/vhost/rte_eth_vhost.c --replace ".link_speed = 10000," ".link_speed = 100000,"
              '';
            });
            usePatchedDpdk = (pktgen: pktgen.override { dpdk = dpdk-for-pktgen; });
          in (usePatchedDpdk pktgenpkgs.pktgen).overrideAttrs (final: prev: {
              # src = /scratch/okelmann/Pktgen-DPDK;
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
          vpp = let
            vpppkgs = pkgsnewer;
            dpdk-for-vpp = vpppkgs.dpdk.overrideAttrs (final: prev: {
              postPatch = prev.postPatch + ''
                substituteInPlace drivers/net/vhost/rte_eth_vhost.c --replace ".link_speed = 10000," ".link_speed = 100000,"
              '';
            });
            usePatchedDpdk = (vpp: vpp.override { dpdk = dpdk-for-vpp; });
          in (usePatchedDpdk pkgsnewer.vpp);
		      # cvm-vfio = pkgs.linuxPackages.kernel.dev.stdenv.mkDerivation {
		      cvm-vfio = pkgs.stdenv.mkDerivation {
		        # doesnt seem to work: guest complains about invalid module format
		        name = "cvm-vfio";
		        src = pkgs.fetchFromGitHub {
              owner = "TUM-DSE";
              repo = "slick-linux";
              rev = "276b98a06d670080c34fcf018c78de813568d546"; # branch wallet-vfio-snp 2026-02-20
              sha256 = "sha256-pVe3xiBHil3cy9H5GRwVY0xJXG2/mBU/iiyoxOCp9ss=";
            };
		        nativeBuildInputs = with pkgs; [ elfutils flex bison bc perl openssl ];
		        postPatch = ''
		          patchShebangs scripts/
		        '';
		        configurePhase = ''
	            make olddefconfig
	            ./scripts/config --module VFIO
	            ./scripts/config --module VFIO_PCI
	            ./scripts/config --enable VFIO_CONTAINER
	            ./scripts/config --enable VFIO_NOIOMMU
	            make olddefconfig
		        '';
		        buildPhase = ''
	            make modules_prepare -j$(nproc)
	            make M=drivers/vfio modules -j$(nproc) KCFLAGS="-Wno-error" KBUILD_MODPOST_WARN=1
		        '';
		        installPhase = ''
	            mkdir -p $out/linux/drivers/vfio/
	            find drivers/vfio -name '*.ko' -exec cp {} $out/linux/drivers/vfio/ \;
		        '';
		        dontFixup = true;
		        dontStrip = true;
		        hardeningDisable = [ "all" ];
		      };
          perf = let
            kernel = pkgs.callPackage ./nix/linux.nix {
              kernelVariantName = "coconut_svsm";
              # kernelVariantName = "version_for_vfio";
            };
          in (pkgs.linuxPackagesFor kernel).perf;
          test = pkgs.callPackage ./node/pkg.nix { };
          iperf-fstack = args.fstack-playground.packages.${system}.iperf-fstack-native;
          iperf-fstack-cvms = args.fstack-playground.packages.${system}.iperf-fstack-native-cvms;
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
                openssl.dev
                hyperscan
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
		            python311Packages.numpy
		            python311Packages.pandas
		            python311Packages.tqdm
		            python311Packages.python-lsp-server
		            python311Packages.matplotlib
		            python311Packages.scikit-learn
		            python311Packages.seaborn
		            python311Packages.igraph
		            python311Packages.netaddr
		            python311Packages.colorlog
		            python311Packages.argcomplete
                texliveMedium
		stdenv.cc.cc.lib
		            selfpkgs.dpdk
		            selfpkgs.pktgen-dpdk
		            libbsd.dev
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
              export ATOMIC_LIB="${pkgs.stdenv.cc.cc.lib}/lib"
              export GLIBC_LIB="${pkgs.glibc}/lib"
              export GLIBC_STATIC="${pkgs.glibc.static}/lib"
              if [ ! -f "./container/99_config.yaml" ]; then
                ./container/netconf.sh 2> /dev/null
              fi;
	      LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib/"
            '';
          };
        };
      }));
}
