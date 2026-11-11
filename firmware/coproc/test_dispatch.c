/* Host test for the command dispatcher.  The reply payloads asserted here are
 * the same byte strings firmware/tests/test_coproc_vectors.py decodes with the
 * Python unpackers, so the two sides cannot drift apart silently. */
#include "dispatch.h"
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

typedef struct {
    int32_t pin_mv[9];
    uint8_t relay;
    int relay_moves;
    int load_active;
    int load_rc;
    uint32_t load_mw; uint16_t load_ms;
    uint8_t led_i, led_s; uint16_t buzz_hz, buzz_ms;
} fake_t;

static int32_t f_pin(void *c, int pin) { return ((fake_t *)c)->pin_mv[pin]; }
static uint32_t f_ohms(void *c, int pos, int neg)
{
    (void)c;
    static const int A[4] = {1, 3, 4, 7}, K[4] = {2, 6, 5, 8};
    static const uint32_t R[4] = {1000, 2200, 4700, 47000};
    for (int i = 0; i < 4; i++) if (pos == A[i] && neg == K[i]) return R[i];
    return NS_OPEN;
}
static void f_delay(void *c, uint32_t ms) { (void)c; (void)ms; }
static void f_vscan(void *c, int32_t *a, int32_t *b, uint8_t *fl) { (void)c; *a = 4400; *b = -24100; *fl = 1; }
static int f_xtalk(void *c, int16_t o[6]) { (void)c; for (int i = 0; i < 6; i++) o[i] = (int16_t)(-4400 + 100 * i); return NS_OK; }
static void f_relay(void *c, uint8_t m) { fake_t *f = c; f->relay = m; f->relay_moves++; }
static void f_poe(void *c, int32_t *mv, uint8_t *k, uint8_t *cl, uint8_t *fl) { (void)c; *mv = 53400; *k = 1; *cl = 4; *fl = 0; }
static int f_load(void *c, uint32_t mw, uint16_t ms, int32_t *mv, int32_t *ma, int32_t *nl, uint8_t *held)
{
    fake_t *f = c; f->load_mw = mw; f->load_ms = ms;
    *mv = 51500; *ma = 388; *nl = 53400; *held = 1;
    return f->load_rc;
}
static int f_load_active(void *c) { return ((fake_t *)c)->load_active; }
static void f_batt(void *c, ns_battery_t *b)
{
    (void)c;
    b->percent = 78; b->mv = 3870; b->ma = -950; b->temp_dc = 315; b->health = 97;
    b->cycles = 41; b->flags = 0; b->minutes = 462;
}
static void f_led(void *c, uint8_t i, uint8_t s) { fake_t *f = c; f->led_i = i; f->led_s = s; }
static void f_buzz(void *c, uint16_t hz, uint16_t ms) { fake_t *f = c; f->buzz_hz = hz; f->buzz_ms = ms; }

static uint8_t out[NS_MAX_FRAME];
static ns_frame_t rep;

static int call(ns_dispatch_t *d, uint8_t cmd, const uint8_t *payload, uint8_t len)
{
    static uint8_t seq;
    ns_frame_t req;
    req.cmd = cmd; req.seq = ++seq; req.len = len;
    if (len) memcpy(req.payload, payload, len);
    size_t n = ns_dispatch(d, &req, out);
    size_t l = n;
    CHECK(ns_decode(out, &l, &rep) == 1 && l == 0);
    CHECK(rep.seq == seq);
    return rep.cmd == NS_CMD_ERROR ? -(int)rep.payload[0] : (int)rep.len;
}

static int payload_is(const char *hex)
{
    size_t n = strlen(hex) / 2;
    if (n != rep.len) return 0;
    for (size_t i = 0; i < n; i++) {
        unsigned v; sscanf(hex + 2 * i, "%2x", &v);
        if (rep.payload[i] != v) return 0;
    }
    return 1;
}

int main(void)
{
    fake_t f;
    memset(&f, 0, sizeof f);
    f.relay = 0xEE;
    ns_hal_t hal = {{f_pin, f_ohms, f_delay, &f}, f_vscan, f_xtalk, f_relay, f_poe, f_load,
                    f_load_active, f_batt, f_led, f_buzz, &f};
    ns_dispatch_t d;
    ns_dispatch_init(&d, &hal);
    CHECK(f.relay == NS_RELAY_LINK);                      /* safe state at start-up */

    CHECK(call(&d, NS_CMD_PING, NULL, 0) == 3 && payload_is("000100"));
    CHECK(call(&d, NS_CMD_VSCAN, NULL, 0) == 9 && payload_is("30110000dca1ffff01"));
    CHECK(call(&d, NS_CMD_POE_STATUS, NULL, 0) == 7 && payload_is("98d00000010400"));
    CHECK(call(&d, NS_CMD_BATTERY, NULL, 0) == 13 && payload_is("4e1e0f4afc3b0161290000ce01"));

    const uint8_t load[6] = {0x20, 0x4e, 0x00, 0x00, 0xd0, 0x07};   /* 20000 mW, 2000 ms */
    CHECK(call(&d, NS_CMD_POE_LOAD, load, 6) == 13 && payload_is("2cc900008401000098d0000001"));
    CHECK(f.load_mw == 20000 && f.load_ms == 2000);
    f.load_rc = NS_ERR_OVERTEMP;
    CHECK(call(&d, NS_CMD_POE_LOAD, load, 6) == -NS_ERR_OVERTEMP);
    f.load_rc = NS_OK;

    /* scans are refused until the relay is in TEST */
    CHECK(call(&d, NS_CMD_WIREMAP, NULL, 0) == -NS_ERR_BUSY);
    CHECK(call(&d, NS_CMD_XTALK, NULL, 0) == -NS_ERR_BUSY);

    uint8_t mode = NS_RELAY_TEST;
    CHECK(call(&d, NS_CMD_RELAY, &mode, 1) == 0 && f.relay == NS_RELAY_TEST);
    CHECK(call(&d, NS_CMD_POE_LOAD, load, 6) == -NS_ERR_BUSY);      /* no load with the AFE on the line */
    CHECK(call(&d, NS_CMD_WIREMAP, NULL, 0) == 224);
    CHECK(rep.payload[0] == 0xE8 && rep.payload[1] == 0x03);        /* 1 -> 2 = 1000 ohm */
    CHECK(rep.payload[4] == 0xFF && rep.payload[7] == 0xFF);        /* 1 -> 3 open */
    CHECK(call(&d, NS_CMD_XTALK, NULL, 0) == 12 && payload_is("d0ee34ef98effcef60f0c4f0"));

    /* voltage appears mid-session: scan refused and relay forced back to LINK */
    f.pin_mv[4] = 24100;
    CHECK(call(&d, NS_CMD_WIREMAP, NULL, 0) == -NS_ERR_UNSAFE_VOLTAGE);
    CHECK(f.relay == NS_RELAY_LINK && d.relay == NS_RELAY_LINK);
    CHECK(call(&d, NS_CMD_RELAY, &mode, 1) == -NS_ERR_UNSAFE_VOLTAGE && f.relay == NS_RELAY_LINK);
    f.pin_mv[4] = -48000;
    CHECK(call(&d, NS_CMD_RELAY, &mode, 1) == -NS_ERR_UNSAFE_VOLTAGE);
    f.pin_mv[4] = 0;

    /* relay never moves while a PoE load is applied */
    f.load_active = 1;
    int moves = f.relay_moves;
    CHECK(call(&d, NS_CMD_RELAY, &mode, 1) == -NS_ERR_BUSY && f.relay_moves == moves);
    f.load_active = 0;

    const uint8_t led[2] = {2, 1}, buzz[4] = {0xa0, 0x0f, 0x64, 0x00};
    CHECK(call(&d, NS_CMD_LED, led, 2) == 0 && f.led_i == 2 && f.led_s == 1);
    CHECK(call(&d, NS_CMD_BUZZ, buzz, 4) == 0 && f.buzz_hz == 4000 && f.buzz_ms == 100);

    /* malformed requests */
    uint8_t bad = 9;
    CHECK(call(&d, NS_CMD_RELAY, &bad, 1) == -NS_ERR_BAD_LEN);
    CHECK(call(&d, NS_CMD_PING, &bad, 1) == -NS_ERR_BAD_LEN);
    CHECK(call(&d, NS_CMD_POE_LOAD, load, 5) == -NS_ERR_BAD_LEN);
    CHECK(call(&d, 0x55, NULL, 0) == -NS_ERR_BAD_CMD);
    CHECK(call(&d, NS_CMD_KEY, NULL, 0) == -NS_ERR_BAD_CMD);        /* device-to-host only */

    hal.xtalk = NULL;                                               /* split-pair circuit not fitted */
    mode = NS_RELAY_TEST;
    CHECK(call(&d, NS_CMD_RELAY, &mode, 1) == 0);
    CHECK(call(&d, NS_CMD_XTALK, NULL, 0) == -NS_ERR_BAD_CMD);

    printf(failures ? "%d FAILED\n" : "coproc dispatch tests: all passed\n", failures);
    return failures != 0;
}
