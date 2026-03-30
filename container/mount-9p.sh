#!/bin/bash
# Retry-mount all 9p filesystems from /etc/fstab until they succeed.
# Virtio-9p devices may not be ready immediately at boot.

RETRY_DELAY=0.1
MAX_RETRIES=100

# Collect 9p mount points from fstab
mapfile -t MOUNTS < <(awk '$3 == "9p" { print $2 }' /etc/fstab)

if [ ${#MOUNTS[@]} -eq 0 ]; then
    echo "mount-9p: no 9p entries in fstab"
    exit 0
fi

for (( i=1; i<=MAX_RETRIES; i++ )); do
    all_ok=true
    for mp in "${MOUNTS[@]}"; do
        if mountpoint -q "$mp" 2>/dev/null; then
            continue
        fi
        mount "$mp" 2>/dev/null && echo "mount-9p: mounted $mp" || all_ok=false
    done
    if $all_ok; then
        echo "mount-9p: all 9p filesystems mounted"
        exit 0
    fi
    sleep "$RETRY_DELAY"
done

echo "mount-9p: gave up after $MAX_RETRIES retries, still unmounted:"
for mp in "${MOUNTS[@]}"; do
    mountpoint -q "$mp" 2>/dev/null || echo "  $mp"
done
exit 1
