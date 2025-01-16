#!/usr/bin/env python3

import os
import pandas as pd

os.system("cd ../../svsm/; cargo tree -p svsm -e no-dev --prefix depth > ../Benchmarks/TCB/svsm.log")

with open("svsm.log") as f:
    deps = [x.replace("\n", "").replace(" (*)", "").replace(" (proc-macro)", "")[1:] for x in f.readlines()]

local_deps = [x for x in deps if "(" in x and "http" not in x]
git_deps = [x for x in deps if "(" in x and "http" in x]
cargo_deps = [x for x in deps if "(" not in x]

cargo_path = f"{os.environ.get('HOME')}/.cargo/registry/src/index.crates.io-6f17d22bba15001f/"

paths = ""

for d in local_deps:
    t = d.split(" ")
    name = t[0]
    d = t[2].replace("(", "").replace(")","")
    paths += d + " "

for d in cargo_deps:
    t = d.split(" ")
    name = t[0]
    d = cargo_path + name + "-" + t[1].replace("v", "")
    paths += d + " "

cargo_path = f"{os.environ.get('HOME')}/.cargo/git/checkouts/"

subdir = os.listdir(cargo_path)

for d in git_deps:
    t = d.split(" ")
    name = t[0]
    path = cargo_path
    for sub in subdir:
        if name in sub:
            path += sub
            break
    h = t[2].split("#")[1].replace(")","")[0:7]
    path += "/" + h + "/"
    paths += " " + path

os.system(f"cloc --csv --exclude-dir my_crypto {paths} > svsm.csv")

os.system("""inotifywait -m -r -e open --format '%w%f' -o crypto.log ../../svsm/kernel/src/my_crypto &
PID=$!
sleep 5
(cd ../../svsm/kernel/src/my_crypto/; ./build.sh)
kill $PID
cat crypto.log | grep -E "\.c$|\.h$|\.H$|\.s$|\.S$" > crypto.log.prep
cloc --csv --list-file=crypto.log.prep > crypto.csv
""")

df = pd.read_csv("svsm.csv").iloc[:, :-1]
df2 = pd.read_csv("crypto.csv").iloc[:, :-1]

l = "language"

df = df[df[l].str.contains("C") | df[l].str.contains("Rust") |\
        df[l].str.contains("Assembly") | df[l].str.contains("Header")]

df2 = df2[df2[l].str.contains("C") | df2[l].str.contains("Rust") |\
        df2[l].str.contains("Assembly") | df2[l].str.contains("Header")]

print("SVSM: ", df["code"].sum())
print("Crypto: ", df2["code"].sum())

print("Total: ", df["code"].sum() + df2["code"].sum())
