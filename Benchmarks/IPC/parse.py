
import pandas as pd
import numpy as np
import sys

df = pd.read_csv("results.csv",header=None, names=["type","size","time"])
result = df.groupby("size")["time"].agg(["mean", "std"]).reset_index()

output = f"{sys.argv[1]}:\nsize,mean,std\n"
for _, row in result.iterrows():
    output += f"{int(row['size'])},{row['mean']},{row['std']}\n"

print(output)
