{ fetchurl }: [
  {
    name = "gmp-6.3.0.tar.xz";
    archive = fetchurl {
      hash = "sha256-o8K4AgG4nmhhb0rTC8Zq7kknw85Q4zkpyoGdXENTiJg=";
      url = "mirror://gnu/gmp/gmp-6.3.0.tar.xz";
    };
  }
  {
    name = "mpfr-4.2.1.tar.xz";
    archive = fetchurl {
      hash = "sha256-J3gHNTpnJpeJlpRa8T5Sgp46vXqaW3+yeTiU4Y8fy7I=";
      url = "mirror://gnu/mpfr/mpfr-4.2.1.tar.xz";
    };
  }
  {
    name = "mpc-1.3.1.tar.gz";
    archive = fetchurl {
      sha256 = "1f2rqz0hdrrhx4y1i5f8pv6yv08a876k1dqcm9s2p26gyn928r5b";
      url = "mirror://gnu/mpc/mpc-1.3.1.tar.gz";
    };
  }
  {
    name = "gcc-13.2.0.tar.xz";
    archive = fetchurl {
      hash = "sha256-4nXnZEKmBnNBon8Exca4PYYTFEAEwEE1KIY9xrXHQ9o=";
      url = "mirror://gnu/gcc/gcc-13.2.0/gcc-13.2.0.tar.xz";
    };
  }
  {
    name = "binutils-2.41.tar.xz";
    archive = fetchurl {
      hash = "sha256-rppXieI0WeWWBuZxRyPy0//DHAMXQZHvDQFb3wYAdFA=";
      url = "mirror://gnu/binutils/binutils-2.41.tar.xz";
    };
  }
  {
    name = "R06_28_23.tar.gz";
    archive = fetchurl {
      hash = "sha256-Ikh5m3ygincRrIfTGSQ1TtSQR1B2B9AzvTJ7qGHsTTE=";
      url = "https://github.com/acpica/acpica/archive/refs/tags/R06_28_23.tar.gz";
    };
  }
  {
    name = "nasm-2.16.01.tar.bz2";
    archive = fetchurl {
      hash = "sha256-NbatLuBI1BxHefBz8+/Kd2KoIrfS1O9OjfJM9ldHuy4=";
      url = "https://www.nasm.us/pub/nasm/releasebuilds/2.16.01/nasm-2.16.01.tar.bz2";
    };
  }
]