#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/mman.h>
#include <semaphore.h>

struct TimeData {
    struct timeval start;
    struct timeval end;
};

struct TimeData* time_data;

void get_time() {
    struct timeval* start = &time_data->start;
    struct timeval* end = &time_data->end;

    long time = (end->tv_sec - start->tv_sec) * 1000000 + (end->tv_usec - start->tv_usec);
    printf("%ld\n", time);
}

void ipc_pipe(char* buffer, int buffer_size) {
    int fd[2];

    if (pipe(fd) == -1) {
        perror("pipe failed");
        exit(1);
    }

    pid_t pid = fork();
    if (pid < 0) {
        perror("fork failed");
        exit(1);
    }

    if (pid == 0) {  // Receiver
        close(fd[1]);

        read(fd[0], buffer, buffer_size);
        gettimeofday(&time_data->end, NULL);
        get_time();
        close(fd[0]);
    } else {  // Sender
        close(fd[0]);

        gettimeofday(&time_data->start, NULL);
        write(fd[1], buffer, buffer_size);
        close(fd[1]);
        wait(NULL);
    }
}

void ipc_socket(char* buffer, int buffer_size) {
    int sock_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sock_fd == -1) {
        perror("socket failed");
        exit(1);
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(struct sockaddr_un));
    addr.sun_family = AF_UNIX;
    strcpy(addr.sun_path, "\0socket");

    if (bind(sock_fd, (struct sockaddr *) &addr, sizeof(struct sockaddr_un)) == -1) {
        perror("bind failed");
        close(sock_fd);
        exit(1);
    }

    if (listen(sock_fd, 5) == -1) {
        perror("listen failed");
        close(sock_fd);
        exit(1);
    }

    pid_t pid = fork();
    if (pid < 0) {
        perror("fork failed");
        exit(1);
    }

    if (pid == 0) {  // Receiver
        int client_fd = accept(sock_fd, NULL, NULL);
        if (client_fd == -1) {
            perror("accept failed");
            exit(1);
        }

        read(client_fd, buffer, buffer_size);
        gettimeofday(&time_data->end, NULL);
        get_time();
        close(client_fd);
    } else {  // Sender
        sleep(1);  // Ensure the server is ready before sending
        int client_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (client_fd == -1) {
            perror("client socket failed");
            exit(1);
        }

        if (connect(client_fd, (struct sockaddr *)&addr, sizeof(struct sockaddr_un)) == -1) {
            perror("connect failed");
            exit(1);
        }

        gettimeofday(&time_data->start, NULL);
        write(client_fd, buffer, buffer_size);
        close(client_fd);
        wait(NULL);
    }
}

void ipc_shm(char* buffer, int buffer_size) {

    char* shm_ptr = mmap(NULL, sizeof(sem_t) + buffer_size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (shm_ptr == MAP_FAILED) {
        perror("mmap failed");
        exit(1);
    }

    sem_t* sem = (sem_t*) shm_ptr;
    if (sem_init(sem, 1, 0) == -1) {
        perror("sem_init failed");
        exit(1);
    }

    char* buffer_ptr = shm_ptr + sizeof(sem_t);

    pid_t pid = fork();
    if (pid < 0) {
        perror("fork failed");
        exit(1);
    }

    if (pid == 0) {  // Receiver
        sem_wait(sem);
        memcpy(buffer, buffer_ptr, buffer_size);
        gettimeofday(&time_data->end, NULL);
        get_time();
        sem_destroy(sem);
    } else {  // Sender
        gettimeofday(&time_data->start, NULL);
        memcpy(buffer_ptr, buffer, buffer_size);
        sem_post(sem);
        wait(NULL);
    }
}

int main(int argc, char* argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <pipe|socket|shm> <buffer_size_in_bytes>\n", argv[0]);
        return 1;
    }

    int buffer_size = atoi(argv[2]);

    char* buffer = malloc(buffer_size);
    if (buffer == NULL) {
        perror("malloc failed");
        return 1;
    }

    memset(buffer, 'A', buffer_size - 1);
    buffer[buffer_size - 1] = '\0';

    time_data = mmap(NULL, sizeof(struct TimeData), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (time_data == MAP_FAILED) {
        perror("mmap failed");
        exit(1);
    }

    if (strcmp(argv[1], "pipe") == 0) {
        ipc_pipe(buffer, buffer_size);
    } else if (strcmp(argv[1], "socket") == 0) {
        ipc_socket(buffer, buffer_size);
    } else if (strcmp(argv[1], "shm") == 0) {
        ipc_shm(buffer, buffer_size);
    } else {
        fprintf(stderr, "Invalid option.\n");
        return 1;
    }

    free(buffer);

    return 0;
}
