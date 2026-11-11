#include "proto.h"
#include <string.h>

uint16_t ns_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

size_t ns_encode(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint8_t len, uint8_t *out)
{
    out[0] = NS_SOF;
    out[1] = len;
    out[2] = cmd;
    out[3] = seq;
    if (len)
        memcpy(&out[4], payload, len);
    uint16_t crc = ns_crc16(&out[1], (size_t)len + 3);
    out[4 + len] = (uint8_t)(crc >> 8);
    out[5 + len] = (uint8_t)crc;
    return (size_t)len + 6;
}

int ns_decode(uint8_t *buf, size_t *len, ns_frame_t *f)
{
    size_t n = *len;
    size_t keep = n; /* first position that might still become a frame */

    for (size_t i = 0; i < n; i++) {
        if (buf[i] != NS_SOF)
            continue;
        size_t rest = n - i;
        if (rest < 2 || rest < (size_t)buf[i + 1] + 6) {
            if (keep == n)
                keep = i;
            continue;
        }
        uint8_t plen = buf[i + 1];
        uint16_t crc = (uint16_t)((buf[i + 4 + plen] << 8) | buf[i + 5 + plen]);
        if (ns_crc16(&buf[i + 1], (size_t)plen + 3) != crc)
            continue;
        f->len = plen;
        f->cmd = buf[i + 2];
        f->seq = buf[i + 3];
        memcpy(f->payload, &buf[i + 4], plen);
        size_t used = i + plen + 6;
        memmove(buf, &buf[used], n - used);
        *len = n - used;
        return 1;
    }
    memmove(buf, &buf[keep], n - keep);
    *len = n - keep;
    return 0;
}
