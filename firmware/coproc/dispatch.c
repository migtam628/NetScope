#include "dispatch.h"
#include <string.h>

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

void ns_dispatch_init(ns_dispatch_t *d, const ns_hal_t *hal)
{
    d->hal = hal;
    d->relay = NS_RELAY_LINK;
    hal->relay_set(hal->ctx, NS_RELAY_LINK);
}

static size_t error(const ns_frame_t *req, uint8_t code, uint8_t *out)
{
    return ns_encode(NS_CMD_ERROR, req->seq, &code, 1, out);
}

static void force_link(ns_dispatch_t *d)
{
    d->relay = NS_RELAY_LINK;
    d->hal->relay_set(d->hal->ctx, NS_RELAY_LINK);
}

static int cable_is_safe(const ns_hal_t *h)
{
    for (int pin = 1; pin <= 8; pin++) {
        int32_t mv = h->afe.pin_mv(h->afe.ctx, pin);
        if (mv > NS_UNSAFE_MV || mv < -NS_UNSAFE_MV)
            return 0;
    }
    return 1;
}

size_t ns_dispatch(ns_dispatch_t *d, const ns_frame_t *req, uint8_t *out)
{
    const ns_hal_t *h = d->hal;
    uint8_t p[NS_MAX_PAYLOAD];

    switch (req->cmd) {
    case NS_CMD_PING:
        if (req->len != 0) return error(req, NS_ERR_BAD_LEN, out);
        p[0] = NS_FW_MAJOR; p[1] = NS_FW_MINOR; p[2] = NS_FW_PATCH;
        return ns_encode(req->cmd, req->seq, p, 3, out);

    case NS_CMD_VSCAN: {
        int32_t a, b; uint8_t flags;
        if (req->len != 0) return error(req, NS_ERR_BAD_LEN, out);
        h->vscan(h->ctx, &a, &b, &flags);
        put32(p, (uint32_t)a); put32(p + 4, (uint32_t)b); p[8] = flags;
        return ns_encode(req->cmd, req->seq, p, 9, out);
    }

    case NS_CMD_RELAY: {
        if (req->len != 1 || req->payload[0] > NS_RELAY_ISOLATE)
            return error(req, NS_ERR_BAD_LEN, out);
        uint8_t mode = req->payload[0];
        if (h->poe_load_active(h->ctx))
            return error(req, NS_ERR_BUSY, out);
        if (mode == NS_RELAY_TEST && !cable_is_safe(h)) {
            force_link(d);
            return error(req, NS_ERR_UNSAFE_VOLTAGE, out);
        }
        d->relay = mode;
        h->relay_set(h->ctx, mode);
        return ns_encode(req->cmd, req->seq, NULL, 0, out);
    }

    case NS_CMD_WIREMAP: {
        uint32_t m[56];
        if (req->len != 0) return error(req, NS_ERR_BAD_LEN, out);
        if (d->relay != NS_RELAY_TEST) return error(req, NS_ERR_BUSY, out);
        int rc = ns_wiremap_scan(&h->afe, m);
        if (rc != NS_OK) {
            force_link(d);
            return error(req, (uint8_t)rc, out);
        }
        for (int i = 0; i < 56; i++) put32(p + 4 * i, m[i]);
        return ns_encode(req->cmd, req->seq, p, 224, out);
    }

    case NS_CMD_XTALK: {
        int16_t c[6];
        if (req->len != 0) return error(req, NS_ERR_BAD_LEN, out);
        if (!h->xtalk) return error(req, NS_ERR_BAD_CMD, out);
        if (d->relay != NS_RELAY_TEST) return error(req, NS_ERR_BUSY, out);
        if (!cable_is_safe(h)) {
            force_link(d);
            return error(req, NS_ERR_UNSAFE_VOLTAGE, out);
        }
        int rc = h->xtalk(h->ctx, c);
        if (rc != NS_OK) return error(req, (uint8_t)rc, out);
        for (int i = 0; i < 6; i++) put16(p + 2 * i, (uint16_t)c[i]);
        return ns_encode(req->cmd, req->seq, p, 12, out);
    }

    case NS_CMD_POE_STATUS: {
        int32_t mv; uint8_t kind, cls, flags;
        if (req->len != 0) return error(req, NS_ERR_BAD_LEN, out);
        h->poe_status(h->ctx, &mv, &kind, &cls, &flags);
        put32(p, (uint32_t)mv); p[4] = kind; p[5] = cls; p[6] = flags;
        return ns_encode(req->cmd, req->seq, p, 7, out);
    }

    case NS_CMD_POE_LOAD: {
        int32_t mv = 0, ma = 0, noload = 0; uint8_t held = 0;
        if (req->len != 6) return error(req, NS_ERR_BAD_LEN, out);
        if (d->relay != NS_RELAY_LINK) return error(req, NS_ERR_BUSY, out);
        int rc = h->poe_load(h->ctx, get32(req->payload), get16(req->payload + 4),
                             &mv, &ma, &noload, &held);
        if (rc != NS_OK) return error(req, (uint8_t)rc, out);
        put32(p, (uint32_t)mv); put32(p + 4, (uint32_t)ma); put32(p + 8, (uint32_t)noload);
        p[12] = held;
        return ns_encode(req->cmd, req->seq, p, 13, out);
    }

    case NS_CMD_BATTERY: {
        ns_battery_t b;
        if (req->len != 0) return error(req, NS_ERR_BAD_LEN, out);
        h->battery(h->ctx, &b);
        p[0] = b.percent; put16(p + 1, b.mv); put16(p + 3, (uint16_t)b.ma);
        put16(p + 5, (uint16_t)b.temp_dc); p[7] = b.health; put16(p + 8, b.cycles);
        p[10] = b.flags; put16(p + 11, b.minutes);
        return ns_encode(req->cmd, req->seq, p, 13, out);
    }

    case NS_CMD_LED:
        if (req->len != 2) return error(req, NS_ERR_BAD_LEN, out);
        h->led(h->ctx, req->payload[0], req->payload[1]);
        return ns_encode(req->cmd, req->seq, NULL, 0, out);

    case NS_CMD_BUZZ:
        if (req->len != 4) return error(req, NS_ERR_BAD_LEN, out);
        h->buzz(h->ctx, get16(req->payload), get16(req->payload + 2));
        return ns_encode(req->cmd, req->seq, NULL, 0, out);

    default:
        return error(req, NS_ERR_BAD_CMD, out);
    }
}
