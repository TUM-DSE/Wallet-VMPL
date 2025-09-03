FROM ubuntu:22.04
RUN apt update && apt upgrade -y
RUN apt install -y python3 python3-pip
RUN pip install bottle requests
COPY server.py /server.py
