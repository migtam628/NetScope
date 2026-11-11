/* Host unit test for the portable coprocessor core.  `make test`.
 * Vectors match firmware/tests/test_api_reports.py. */
#include "proto.h"
#include "wiremap.h"
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

/* Fake cable: straight-through onto an RT-1 #1, optional injected voltage. */
typedef struct { int32_t mv[9]; int noisy_reads; uint32_t slept; } fake_t;
static const int ANODE[4] = {1, 3, 4, 7}, CATHODE[4] = {2, 6, 5, 8};
static const uint32_t OHMS[4] = {1000, 2200, 4700, 10000};

static int32_t f_mv(void *c, int pin)
{
    fake_t *f = c;
    if (f->noisy_reads > 0) { f->noisy_reads--; return 4400; }
    return f->mv[pin];
}
static uint32_t f_ohms(void *c, int pos, int neg)
{
    (void)c;
    for (int i = 0; i < 4; i++)
        if (pos == ANODE[i] && neg == CATHODE[i])
            return OHMS[i] + 6;
    return NS_OPEN;
}
static void f_delay(void *c, uint32_t ms) { ((fake_t *)c)->slept += ms; }

int main(void)
{
    uint8_t buf[NS_MAX_FRAME * 2];
    ns_frame_t fr;

    CHECK(ns_crc16((const uint8_t *)"123456789", 9) == 0x29B1);

    size_t n = ns_encode(NS_CMD_PING, 1, NULL, 0, buf);
    CHECK(n == 6 && buf[0] == 0x7E && buf[1] == 0 && buf[2] == 0x01 && buf[3] == 1);

    uint8_t mode = NS_RELAY_TEST;
    uint8_t frame[16];
    size_t flen = ns_encode(NS_CMD_RELAY, 7, &mode, 1, frame);
    CHECK(flen == 7 && memcmp(frame, "\x7e\x01\x13\x07\x01", 5) == 0);

    /* noise (including a false SOF with a huge length) + frame + start of next */
    const uint8_t noise[] = {0x00, 0x7E, 0xFF, 0x10};
    size_t len = 0;
    memcpy(buf, noise, sizeof noise); len += sizeof noise;
    memcpy(buf + len, frame, flen); len += flen;
    buf[len++] = 0x7E;
    CHECK(ns_decode(buf, &len, &fr) == 1);
    CHECK(fr.cmd == NS_CMD_RELAY && fr.seq == 7 && fr.len == 1 && fr.payload[0] == NS_RELAY_TEST);
    CHECK(len == 1 && buf[0] == 0x7E);          /* partial next frame is kept */
    CHECK(ns_decode(buf, &len, &fr) == 0 && len == 1);

    memcpy(buf, frame, flen); len = flen - 1;   /* truncated */
    CHECK(ns_decode(buf, &len, &fr) == 0 && len == flen - 1);
    memcpy(buf, frame, flen); buf[4] ^= 0xFF; len = flen; /* corrupt */
    CHECK(ns_decode(buf, &len, &fr) == 0);

    /* wiremap scan */
    fake_t fake;
    memset(&fake, 0, sizeof fake);
    ns_afe_t afe = {f_mv, f_ohms, f_delay, &fake};
    uint32_t m[56];
    CHECK(ns_wiremap_scan(&afe, m) == NS_OK);
    CHECK(m[0] == 1006);                         /* 1 -> 2 */
    CHECK(m[7] == NS_OPEN);                      /* 2 -> 1 (diode reverse) */
    int hits = 0;
    for (int i = 0; i < 56; i++) hits += m[i] != NS_OPEN;
    CHECK(hits == 4);

    fake.mv[4] = 24100;                          /* passive PoE on pin 4 */
    CHECK(ns_wiremap_scan(&afe, m) == NS_ERR_UNSAFE_VOLTAGE);
    fake.mv[4] = -48000;
    CHECK(ns_wiremap_scan(&afe, m) == NS_ERR_UNSAFE_VOLTAGE);
    fake.mv[4] = 0;

    fake.noisy_reads = 12; fake.slept = 0;       /* PSE pulse outlasts the 8-read gate */
    CHECK(ns_wiremap_scan(&afe, m) == NS_OK && fake.slept > 0);
    fake.noisy_reads = 1000000;                  /* never quiet */
    CHECK(ns_wiremap_scan(&afe, m) == NS_ERR_BUSY);

    printf(failures ? "%d FAILED\n" : "coproc host tests: all passed\n", failures);
    return failures != 0;
}
