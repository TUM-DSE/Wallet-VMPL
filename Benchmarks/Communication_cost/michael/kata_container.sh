#!/usr/bin/env bash

sizes=(64 128 256 512 1024 2048 4096 8192 16384 32768 65536 131072 262144 524288 1048576 2097152)

mkdir -p result_kata/
rm result_kata/* || true

# make kata (NixOS compiled version fails to run in ubuntu)
docker run --rm -v "$(pwd)":/root ubuntu:24.04 bash -c "apt update && apt install -y --no-install-recommends make gcc libstdc++-13-dev && make -C root kata"

for i in "${sizes[@]}"
do
    echo "microseconds" >> result_kata/res-$i.txt

    for j in {1..10}
    do
        receiver=$(docker run -d --runtime kata-qemu -v "$(pwd)":/root ubuntu:24.04 /root/kata receive $i)
        sleep 3
        ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $receiver)
        sender=$(docker run -d --runtime kata-qemu -v "$(pwd)":/root ubuntu:24.04 /root/kata $ip $i)

        time1=$(docker logs -f $sender)
        echo $time1
        time2=$(docker logs -f $receiver)
        echo $time2

        docker container rm $receiver
        docker container rm $sender

        diff=$((time2 - time1))
        echo diff: $diff

        echo "$diff" >> result_kata/res-$i.txt
    done
done
