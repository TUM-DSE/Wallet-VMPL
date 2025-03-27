import os

def get_directory_info(directory):
    total_size = 0
    file_count = 0

    for root, dirs, files in os.walk(directory):
        file_count += len(files)
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)
            else:
                print(f"not a file: {file_path}")

    return file_count, total_size

if __name__ == "__main__":
    directory = input("Path: ")
    if os.path.exists(directory) and os.path.isdir(directory):
        num_files, size_bytes = get_directory_info(directory)
        print(f"Number of files: {num_files}")
        print(f"Total size: {size_bytes} bytes")
    else:
        print("Invalid directory path.")
