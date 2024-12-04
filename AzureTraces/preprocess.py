# Interestingly, this script is not needed as the original data set is already sorted in order of start_timestamp (which is not included but
# can be calculated as start_timestamp = end_timestamp - duration). This script is kept here for reference.

import csv
import numpy as np

# Read the CSV file
input_file = 'AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt'
with open(input_file, 'r') as csvfile:
    reader = csv.reader(csvfile, delimiter=',')
    header = np.array(next(reader), dtype=object)  # Read the header row
    rows = [np.array(row, dtype=object) for row in reader]


orig_rows = rows.copy()

header.resize(5)
header[4] = "start_timestamp"
print(header)
print(rows[0])
print(rows[0][2])

for row in rows:
    row.resize(5, refcheck = False)
    row[4] = str(float(row[2]) - float(row[3]))

#for i in range(len(rows)):
#    row = rows[i]
#    orig_row = orig_rows[i]
#    if(row[0] != orig_row[0]):
#        print("Column 0 not matching after resize")
#        exit(-1)
#    if(row[1] != orig_row[1]):
#        print("Column 1 not matching after resize")
#        exit(-1)
#    if(row[2] != orig_row[2]):
#        print("Column 2 not matching after resize")
#        exit(-1)
#    if(row[3] != orig_row[3]):
#        print("Column 3 not matching after resize")
#        exit(-1)

print(rows[0])
# Calculate start_timestamp for each row and store it as a tuple (start_timestamp, row)
#rows_with_start_timestamps = [(float(row[2]) - float(row[3]), row) for row in rows]
#for row in rows:

# Sort rows by start_timestamp
sorted_rows = sorted(rows, key=lambda x: float(x[4]))

#print('------------------')
#print(rows[57684])
#print(rows[57685])
#print(rows[57686])
#print('------------------')
#print(sorted_rows[57684])
#print(sorted_rows[57685])
#print(sorted_rows[57686])
#print('------------------')

#for i in range(len(rows)):
#    row = rows[i]
#    sorted_row = sorted_rows[i]
#    if(row[0] != sorted_row[0]):
#        print("Column 0 not matching after resize")
#        exit(-1)
#    if(row[1] != sorted_row[1]):
#        print("Column 1 not matching after resize")
#        exit(-1)
#    if(row[2] != sorted_row[2]):
#        print("Column 2 not matching after resize")
#        print(i)
#        print(row)
#        print(sorted_row)
#        exit(-1)
#    if(row[3] != sorted_row[3]):
#        print("Column 3 not matching after resize")
#        exit(-1)


# Extract sorted rows
#sorted_rows = [x[1] for x in sorted_rows_with_start_timestamps]

# Write the sorted rows to a new CSV file
output_file = 'AzureFunctionsInvocationTraceForTwoWeeksJan2021_preprocessed.csv'
with open(output_file, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(header)
    writer.writerows(sorted_rows)

print(f'Sorted CSV saved as {output_file}')
