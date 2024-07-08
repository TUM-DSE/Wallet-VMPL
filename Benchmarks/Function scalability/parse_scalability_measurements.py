import re;

def start():
    f = open("measurements.txt", "r")
    tokens = f.read().split("[")

    fout = open("measurements_vm_kata.csv", "w")

    fout.write('Number of functions,Avg execution time\n')
    for token in tokens:
        if token == '':
            continue
     #   print("Token")
        nb_functions = int(re.findall(r'\d+', token.split(']')[0])[0])
     #   print(f"Looking at {nb_functions} functions")
        times = re.findall('real\s+[0-9]+m[0-9]*\.[0-9]+', token)
     #   print(f'Times: {times}')
        avg = 0
        for time in times:
            time = time[5::] #get rid of 'real'
    #        print(f'time: {time}')
            minutes = int(time.split('m')[0]) * 60 * 1000
            seconds = float(time.split('m')[1]) * 1000
            avg = avg + (minutes + seconds)/len(times)
     #       print(f'len time: {len(times)}')
     #   print(f'Avg: {avg}')
        fout.write(f'{nb_functions},{avg}\n')
            #print(f'Read {minutes} minutes and {seconds} milliseconds')


if __name__ == '__main__':
    start()

