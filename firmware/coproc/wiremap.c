#include "wiremap.h"
#include "proto.h"

static int32_t iabs32(int32_t v) { return v < 0 ? -v : v; }

int ns_wiremap_scan(const ns_afe_t *afe, uint32_t out[56])
{
    /* Safety gate: look before touching.  Sense is high-impedance. */
    for (int pin = 1; pin <= 8; pin++)
        if (iabs32(afe->pin_mv(afe->ctx, pin)) > NS_UNSAFE_MV)
            return NS_ERR_UNSAFE_VOLTAGE;

    int k = 0;
    for (int a = 1; a <= 8; a++) {
        for (int b = 1; b <= 8; b++) {
            if (a == b)
                continue;
            int tries = 0;
            for (;;) {
                int32_t va = iabs32(afe->pin_mv(afe->ctx, a));
                int32_t vb = iabs32(afe->pin_mv(afe->ctx, b));
                if (va > NS_UNSAFE_MV || vb > NS_UNSAFE_MV)
                    return NS_ERR_UNSAFE_VOLTAGE; /* power appeared mid-scan */
                if (va < NS_QUIET_MV && vb < NS_QUIET_MV)
                    break;
                if (++tries > NS_QUIET_RETRIES)
                    return NS_ERR_BUSY;
                afe->delay_ms(afe->ctx, 25);
            }
            out[k++] = afe->measure_ohms(afe->ctx, a, b);
        }
    }
    return NS_OK;
}
