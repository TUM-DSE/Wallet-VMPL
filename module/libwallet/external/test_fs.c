#include <stdio.h>

int main() {
    FILE *fp;
    char path[] = "/external/test.txt";
    fp = fopen(path, "rw");
    if (fp == NULL) {
        printf("File not found: %s\n", path);
        return 1;
    }
    printf("File found\n");
    char buf[100];
    char *ptr = fgets(buf, 100, fp);
    if (ptr == NULL) {
        printf("Error reading file\n");
        return 1;
    }
    printf("File content: %s\n", buf);
    char buf2[] = "Hello from test_fs.c";
    int r = fputs(buf2, fp);
    if (r == 0) {
        printf("Error writing file\n");
        return 1;
    }
    r = fclose(fp);
    if (r != 0) {
        printf("Error closing file\n");
        return 1;
    }

    return 0;
}
