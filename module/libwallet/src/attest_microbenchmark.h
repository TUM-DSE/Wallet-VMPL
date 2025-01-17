#ifndef ATTEST_MICROBENCHMARK_H_
#define ATTEST_MICROBENCHMARK_H_

/* Attestation measurements API */

void measure_monitor_cold();
void measure_monitor_hot();
void prepare_measure_zygote_cold(const uint64_t trusted_process_id);
void measure_zygote_cold(const uint64_t trusted_process_id);
void measure_zygote_hot(const uint64_t trusted_process_id);
void prepare_measure_trustlet_cold(const uint64_t trusted_process_id);
void measure_trustlet_cold(const uint64_t trusted_process_id);
void measure_trustlet_hot(const uint64_t trusted_process_id);
void measure_function(const uint64_t trusted_process_id, const char* input, const uint64_t input_len, 
                        const char* output, const uint64_t output_len);

/* End of Attestation measurements API */

#endif // ATTEST_MICROBENCHMARK_H_
