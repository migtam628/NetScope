CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O2

test: test_host test_dispatch
	./test_host
	./test_dispatch

test_host: proto.c wiremap.c test_host.c proto.h wiremap.h
	$(CC) $(CFLAGS) -o $@ proto.c wiremap.c test_host.c

test_dispatch: proto.c wiremap.c dispatch.c test_dispatch.c proto.h wiremap.h dispatch.h
	$(CC) $(CFLAGS) -o $@ proto.c wiremap.c dispatch.c test_dispatch.c

clean:
	rm -f test_host test_dispatch
.PHONY: test clean
