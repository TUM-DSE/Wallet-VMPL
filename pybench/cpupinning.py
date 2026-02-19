rose_cluster_size = 6 # shares L3 cache
rose_hyperthreads = 2
wilfred_hyperthreads = 2

class CpuPinner:
    """
    Functions that return ranges like 1-2 of cpus to pin certain tasks to.
    """

    def __init__(self, server: 'Server'):
        self.server = server
        self._cores_available = None

    def _vm_number(self, vm_number: int) -> int:
        """
        vm_number arg: is 0 in single-vm tests. In multi-VM tests, the first one is 1. We normalize this so that 0 is always the first one.
        """
        if vm_number > 0:
            return vm_number - 1
        else:
            return vm_number

    def cores_available(self) -> int:
        if self._cores_available is None:
            self._cores_available = int(self.server.exec("nproc --all"))
        return self._cores_available

    def in_cluster(self, cluster: int, offset: int, length: int = 1):
        assert offset + length - 1 < rose_cluster_size # dont use this function, if the cpu range doesnt fit into a cluster
        start = ((cluster * rose_cluster_size) + offset) % self.cores_available()
        end = (start + length - 1) % self.cores_available()
        return f"{start}-{end}"

    def qemu(self, vm_number: int) -> str:
        vm_number = self._vm_number(vm_number)
        return self.in_cluster(vm_number, 0, length=rose_cluster_size)

    def vmux_main(self):
        return "0"

    def vmux_runner(self, vm_number: int):
        vm_number = self._vm_number(vm_number)
        overcommittment = int((vm_number) / (self.cores_available() / rose_hyperthreads / rose_cluster_size))
        offset = (overcommittment * 2 + 2) % rose_cluster_size
        return self.in_cluster(vm_number, offset)

    def vmux_rx(self, vm_number: int):
        vm_number = self._vm_number(vm_number)
        overcommittment = int((vm_number) / (self.cores_available() / rose_hyperthreads / rose_cluster_size))
        offset = (overcommittment * 2 + 3) % rose_cluster_size
        return self.in_cluster(vm_number, offset)

    def redis_shards(self):
        return int(self.cores_available() / wilfred_hyperthreads)
