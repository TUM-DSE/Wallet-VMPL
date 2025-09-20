#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/time.h>

#define CHUNK_SIZE 1400 // UDP safe size
#define PORT 9000

void error_exit(const char *msg) {
    perror(msg);
    exit(1);
}

void udp_sender(const char *receiver_ip, int payload_size) {
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) error_exit("socket");

    int sndbuf_size = 8 * 1024 * 1024;  // 8 MB
    if (setsockopt(sockfd, SOL_SOCKET, SO_SNDBUF, &sndbuf_size, sizeof(sndbuf_size)) < 0) {
        perror("setsockopt SO_SNDBUF failed");
    }

    struct sockaddr_in receiver_addr;
    memset(&receiver_addr, 0, sizeof(receiver_addr));
    receiver_addr.sin_family = AF_INET;
    receiver_addr.sin_port = htons(PORT);
    if (inet_pton(AF_INET, receiver_ip, &receiver_addr.sin_addr) <= 0) error_exit("inet_pton");

    char *data = malloc(payload_size);
    if (!data) error_exit("malloc");
    memset(data, 'A', payload_size);

    struct timeval start_time;
    gettimeofday(&start_time, NULL);

    int chunks = (payload_size + CHUNK_SIZE - 1) / CHUNK_SIZE;
    for (int i = 0; i < chunks; i++) {
        int chunk_size = (i == chunks - 1) ? (payload_size % CHUNK_SIZE) : CHUNK_SIZE;
        if (chunk_size == 0) chunk_size = CHUNK_SIZE;
        if (sendto(sockfd, data + (i * CHUNK_SIZE), chunk_size, 0, (struct sockaddr *)&receiver_addr, sizeof(receiver_addr)) < 0)
            error_exit("sendto");
    }

    printf("%ld%06ld\n", start_time.tv_sec, start_time.tv_usec);
    close(sockfd);
    free(data);
}

void udp_receiver(int expected_size) {
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) error_exit("socket");

    int rcvbuf_size = 8 * 1024 * 1024;  // 8 MB
    if (setsockopt(sockfd, SOL_SOCKET, SO_RCVBUF, &rcvbuf_size, sizeof(rcvbuf_size)) < 0) {
        error_exit("setsockopt SO_RCVBUF failed");
    }

    struct sockaddr_in server_addr, client_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PORT);

    if (bind(sockfd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) error_exit("bind");

    char buffer[CHUNK_SIZE];
    socklen_t client_len = sizeof(client_addr);
    int received_bytes = 0;

    while (received_bytes < expected_size) {
        ssize_t received = recvfrom(sockfd, buffer, CHUNK_SIZE, 0, (struct sockaddr *)&client_addr, &client_len);
        if (received < 0) error_exit("recvfrom");
        received_bytes += received;
    }

    struct timeval end_time;
    gettimeofday(&end_time, NULL);
    printf("%ld%06ld\n", end_time.tv_sec, end_time.tv_usec);

    close(sockfd);
}

int main(int argc, char *argv[]) {
    if (argc == 3 && strcmp(argv[1], "receive") == 0) {
        udp_receiver(atoi(argv[2]));
    } else if (argc == 3) {
        udp_sender(argv[1], atoi(argv[2]));
    } else {
        fprintf(stderr, "Usage: %s <receiver_ip> <payload_size> | receive <expected_size>\n", argv[0]);
        exit(1);
    }
    return 0;
}
