#!/usr/bin/env python3

from pathlib import Path
import sys

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer',
    '311.compression', '411.image-recognition',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    '504.dna-visualisation'
]

trace_data = {}

def parse_benchmark(b,r,me="profiling"):
    for alloc in ["prealloc"]:
        p = Path("results/")
        p /= me
        p /= f"wallet_profiling_cow_{alloc}"
        #bpftrace
        try:
            trace_path = p / f"trace-{b}"
            with open(trace_path) as f:
                trace = f.read()
        except:
            print(f"Trace missing {trace_path}")
            return

        trace = trace.split("Clearing\n")[1:]
        trace = [x.split("\n")[0:2] for x in trace if len(x) > 1]
        trace = [x for x in trace if len(x[0])>1]
        vmexit = [int(x[0].split(": ")[1]) for x in trace]
        vmgexit = [int(x[1].split(": ")[1]) for x in trace]

        #Monitor stats
        try:
            stats_path = p / f"wallet_profiling-{b}"
            with open(stats_path) as f:
                trace = f.read()
        except:
            print(f"Trace missing {stats_path}")
            return
       
        trace = trace.split("[SVSM] ERROR: Stat\n")[1:]
        trace = [x.split("\n")[0:3] for x in trace]
        pvalidate = [int(x[0].split(": ")[2]) for x in trace]
        page_fault = [int(x[1].split(": ")[2]) for x in trace]
        cow = [int(x[2].split(": ")[2]) for x in trace]
        if len(vmexit) != len(pvalidate):
            print("Missing results/Benchmark might have failed?")
            print(f"Path: {stats_path}\nBenchmark: {b}\n")
            return
        for i in range(len(vmexit)):
            r.write(f"{b},{alloc},{vmexit[i]},{vmgexit[i]},{pvalidate[i]},{page_fault[i]},{cow[i]}\n")

def parse_memory(b,r):
        try:
            with open(f"results/memory_extern/wallet_extern_cow_prealloc/wallet_extern-{b}") as f:
                trace = f.read()
        except:
            print(f"Trace missing results/wallet_traces_{alloc}/wallet_profiling-{b}")
            return

        trace = trace.split("[SVSM] ERROR: Stat\n")[1:]
        trace = [x.split("\n")[3:5] for x in trace]
        cow = [int(x[0].split(": ")[2]) for x in trace]
        no_cow = [int(x[1].split(": ")[2]) for x in trace]
        import pprint
        for i in range(len(cow)):
            r.write(f"wallet,{b},{(cow[i]+no_cow[i]) * 4096},{cow[i]},{no_cow[i]}\n")

def parse_memory_vm(b,r,t):
    with open(f"results/memory/{t}") as f:
        l = f.read()

    l = l.split(f"BENCHMARK DONE: {b}")[0]
    print(b)
    l = l.split(f"BENCHMARK: {b}")[1]
    ll = l.split("\n")
    res = []
    for l in ll:
        if "Memory utilization:" in l:
            z = l.split("Memory utilization: ")[1]
            res.append(int(z))
    for rr in res:
        r.write(f"{t},{b},{rr},,\n")

if len(sys.argv) < 2:
    print("Specifiy memory or trace")
    exit(-1)

match sys.argv[1]:
    case "memory":
        with open("memory.csv", "w") as f:
            f.write("type,bench,total,cow,no_cow\n")
            for b in BENCHMARKS:
                parse_memory(b,f)
                #parse_memory_vm(b,f,"vm")
                #parse_memory_vm(b,f,"cvm")
                #parse_memory_vm(b,f,"kata")

    case "trace":
        csv_header = "bench,prealloc,vmexit,vmgexit,pvalidate,page_fault,cow\n"
        with open("trace_result_measure.csv", "w") as f1:
            f1.write(csv_header)
            with open("trace_result.csv", "w") as f2:
                f2.write(csv_header)
                for b in BENCHMARKS:
                    parse_benchmark(b,f1,"measure_profiling")
                    parse_benchmark(b,f2,"profiling")

    case _:
        print(sys.argv[1], "is not a valid option")
