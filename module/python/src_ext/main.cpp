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
}

// These functions are taken from the ./app/t.c
// TODO: unify the code

typedef signed long long int u64;
struct svsm_call {
    void* caa;
    u64 rax;
    u64 rcx;
    u64 rdx;
    u64 r8;
    u64 r9;
};

struct zygote_data {
    void* zygote_data[3];
    uint64_t size[3];
};

void allocate_zygote_struct(struct zygote_data** z) {
    uint8_t* buf = (uint8_t*)::aligned_alloc(4096, 4096);
    for (int i = 0; i < 4096; i++) buf[i] = 0;
    *z = (zygote_data*)buf;
}

void load_file(const char* filename, uint8_t** buffer, uint64_t* buffer_size) {
    FILE* file = ::fopen(filename, "r");
    ::fseek(file, 0L, SEEK_END);
    uint64_t size = ::ftell(file);
    ::rewind(file);
    size_t buf_size_round_up = (size + 4096 - 1) & ~(4096 - 1);
    uint8_t* buf = (uint8_t*)::aligned_alloc(4096, buf_size_round_up);
    if (buf == 0) {
        ::fprintf(stderr, "Failed to allocate %zd", buf_size_round_up);
        ::exit(-1);
    }
    for (uint64_t i = 0; i < buf_size_round_up; i++) buf[i] = 0;
    size_t read_len = ::fread((void*)buf, 1, size, file);
    if (read_len != size) {
        ::fprintf(stderr, "Failed to load entire file %ld != %ld", read_len,
                  size);
        ::exit(-1);
    }
    *buffer = buf;
    *buffer_size = size;
}

void load_string(std::string string, uint8_t** buffer, uint64_t* buffer_size) {
    size_t buf_size_round_up = ((string.size() + 1) + 4096 - 1) & ~(4096 - 1); // + 1 for 0-terminating the string
    uint8_t* buf = (uint8_t*)::aligned_alloc(4096, buf_size_round_up);
    if (buf == 0) {
        ::fprintf(stderr, "Failed to allocate %zd", buf_size_round_up);
        ::exit(-1);
    }
    for (uint64_t i = 0; i < buf_size_round_up; i++) buf[i] = 0;
    string.copy((char*) buf, string.size());
    *buffer = buf;
    *buffer_size = string.size() + 1;
}

// ------------------------------
// Functions for the Python module

int open_device(const char* path = "/dev/vmpl_device") {
    int fd = ::open(path, O_RDWR);
    // skip error handling for now, let the python code handle the error
    // if (fd < 0) {
    //     throw std::runtime_error("Failed to open device");
    // }
    return fd;
}

void close_device(int fd) { ::close(fd); }

int create_zygote(int fd, const char* zygote_path, const char* manifest_path,
                  const char* libos_path) {
    uint8_t* zygote;
    uint64_t zygote_size;
    printf("load zygote\n");
    load_file(zygote_path, &zygote, &zygote_size);

    uint8_t* manifest;
    uint64_t manifest_size;
    load_file(manifest_path, &manifest, &manifest_size);

    uint8_t* libos;
    uint64_t libos_size;
    load_file(libos_path, &libos, &libos_size);

    struct zygote_data* z;
    allocate_zygote_struct(&z);
    z->zygote_data[0] = zygote;
    z->size[0] = zygote_size;
    z->zygote_data[1] = manifest;
    z->size[1] = manifest_size;
    z->zygote_data[2] = libos;
    z->size[2] = libos_size;

    struct monitor_call call;

    call.zygote.zygote_data = (void*)z;
    call.zygote.size = 4096;

    call.type = createZygote;

    int ret = ::ioctl(fd, VMPL_WR, &call);

    return ret;
}

int create_trustlet(int fd, const int zygote_id, const char* function_code) {
    uint8_t* function;
    uint64_t function_size;
    load_file(function_code, &function, &function_size);

    struct monitor_call call;
    call.type = createTrustlet;
    call.trustlet.zygote = zygote_id;
    call.trustlet.trustlet_data = function;
    call.trustlet.size = function_size;

    int ret = ::ioctl(fd, VMPL_WR, &call);

    return ret;
}

char* invoke_trustlet(int fd, const int trustlet_id, std::string argument_string) {
    uint8_t* argument;
    uint64_t argument_size;
    load_string(argument_string, &argument, &argument_size);

    struct monitor_call call;
    call.type = invokeTrustlet;
    call.invokation.process_id = trustlet_id;

    call.invokation.input_data = argument;
    call.invokation.input_data_size = argument_size;

    // todo: return value size
    size_t buf_size_round_up = (argument_size + 4096 - 1) & ~(4096 - 1);
    uint8_t* buf = (uint8_t*)::aligned_alloc(4096, buf_size_round_up);
    call.invokation.result = buf;
    call.invokation.result_size = buf_size_round_up;

    int ret = ::ioctl(fd, VMPL_WR, &call);
    // return ret;

    if (ret < 0) {
        throw std::runtime_error("Failed to invoke trustlet");
    }

    return (char*) call.invokation.result; // python takes ownership of memory
}

// ------------------------------

PYBIND11_MODULE(_wallet, m) {
    m.def("open_device", &open_device, py::arg("path") = "/dev/vmpl_device");
    m.def("close_device", &close_device, py::arg("fd"));

    m.def("create_zygote", &create_zygote, py::arg("fd"),
          py::arg("zygote_path"), py::arg("manifest_path"),
          py::arg("libos_path"));
    m.def("create_trustlet", &create_trustlet, py::arg("fd"),
          py::arg("zygote_id"), py::arg("function_code"));
    m.def("invoke_trustlet", &invoke_trustlet, py::arg("fd"),
          py::arg("trustlet_id"), py::arg("argument"));

#ifdef VERSION_INFO
    m.attr("__version__") = MACRO_STRINGIFY(VERSION_INFO);
#else
    m.attr("__version__") = "dev";
#endif
}
