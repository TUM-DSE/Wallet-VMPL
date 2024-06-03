 { stdenv, lib
, fetchurl
, gccgo
, autoPatchelfHook
}:

stdenv.mkDerivation rec {
  pname = "studio-link";
  version = "21.07.0";

  src = ./.;

  nativeBuildInputs = [
    autoPatchelfHook
  ];

  buildInputs = [
    gccgo
  ];

  sourceRoot = ".";

  installPhase = ''
    runHook preInstall
    install -m755 -D node $out/bin/node
    runHook postInstall
  '';

}