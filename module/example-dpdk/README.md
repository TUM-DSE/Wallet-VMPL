## Systems

* measure_vm
  * mirror: Optimal baseline (albeit single threaded) in CVM
  * iomgr: Slick design (multithreaded)
  * noiomgr: Naive polling design with dpdk (multithreaded)
  * insecure: all VNFs in a single CVM process (multithreaded)
  * kata: kata containers on the host spawn VMs and run container workload in there (uses linux networking)
  * mirrorUnconfidential: like mirror, but in an unconfidential VM
  * mirrorKni: like mirror but with linux kernel networking on the host and in the VM

* measure_multivm
  * mirror: Secure with one VM per VNF



example:

`make run_tests TEST_DIR=example-dpdk TEST_TARGET=run_noiomgr`
