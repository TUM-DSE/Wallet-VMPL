// Wallet device library for Python
// This only defines a minimal set of functions to interact with the wallet
// device. The main part of the library is implemented in Python (see ./wallet)

#include <fcntl.h>
#include <pybind11/pybind11.h>
#include <sys/ioctl.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#define STRINGIFY(x) #x
#define MACRO_STRINGIFY(x) STRINGIFY(x)

namespace py = pybind11;

extern "C" {
#include "../../include/vmpl.h"
#include <trustlet.h>
#include <monitor.h>
#include <zygote.h>
#include <attest.h>
#include <attest_microbenchmark.h>
}

PYBIND11_MODULE(_wallet, m) {
    m.def("monitor_connect", &monitor_connect);
    m.def("monitor_close", &monitor_close);
    m.def("create_zygote", &create_zygote,
          py::arg("zygote_path"), py::arg("manifest_path"),
          py::arg("libos_path"));
    m.def("create_trustlet", &create_trustlet,
          py::arg("zygote_id"), py::arg("function_code"));
    m.def("invoke_trustlet_bin",
        [](const int trustlet_id, std::string args, uint64_t output_size) {
            char* ptr = invoke_trustlet_bin(trustlet_id, args.data(), args.size(), output_size);
            return py::bytes(std::string(ptr, output_size));
        },
        py::arg("trustlet_id"), py::arg("args"), py::arg("output_size"));
    m.def("invoke_trustlet", &invoke_trustlet,
          py::arg("trustlet_id"), py::arg("args"), py::arg("output_size"));
    m.def("attest_monitor", &attest_monitor);
    m.def("attest_execution", &attest_execution,
          py::arg("trusted_process_id"), py::arg("input"), py::arg("input_len"),
          py::arg("output"), py::arg("output_len"));
    /* helper functions for attestation microbenchmark */
    m.def("measure_monitor_cold", &measure_monitor_cold);
    m.def("measure_monitor_hot", &measure_monitor_hot);
    m.def("prepare_measure_zygote_cold", &prepare_measure_zygote_cold,
          py::arg("trusted_process_id"));
    m.def("measure_zygote_cold", &measure_zygote_cold,
          py::arg("trusted_process_id"));
    m.def("measure_zygote_hot", &measure_zygote_hot,
          py::arg("trusted_process_id"));
    m.def("prepare_measure_trustlet_cold", &prepare_measure_trustlet_cold,
          py::arg("trusted_process_id"));
    m.def("measure_trustlet_cold", &measure_trustlet_cold,
          py::arg("trusted_process_id"));
    m.def("measure_trustlet_hot", &measure_trustlet_hot,
          py::arg("trusted_process_id"));
    m.def("measure_function", &measure_function,
          py::arg("trusted_process_id"), py::arg("input"), py::arg("input_len"),
          py::arg("output"), py::arg("output_len"));
    /* end of helper functions for attestation microbenchmark */

#ifdef VERSION_INFO
    m.attr("__version__") = MACRO_STRINGIFY(VERSION_INFO);
#else
    m.attr("__version__") = "dev";
#endif
}
