#!/usr/bin/env python3
from pathlib import Path

ZYGOTE_DATA_START = 200
ZYGOTE_DATA_END = 201
ZYGOTE_INIT_START = 201
ZYGOTE_INIT_END = 202
ZYGOTE_MEASURE_START=198
ZYGOTE_MEASURE_END=199

TRUSTLET_CREATION_START=203
TRUSTLET_CREATION_END=204
TRUSTLET_MEASURE_START=205
TRUSTLET_MEASURE_END=206
TRUSTLET_FUNCTION_START=204
TRUSTLET_FUNCTION_END=207

INPUT_MEASURE_START=190
INPUT_MEASURE_END=191
OUTPUT_MEASURE_START=192
OUTPUT_MEASURE_END=193

INVOKE_DATA_START=210
INVOKE_DATA_END=211
INVOKE_SETUP_START=211
INVOKE_SETUP_END=212
INVOKE_DATA_COPY_START=212
INVOKE_DATA_COPY_END=213
INVOKE_TIME_START=213
INVOKE_TIME_END=214
INVOKE_RESULT_COPY_START=220
INVOKE_RESULT_COPY_END=221





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
        if not (r_dict.get(end, None)) and not (r_dict.get(start, None)):
            print(start,end)
            print(r_dict.get(start), r_dict.get(end))
            return 0
        for i in range(len(d[end])):
            e = r_dict[end][i]
            s = r_dict[start][i]
            total += e - s
        return total
    def sum_key_word(s,d):
        start = globals()[f"{s}_START"]
        end = globals()[f"{s}_END"]
        return sum_all(end, start, d)

    run_sums = []
    c = 0
    for r in runs:
        def find_missing_time():
            last = 0
            last_timestamp = 0
            for rr in r:
                time = int(rr.split(": ")[0])
                n = int(rr.split(": ")[1].split(" Monitor")[0])
                if last == ZYGOTE_INIT_END and n == 255:
                    return (time -last_timestamp)
                else:
                    last = n
                    last_timestamp = time

        missing_time = find_missing_time()
        if not missing_time:
            print("Failed")
            exit()
        r_dict = {}
        for rr in r:
            time = int(rr.split(": ")[0])
            n = int(rr.split(": ")[1].split(" Monitor")[0])
            if not r_dict.get(n,None):
                r_dict[n] = []
            r_dict[n].append(time)
        #zygote data copy
        zygote_data_copy = sum_key_word("ZYGOTE_DATA",r_dict)
        zygote_measure = sum_key_word("ZYGOTE_MEASURE",r_dict)
        zygote_init = sum_key_word("ZYGOTE_INIT",r_dict) + missing_time
        trustlet_creation = sum_key_word("TRUSTLET_CREATION",r_dict)
        trustlet_measure = sum_key_word("TRUSTLET_MEASURE",r_dict)
        trustlet_function = sum_key_word("TRUSTLET_FUNCTION",r_dict)
        invoke_data = sum_key_word("INVOKE_DATA",r_dict)
        invoke_setup = sum_key_word("INVOKE_SETUP", r_dict)
        invoke_data_copy = sum_key_word("INVOKE_DATA_COPY",r_dict)
        invoke_time = sum_key_word("INVOKE_TIME",r_dict)
        invoke_result_copy = sum_key_word("INVOKE_RESULT_COPY",r_dict)
        input_measure = sum_key_word("INPUT_MEASURE",r_dict)
        if len(r_dict[OUTPUT_MEASURE_START]) < 3:
           continue
        output_measure = sum_key_word("OUTPUT_MEASURE",r_dict)
        total_time = r_dict[255][-1] - r_dict[254][0]

        #Remove overlapping timestamps
        zygote_data_copy -= zygote_measure
        trustlet_function -= trustlet_measure
        invoke_data_copy -= input_measure
        invoke_result_copy -= output_measure

        sums = [zygote_data_copy,zygote_init,trustlet_creation,
                    trustlet_function,invoke_data,invoke_setup,
                    invoke_data_copy,invoke_time,invoke_result_copy,
                    total_time,zygote_measure,trustlet_measure,
                    input_measure,output_measure]
        run_sums.append(sums)
        c += 1
    return run_sums

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer',
    '311.compression', '411.image-recognition',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    '504.dna-visualisation'
]

print("zygote_data_copy,zygote_init,trustlet_creation,trustlet_function,invoke_data,invoke_setup", end = "")
print(",invoke_data_copy,invoke_time,invoke_result_copy,total_time,zygote_measure,trustlet_measure,input_measure,output_measure,benchmark,alloc,cow")
for a in ["prealloc"]:
    for cow in ["cow" ]:
        for b in BENCHMARKS:
            file_name = f"wallet_extern-{b}-{a}-{cow}"
            file_path = Path("measure")
            #file_path /= f"wallet_{cow}_{a}"
            file_path /= file_name
            data = parse(file_path)
            for p in data:
                p = [str(x) for x in p]
                print(",".join(p),end="")
                print(f",{b},{a},{cow}")
