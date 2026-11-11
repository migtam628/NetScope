CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O2

test: test_host
	./test_host

test_host: proto.c wiremap.c test_host.c proto.h wiremap.h
	$(CC) $(CFLAGS) -o $@ proto.c wiremap.c test_host.c

clean:
	rm -f test_host
.PHONY: test clean
