#!/usr/bin/env bash
set -e
groupadd -g $1 users || true
useradd -l -u $2 -g users user || true
su -c "./build.sh $3" user
