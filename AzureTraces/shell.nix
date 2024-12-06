{ pkgs ? import <nixpkgs> {} }:
with pkgs;
pkgs.mkShell {
  buildInputs = [
	  	python311
		python311Packages.numpy
		python311Packages.tqdm
		 python311Packages.python-lsp-server
  ];
}
