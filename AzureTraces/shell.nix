{ pkgs ? import <nixpkgs> {} }:
with pkgs;
pkgs.mkShell {
  buildInputs = [
  		unrar
	  	python311
		python311Packages.numpy
		python311Packages.pandas
		python311Packages.tqdm
		python311Packages.python-lsp-server
		python311Packages.matplotlib
		python311Packages.scikit-learn
		python311Packages.seaborn
		texliveMedium
  ];
}
