{ stdenvNoCC, lib, fetchgit, getopt, stdenv, bison, curl, git, perl, flex, zlib
, gcc, callPackage }:

stdenvNoCC.mkDerivation {
  pname = "coreboot-gcc";
  version = "13.2.0";

  src = fetchgit {
    url = "https://review.coreboot.org/coreboot";
    rev = "e33fc66fc9ddc28e4eddebc06eac5cd0ec1c3af1";
    hash = "sha256-1CYk9ZYuH1SaGpmFnaIgWdgtBAh3vsB0frb1AZDw0jM=";
    fetchSubmodules = false;
    leaveDotGit = true;
    postFetch = ''
      PATH=${
        lib.makeBinPath [ getopt ]
      }:$PATH ${stdenv.shell} $out/util/crossgcc/buildgcc -W > $out/.crossgcc_version
      rm -rf $out/.git
    '';
    allowedRequisites = [ ];
  };

  nativeBuildInputs = [ bison curl git perl ];
  buildInputs = [ flex zlib gcc ];

  enableParallelBuilding = true;
  dontConfigure = true;
  dontInstall = true;

  postPatch = ''
    patchShebangs util/crossgcc/buildgcc

    mkdir -p util/crossgcc/tarballs

    ${lib.concatMapStringsSep "\n"
    (file: "ln -s ${file.archive} util/crossgcc/tarballs/${file.name}")
    (callPackage ./compsource.nix { })}

    patchShebangs util/genbuild_h/genbuild_h.sh
  '';

  buildPhase = ''
    export CROSSGCC_VERSION=$(cat .crossgcc_version)
    make crossgcc-x64 CPUS=$NIX_BUILD_CORES DEST=$out
  '';

}
