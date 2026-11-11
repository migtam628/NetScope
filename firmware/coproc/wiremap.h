/* DC wiremap scan sequencing.  Hardware access goes through ns_afe_t so the
 * same code runs on the STM32 and in the host unit test. */
#ifndef NS_WIREMAP_H
#define NS_WIREMAP_H
#include <stdint.h>

#define NS_OPEN 0xFFFFFFFFu
/* Any pin above this (either polarity) means external power on the cable:
 * the scan is refused and the relays stay in LINK (isolated) position. */
#define NS_UNSAFE_MV 12000
/* A pin must be quieter than this before it is driven (a PSE's detection
 * pulses come and go; we measure in the gaps). */
#define NS_QUIET_MV 300
#define NS_QUIET_RETRIES 40

typedef struct {
    int32_t (*pin_mv)(void *ctx, int pin);               /* pin 1..8, high-Z sense   */
    uint32_t (*measure_ohms)(void *ctx, int pos, int neg); /* diode-compensated      */
    void (*delay_ms)(void *ctx, uint32_t ms);
    void *ctx;
} ns_afe_t;

/* Fills out[56] in the order a=1..8, b=1..8, a!=b (a driven positive).
 * Returns NS_OK, NS_ERR_UNSAFE_VOLTAGE or NS_ERR_BUSY (line never went quiet). */
int ns_wiremap_scan(const ns_afe_t *afe, uint32_t out[56]);

#endif
