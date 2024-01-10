{ pkgs, lib, modulesPath, ... }:
let
  keys = map (key: "${builtins.getEnv "HOME"}/.ssh/${key}")
    [ "id_rsa.pub" "id_ecdsa.pub" "id_ed25519.pub" ];
  #  kernel-vmpl = pkgs.linuxKernel.customPackage {
  #	version = "6.5.0-vmpl";
  #	configfile = /scratch/patrick/vmpl/.config;
  #	#patch = /scratch/patick/wkernel.patch;
  #	src =  "linuxsrc";
  #};
in
{
  imports = [
    (modulesPath + "/profiles/qemu-guest.nix")
    (modulesPath + "/virtualisation/qemu-vm.nix")
    #<nixpkgs/nixos/modules/virtualisation/qemu-vm.nix>
  ];
  # somehow udev does not pick up hvc0?
  systemd.services."serial-getty" = {
    wantedBy = [ "multi-user.target" ];
    serviceConfig.ExecStart = "${pkgs.util-linux}/sbin/agetty  --login-program ${pkgs.shadow}/bin/login --autologin root hvc0 --keep-baud vt100";
  };
  systemd.services."serial-getty@hvc0".enable = false;



  #virtualization.useDefaultFilesystems = true;

  # slows things down
  systemd.services.systemd-networkd-wait-online.enable = false;

  #boot.loader.grub.enable = true;
  boot.initrd.enable = true;
  boot.kernelPackages =
    let
      linux-vmpl = { fetchurl, buildLinux, ... } @ args:
        buildLinux (args // rec {
          version = "6.5.0-vmpl";
          modDirVersion = "6.5.0";
          src = fetchurl {
            url = "https://github.com/coconut-svsm/linux/archive/e1335c6f029281db280945e084ec2d079934e744.tar.gz";
            hash = "sha256-iIgv8CrksuydkevTk31b9D/BcXAXeO+JqaxZcRkCDo4=";
          };
          kernelPatches = [

            {
              name = "vmpl";
              patch = ./kernel.patch;
              extraConfig = ''
              '';
            }
          ];
          extraMeta.branch = "6.5";
        } // (args.argsOverride or { }));
      linux-vmpl-build = pkgs.callPackage linux-vmpl { };
    in
    pkgs.recurseIntoAttrs (pkgs.linuxPackagesFor linux-vmpl-build);
  #boot.loader.initScript.enable = true;
  ## login with empty password
  users.extraUsers.root.initialHashedPassword = "";
  services.openssh.enable = true;

  users.users.root.openssh.authorizedKeys.keyFiles = lib.filter builtins.pathExists keys;
  networking.firewall.enable = false;

  system.stateVersion = "23.05";
  
  fileSystems."/mnt" = {
    device = "home";
    fsType = "9p";
    # skip mount in nested qemu
    options = [ "trans=virtio" "nofail" "msize=104857600" ];
  };

  fileSystems."/linux" = {
    device = "linux";
    fsType = "9p";
    # skip mount in nested qemu
    options = [ "trans=virtio" "nofail" "msize=104857600" ];
  };

  users.users.root.openssh.authorizedKeys.keys = [
    (builtins.readFile ../key.pub)
  ];

  services.getty.helpLine = ''
    Log in as "root" with an empty password.
    If you are connect via serial console:
    Type Ctrl-a c to switch to the qemu console
    and `quit` to stop the VM.
  '';

  services.getty.autologinUser = lib.mkDefault "root";

  documentation.doc.enable = false;
  documentation.man.enable = false;
  documentation.nixos.enable = false;
  documentation.info.enable = false;
  programs.bash.enableCompletion = false;
  programs.command-not-found.enable = false;

  environment.systemPackages = with pkgs;
    [
      busybox
      devmem2
      sysbench
      cloud-hypervisor
      bpftrace
      tmux
      fio
    ];
}
