#include "attest.h"
#include "attest_microbenchmark.h"
#include "vmpl.h"

#define PAGE_SIZE 4096

// Function to allocate the struct for the function attestation arguments
static void allocate_function_struct(function_data** fn){
    uint8_t* buf = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
    if (buf == NULL) {
        printf("Can't allocate function struct for the attestation\n");
        *fn = NULL;
        return;
    }
    for(int i = 0; i < PAGE_SIZE; i++) {
        buf[i] = 0;
    }
    *fn = (void*)buf;
}

void measure_monitor_cold() {
  uint8_t* att_buffer = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
  if (att_buffer == NULL) {
      printf("Can't allocate monitor attestation report buffer\n");
      return;
  }
  for(int i = 0; i < PAGE_SIZE; i++){
      att_buffer[i] = 0;
  }

  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = monitorAttestation;
  call.attestation_target = att_buffer;
  uint64_t ret = ioctl(con, VMPL_WR, &call);

  struct attestation_report* report = (struct attestation_report*)att_buffer;
  free(att_buffer);
  
  return;
}

void measure_monitor_hot() {
  uint8_t* att_buffer = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
  if (att_buffer == NULL) {
      printf("Can't allocate monitor attestation report buffer\n");
      return;
  }
  for(int i = 0; i < PAGE_SIZE; i++){
      att_buffer[i] = 0;
  }

  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = monitorAttestationCold;
  call.attestation_target = att_buffer;
  uint64_t ret = ioctl(con, VMPL_WR, &call);

  struct attestation_report* report = (struct attestation_report*)att_buffer;
  free(att_buffer);
  
  return;
}

void prepare_measure_zygote_cold(const uint64_t trusted_process_id) {
  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = prepareZygoteAttestationCold;
  call.monitor_attestation.process_id = trusted_process_id;
  uint64_t ret = ioctl(con, VMPL_WR, &call);
  
  return;
}

void measure_zygote_cold(const uint64_t trusted_process_id) {
  uint8_t* att_buffer = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
  if (att_buffer == NULL) {
      printf("Can't allocate zygote attestation report buffer\n");
      return;
  }
  for(int i = 0; i < PAGE_SIZE; i++){
      att_buffer[i] = 0;
  }

  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = zygoteAttestationCold;
  call.monitor_attestation.process_id = trusted_process_id;
  call.attestation_target = att_buffer;
  uint64_t ret = ioctl(con, VMPL_WR, &call);

  struct attestation_report* report = (struct attestation_report*)att_buffer;
  free(att_buffer);
  
  return;
}

void measure_zygote_hot(const uint64_t trusted_process_id) {
  uint8_t* att_buffer = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
  if (att_buffer == NULL) {
      printf("Can't allocate zygote attestation report buffer\n");
      return;
  }
  for(int i = 0; i < PAGE_SIZE; i++){
      att_buffer[i] = 0;
  }

  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = zygoteAttestation;
  call.monitor_attestation.process_id = trusted_process_id;
  call.attestation_target = att_buffer;
  uint64_t ret = ioctl(con, VMPL_WR, &call);

  struct attestation_report* report = (struct attestation_report*)att_buffer;
  free(att_buffer);
  
  return;
}

void prepare_measure_trustlet_cold(const uint64_t trusted_process_id) {
  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = prepareTrustletAttestationCold;
  call.monitor_attestation.process_id = trusted_process_id;
  uint64_t ret = ioctl(con, VMPL_WR, &call);
  
  return;
}

void measure_trustlet_cold(const uint64_t trusted_process_id) {
  uint8_t* att_buffer = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
  if (att_buffer == NULL) {
      printf("Can't allocate trustlet attestation report buffer\n");
      return;
  }
  for(int i = 0; i < PAGE_SIZE; i++){
      att_buffer[i] = 0;
  }

  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = trustletAttestationCold;
  call.monitor_attestation.process_id = trusted_process_id;
  call.attestation_target = att_buffer;
  uint64_t ret = ioctl(con, VMPL_WR, &call);

  struct attestation_report* report = (struct attestation_report*)att_buffer;
  free(att_buffer);
  
  return;
}


void measure_trustlet_hot(const uint64_t trusted_process_id) {
  uint8_t* att_buffer = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
  if (att_buffer == NULL) {
      printf("Can't allocate trustlet attestation report buffer\n");
      return;
  }
  for(int i = 0; i < PAGE_SIZE; i++){
      att_buffer[i] = 0;
  }

  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = trustletAttestation;
  call.monitor_attestation.process_id = trusted_process_id;
  call.attestation_target = att_buffer;
  uint64_t ret = ioctl(con, VMPL_WR, &call);

  struct attestation_report* report = (struct attestation_report*)att_buffer;
  free(att_buffer);
  
  return;
}

void measure_function(const uint64_t trusted_process_id, const char* input, const uint64_t input_len, 
                        const char* output, const uint64_t output_len)
{
  uint8_t* att_buffer = aligned_alloc(PAGE_SIZE, PAGE_SIZE);
  if (att_buffer == NULL) {
    printf("Can't allocate function attestation report buffer\n");
    return;
  }
  for(int i = 0; i < PAGE_SIZE; i++){
      att_buffer[i] = 0;
  }

  function_data* function_data_ptr;
  allocate_function_struct(&function_data_ptr);
  function_data_ptr->trustletId = trusted_process_id;
  function_data_ptr->fnInput = (void*)input;
  function_data_ptr->fnInputSize = input_len;
  function_data_ptr->fnOutput = (void*)output;
  function_data_ptr->fnOutputSize = output_len;

  struct monitor_call call;
  call.type = attest;
  call.monitor_attestation.type = functionAttestation;
  call.monitor_attestation.process_id = trusted_process_id;
  call.monitor_attestation.function_data_ptr = (void*)function_data_ptr;
  call.attestation_target = att_buffer;
  uint64_t ret = ioctl(con, VMPL_WR, &call);

  struct attestation_report* report = (struct attestation_report*)att_buffer;
  free(att_buffer);

  return;
}
