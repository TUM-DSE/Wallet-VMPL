#ifndef MEASUREMENT_UTILS_H
#define MEASUREMENT_UTILS_H

static inline uint64_t get_cycles() 
{
    unsigned int lo,hi;
    __asm__ __volatile__ ("rdtsc" : "=a" (lo), "=d" (hi));
    return ((uint64_t)hi << 32) | lo;
}
 
// NOTE: Function sleeps for 100 ms, don't call in performance sensitive code
static uint64_t get_CPU_freq() 
{
	uint64_t initial_cycles = get_cycles();
	// sleep in microseconds
	// sleep for 100 millisecond
	usleep(100000); 
	uint64_t final_cycles = get_cycles();

	// convert to frequency
	return (final_cycles - initial_cycles) * 10;
}

static inline float cycles_to_ms(uint64_t cycles, uint64_t CPU_freq)
{
	return (float) cycles/CPU_freq * 1000;
}

#endif
