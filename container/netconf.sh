#!/usr/bin/env bash
sub=$(expr $(id -u) - 1000)
YAMLIN=./container/99_config.yaml.in
YAMLOUT=./container/99_config.yaml

if [ $sub -ge 1000 ]; then
    sub=$(expr ${sub} - 1000)
    Addr="10.10.${sub}.10/24"
    Route="10.10.${sub}.1"
else
   Addr="192.168.${sub}.10/24"
   Route="192.168.${sub}.1"

fi
cp ${YAMLIN} ${YAMLOUT}
yq -i -y '.network.ethernets.enp0s2.addresses[0] = "'${Addr}'"' ${YAMLOUT} > /dev/null
yq -i -y '.network.ethernets.enp0s3.addresses[0] = "'${Addr}'"' ${YAMLOUT} > /dev/null

yq -i -y '.network.ethernets.enp0s2.routes[0].via = "'${Route}'"' ${YAMLOUT} > /dev/null
yq -i -y '.network.ethernets.enp0s3.routes[0].via = "'${Route}'"' ${YAMLOUT} > /dev/null

