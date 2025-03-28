#!/usr/bin/env python3

def parse(filename):
    with open(filename, "r") as f:
        text = f.read()

    res_list = []
    current = {}

    text = text.split(": 52")[1].split("\n")
    text = [x for x in text if x]
    positions = []
    counter = 0
    for line in text:
        counter += 1
        if "zygote_data start" in line:
            positions.append(counter - 1)

    runs = []

    for i in range(len(positions)):
        start = positions[i]
        if i+1 < len(positions):
            end = positions[i + 1]
        else:
            end = len(text) + 1
        if end - start > 33:
            runs.append(text[(start-1):(end-1)])

    run_data = []
    """
    Zygote Data: 201 - 200
    Zygote Init: 202 - 201
    Trustlet Creation: 204 - 203
    Trustlet Function: 205 - 204
    Invoke Data: 211 - 210
    Invoke Setup: 212 - 211
    Invoke Data Copy: 213 - 212
    Invoke Time: 214 - 213
    Invoke Result Copy: 221 - 220
    Total Time: End Line - First Line
    """

    def sum_all(end,start,d):
        total = 0
        for i in range(len(d[end])):
            e = r_dict[end][i]
            s = r_dict[start][i]
            total += e - s
        return total

    run_sums = []
    c = 0
    for r in runs:
        r_dict = {}
        for rr in r:
            time = int(rr.split(": 2")[0])
            n = int(rr.split(": 2")[1].split(" Monitor")[0]) + 200
            if not r_dict.get(n,None):
                r_dict[n] = []
            r_dict[n].append(time)
        #zygote data copy
        zygote_data_copy = sum_all(201,200,r_dict)
        zygote_init = sum_all(202,201,r_dict)
        trustlet_creation = sum_all(204,203,r_dict)
        trustlet_function = sum_all(205,204,r_dict)
        invoke_data = sum_all(211,210,r_dict)
        invoke_setup = sum_all(212, 211, r_dict)
        invoke_data_copy = sum_all(213,212,r_dict)
        invoke_time = sum_all(214, 213,r_dict)
        invoke_result_copy = sum_all(221,220,r_dict)
        total_time = r_dict[255][-1] - r_dict[254][0]
        sums = [zygote_data_copy,zygote_init,trustlet_creation,
                    trustlet_function,invoke_data,invoke_setup,
                    invoke_data_copy,invoke_time,invoke_result_copy,
                    total_time]
        run_sums.append(sums)
        c += 1
    return run_sums

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer',
    '311.compression',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    '504.dna-visualisation'
]

print("zygote_data_copy,zygote_init,trustlet_creation,trustlet_function,invoke_data,invoke_setup", end = "")
print(",invoke_data_copy,invoke_time,invoke_result_copy,total_time,benchmark,alloc,cow")
for a in ["no_prealloc", "prealloc"]:
    for cow in ["", "-no_cow"]:
        for b in BENCHMARKS:
            file_name = f"wallet-{b}-{a}{cow}"
            file_path = "results/" + file_name
            data = parse(file_path)
            if "-no_cow" in cow:
                c = "cow"
            else:
                c = "no_cow"
            for p in data:
                p = [str(x) for x in p]
                print(",".join(p),end="")
                print(f",{b},{a},{c}")
