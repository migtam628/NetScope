/* Command dispatcher: turns a request frame into a reply frame.
 *
 * Portable: all hardware access goes through ns_hal_t, so the same code runs
 * on the STM32 and in the host test.  Payload layouts are little-endian and
 * mirror the unpack_* functions in netscope/hal/coproc.py.
 *
 * Safety rules enforced here (not left to the caller):
 *   - the relay enters TEST only if every pin is below NS_UNSAFE_MV;
 *   - WIREMAP and XTALK are refused unless the relay is in TEST;
 *   - any refused or failed scan returns the relay to LINK;
 *   - the relay is never moved while a PoE load is applied.
 */
#ifndef NS_DISPATCH_H
#define NS_DISPATCH_H
#include "proto.h"
#include "wiremap.h"

#define NS_FW_MAJOR 0
#define NS_FW_MINOR 1
#define NS_FW_PATCH 0

typedef struct {
    uint8_t percent;
    uint16_t mv;
    int16_t ma;
    int16_t temp_dc;      /* 0.1 C */
    uint8_t health;
    uint16_t cycles;
    uint8_t flags;        /* bit0 charging */
    uint16_t minutes;     /* 0xFFFF = unknown */
} ns_battery_t;

typedef struct {
    ns_afe_t afe;                                                   /* wiremap front end */
    void (*vscan)(void *ctx, int32_t *alt_a_mv, int32_t *alt_b_mv, uint8_t *flags);
    int (*xtalk)(void *ctx, int16_t cdb[6]);                        /* may be NULL */
    void (*relay_set)(void *ctx, uint8_t mode);
    void (*poe_status)(void *ctx, int32_t *mv, uint8_t *kind, uint8_t *cls, uint8_t *flags);
    /* returns NS_OK, NS_ERR_OVERTEMP or NS_ERR_POE_UNPOWERED */
    int (*poe_load)(void *ctx, uint32_t mw, uint16_t ms, int32_t *mv, int32_t *ma,
                    int32_t *noload_mv, uint8_t *held);
    int (*poe_load_active)(void *ctx);
    void (*battery)(void *ctx, ns_battery_t *b);
    void (*led)(void *ctx, uint8_t index, uint8_t state);
    void (*buzz)(void *ctx, uint16_t hz, uint16_t ms);
    void *ctx;
} ns_hal_t;

typedef struct {
    const ns_hal_t *hal;
    uint8_t relay;        /* current relay mode; NS_RELAY_LINK after ns_dispatch_init */
} ns_dispatch_t;

void ns_dispatch_init(ns_dispatch_t *d, const ns_hal_t *hal);

/* Handles one request and writes one complete reply frame to out
 * (>= NS_MAX_FRAME bytes).  Returns the reply length. */
size_t ns_dispatch(ns_dispatch_t *d, const ns_frame_t *req, uint8_t *out);

#endif
