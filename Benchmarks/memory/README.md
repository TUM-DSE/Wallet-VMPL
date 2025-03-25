## pvalidate/rmpajdust microbenchmark
- Build svsm with `bench_mem feature`
```
FEATURE=bench_mem make build_svsm
```
- Start bpftace in another terminal
```
sudo bpftrace a.bt
```
- Start the wallet
```
make run
```

## Result
- Total execution time (ns) to execute pvalidate/rmpadjust 256 pages
```
PVALIDATE: 6243294
RMPADJUST: 38784
```
