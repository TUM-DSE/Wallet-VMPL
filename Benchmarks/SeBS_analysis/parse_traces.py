#!/usr/bin/env python3

BENCHMARKS = [
    '110.dynamic-html', #'120.uploader',
    '210.thumbnailer',
    '311.compression',
    '501.graph-pagerank', '502.graph-mst', '503.graph-bfs',
    '504.dna-visualisation'
]

trace_data = {}

def parse_benchmark(b,r):
    for alloc in ["no_prealloc", "prealloc"]:
        #bpftrace
        try:
            with open(f"results/wallet_traces_{alloc}/{b}") as f:
                trace = f.read()
        except:
            print(f"Trace missing results/wallet_traces_{alloc}/{b}")
            return

        trace = trace.split("Clearing\n")[1:]
        trace = [x.split("\n")[0:2] for x in trace if len(x) > 1]
        trace = [x for x in trace if len(x[0])>1]
        vmexit = [int(x[0].split(": ")[1]) for x in trace]
        vmgexit = [int(x[1].split(": ")[1]) for x in trace]

        #Monitor stats
        try:
            with open(f"results/wallet_traces_{alloc}/wallet_profiling-{b}") as f:
                trace = f.read()
        except:
            print(f"Trace missing results/wallet_traces_{alloc}/wallet_profiling-{b}")
            return
       
        trace = trace.split("[SVSM] ERROR: Stat\n")[1:]
        trace = [x.split("\n")[0:3] for x in trace]
        pvalidate = [int(x[0].split(": ")[2]) for x in trace]
        page_fault = [int(x[1].split(": ")[2]) for x in trace]
        cow = [int(x[2].split(": ")[2]) for x in trace]
        if len(vmexit) != len(pvalidate):
            print("Missing results/Benchmark might have failed?")
            return
        for i in range(len(vmexit)):
            r.write(f"{b},{alloc},{vmexit[i]},{vmgexit[i]},{pvalidate[i]},{page_fault[i]},{cow[i]}\n")

with open("trace_result.csv", "w") as f:
    f.write("bench,prealloc,vmexit,vmgexit,pvalidate,page_fault,cow\n")
    for b in BENCHMARKS:
        parse_benchmark(b,f)
