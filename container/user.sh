#!/usr/bin/env bash

groupadd -g $1 users
useradd -l -u $2 -g users user
su -c "./build.sh $3" user
