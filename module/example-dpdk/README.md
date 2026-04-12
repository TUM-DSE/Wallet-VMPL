## Systems

* measure_vm
  * ~~mirror: Optimal baseline (albeit single threaded)~~
  * iomgr: Slick design (multithreaded)
  * noiomgr: Naive polling design with dpdk (multithreaded)
  * insecure: all VNFs in a single CVM process (multithreaded)

* measure_multivm
  * mirror: Secure with one VM per VNF



example:

`make run_tests TEST_DIR=example-dpdk TEST_TARGET=run_noiomgr`
