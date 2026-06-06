## Systems

* measure_vm
  * mirror: Optimal baseline (albeit single threaded) in CVM
  * iomgr: Slick design (multithreaded)
  * noiomgr: Naive polling design with dpdk (multithreaded)
  * insecure: all VNFs in a single CVM process (multithreaded)
  * kata: kata containers on the host spawn VMs and run container workload in there (uses linux networking)
  * mirrorUnconfidential: like mirror, but in an unconfidential VM
  * mirrorKni: like mirror but with linux kernel networking on the host and in the VM
  * mirrorMicrobenchmark: like mirror, but instead of placing pktgen outside the CVM, we place it inside and connect it directly to the mirror instance (via vhost-user)
  * iomgrMicrobenchmark: the iomgr acts as a load generator to directly measure a vnflet

* measure_multivm
  * mirror: Secure with one VM per VNF



example:

`make run_tests TEST_DIR=example-dpdk TEST_TARGET=run_noiomgr`
