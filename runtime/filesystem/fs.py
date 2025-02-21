#!/usr/bin/env python3

import os

C_NODE_DEFINE = """
#include "libos_fs.h"
#include "libos_fs_pseudo.h"

#define __DEFINE_LIBOS_FS_PSEUDO_NODE(name, data, size) \\
    static int name(struct libos_dentry* dent, char** out_data, size_t* out_size) { \\
        __UNUSED(dent); \\
        *out_data = (char*) data; \\
        *out_size = size; \\
        return 0; \\
    }

#define __ADD_NODE(name, data) do{\\
    node = pseudo_add_str(root, name, &data); \\
    node->str.no_free = true; \\
    node->perm = PSEUDO_PERM_LINK; \\
    } while (0)

#define __ADD_DIR(name) struct pseudo_node* tmp = pseudo_add_dir(root, name); struct pseudo_node* root = tmp; (void)root;

"""

FS_IN = "/" + os.environ.get("FS_IN", "fs/")
FS_OUT = "/" + os.environ.get("FS_OUT", "fs_out/")

os.makedirs(os.path.dirname(os.path.realpath(__file__)) + FS_OUT + "files/",exist_ok=True)

slash_replacement = "__"

def get_name(subpath, a, f):
    return (subpath + a + f).replace("/",slash_replacement).replace(".", "dot").replace("-","dash").replace("+", "pp")

class Filestructure:
    name = ""
    directories = {}
    files = []
    parent = None

    def parse(self):
        path = os.path.dirname(os.path.realpath(__file__)) + FS_IN
        s = list(os.walk(path))
        self.name =  ""
        p, f, d = s[0]
        self.files = d
        for directory in f:
            new_directory = Filestructure()
            new_directory.name = directory
            new_directory.parent = self
            new_directory.directories = {}
            new_directory._parse(path, path + directory, s)
            self.directories[directory] = new_directory

    def _parse(self, path, subpath, parse_list):
        for p, f, d in parse_list:
            if subpath in p and subpath.split("/")[-1] == (p.split("/")[-1]):
                self.files = d
                for directory in f:
                    new_directory = Filestructure()
                    new_directory.name = directory
                    new_directory.parent = self
                    new_directory.directories = {}
                    new_directory._parse(path, p+ "/" + directory, parse_list)
                    self.directories[directory] = new_directory
                break

        pass

    def print(self):
        self._print("")

    def _print(self, a):
        print(f"{a}{self.name}:")
        print(f"{a}Files: {self.files}\n")
        for f in self.directories:
            self.directories[f]._print(a + "        ")

    def create_c_files(self):
        out_dir = os.path.dirname(os.path.realpath(__file__)) + FS_OUT + "files/"
        in_dir = os.path.dirname(os.path.realpath(__file__)) + FS_IN
        self._create_c_files(out_dir, in_dir, self.name)

    def _create_c_files(self, out_dir, in_dir, subpath):
        a = "/" if len(subpath) > 1 else ""
        current_path = in_dir + subpath
        for f in self.files:
            target_array_name = get_name(subpath, a, f)
            target_file_name = target_array_name + ".h"
            src_file_name = in_dir + subpath + a + f
            os.system(f"xxd -n {target_array_name} -i {src_file_name} > {out_dir}{target_file_name}")
        for d in self.directories:
            self.directories[d]._create_c_files(out_dir, in_dir, subpath + a + self.directories[d].name)


    def create_fs(self):
        self._create_fs_()

    def _create_fs_(self):
        out_dir = os.path.dirname(os.path.realpath(__file__)) + FS_OUT

        c_file = C_NODE_DEFINE
        pseudo_header = ""
        init_header = ""


        for d in self.directories:
            struct = self.directories[d]
            c_file += struct._get_include(out_dir + "files/", struct.name )

        c_file += "\n"

        for d in self.directories:
            struct = self.directories[d]
            c_file += struct._define_nodes(out_dir + "files/", struct.name)

        for d in self.directories:
            struct = self.directories[d]

            init_header += f"if ((ret = init_static_fs_{struct.name}()) < 0) goto err;\n"
            pseudo_header += f"int init_static_fs_{struct.name}(void);\n"

            c_file += f"\nint init_static_fs_{struct.name}() "+\
                f"{{\n    struct pseudo_node* root = pseudo_add_root_dir(\"{struct.name}\"); (void)root;\n" +\
                "    struct pseudo_node* node; (void)node;\n"
            c_file += struct._create_fs_sub(struct.name, "    ")
            c_file += "\n    return 0;\n}\n"

        with open(out_dir + "fs.c", "w") as f:
            f.write(c_file)

        with open(out_dir + "libos_fs_pseudo_static.h", "w") as f:
            f.write(pseudo_header)

        with open(out_dir + "libos_fs_extension.h", "w") as f:
            f.write(init_header)


    def _get_include(self, out_dir, subpath):
        includes = ""
        a = "/" if len(subpath) > 1 else ""
        for f in self.files:
            target_array_name = get_name(subpath, a, f)
            target_file_name = target_array_name + ".h"
            includes += "#include \"files/"+ target_file_name +"\"\n"

        for d in self.directories:
            struct = self.directories[d]
            includes = includes + struct._get_include(out_dir, subpath + a + struct.name)

        return includes

    def _define_nodes(self, out_dir, subpath):
        nodes = ""
        a = "/" if len(subpath) > 1 else ""
        for f in self.files:
            target_array_name = get_name(subpath, a, f)
            target_file_name = target_array_name + ".h"
            nodes += f"__DEFINE_LIBOS_FS_PSEUDO_NODE({target_array_name}_, {target_array_name}, {target_array_name}_len)\n"

        for d in self.directories:
            struct = self.directories[d]
            nodes += struct._define_nodes(out_dir, subpath + a + struct.name)

        return nodes


    
    def _create_fs_sub(self, subpath, ind):
        files = "\n"
        a = "/" if len(subpath) > 1 else ""

        for f in self.files:
            target_function_name = get_name(subpath, a, f) + "_"
            name = f
            files += f"{ind}__ADD_NODE(\"{name}\", {target_function_name});\n"

        for d in self.directories:
            struct = self.directories[d]
            files += ind + "{\n"
            files += ind + 4*" " + f"__ADD_DIR(\"{struct.name}\");\n"
            files += struct._create_fs_sub(subpath + a + struct.name, ind + "    ")
            files += ind + "}\n"


        return files

a = Filestructure()
a.parse()

#a.print()
a.create_c_files()
a.create_fs()
