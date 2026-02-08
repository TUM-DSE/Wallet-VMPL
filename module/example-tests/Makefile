TRUSTLET_SRCS := $(wildcard *_trustlet.c)
TRUSTLETS := $(TRUSTLET_SRCS:.c=)
RUNNER_SRCS := $(wildcard *_run.py)
RUNNERS := $(RUNNER_SRCS:.py=)

all: $(TRUSTLETS)

run_tests:
	@for runner in $(RUNNERS); do \
		echo "Running $$runner..."; \
		make $$runner; \
	done
	# make -C ../../ trustlet_test

$(RUNNERS): %: %.py
	make -C ../../ ssh_with_command SSH_COMMAND="cd module/example-tests && python3 $<"

$(TRUSTLETS): %: %.c
	gcc -I../../runtime/client/ -o $@ $<

simple_slick_fs: $(TRUSTLETS)
	mkdir -p ../../runtime/filesystem/simple/fs/lib/
	rm -rf ../../runtime/filesystem/simple/fs_out/
	rm -rf ../../runtime/filesystem/simple/fs/lib/*
	cp $(TRUSTLETS) ../../runtime/filesystem/simple/fs/lib/
	cd ../../runtime/filesystem/simple/; ./create.sh

clean:
	rm -f $(TRUSTLETS)

.PHONY: all clean $(RUNNERS)
