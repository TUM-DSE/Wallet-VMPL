#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "../client/cpuid.h"
#include <stdio.h>

#define FUNCTION 0x14000000000
#define NEWLINE "\n"
const char* init =
    "import ctypes" NEWLINE
    "import json" NEWLINE
    "a=ctypes.string_at(0x140_0000_0000)" NEWLINE
    "exec(a)" NEWLINE;

const char* function_call =
    "input=ctypes.string_at(0x280_0000_0000)" NEWLINE
    "input = json.loads(input)" NEWLINE
    "res = handle(input)" NEWLINE
    "res = json.dumps(res).encode() + b'\0'" NEWLINE
    "ptr=ctypes.POINTER(ctypes.c_char*len(res))" NEWLINE
    "dst=ctypes.cast(0x300_0000_0000, ptr)" NEWLINE
    "ctypes.memmove(dst, res, len(res))" NEWLINE;


int main(int argc, char *argv[])
{
    PyStatus status;
    PyConfig config;
    PyConfig_InitPythonConfig(&config);

    status = PyConfig_SetBytesString(&config, &config.program_name, argv[0]);
    if (PyStatus_Exception(status)) {
        return -1;
    }

    status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status)) {
        return -1;
    }
    PyConfig_Clear(&config);
    PyRun_SimpleString(init);
    while(1) {
        PyRun_SimpleString(function_call);
        notify_monitor();
    }
    if (Py_FinalizeEx() < 0) {
        return -1;
    }
    return 0;
}
