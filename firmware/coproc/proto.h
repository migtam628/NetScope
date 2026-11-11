/* NetScope X1 coprocessor serial protocol.  Mirrors netscope/hal/coproc.py.
 *
 * Frame: 0x7E | LEN | CMD | SEQ | payload[LEN] | CRC16-CCITT(LEN..payload), big-endian
 */
#ifndef NS_PROTO_H
#define NS_PROTO_H
#include <stddef.h>
#include <stdint.h>

#define NS_SOF 0x7E
#define NS_MAX_PAYLOAD 255
#define NS_MAX_FRAME (NS_MAX_PAYLOAD + 6)

enum {
    NS_CMD_PING = 0x01, NS_CMD_VSCAN = 0x10, NS_CMD_WIREMAP = 0x11, NS_CMD_XTALK = 0x12,
    NS_CMD_RELAY = 0x13, NS_CMD_POE_STATUS = 0x20, NS_CMD_POE_LOAD = 0x21,
    NS_CMD_BATTERY = 0x30, NS_CMD_KEY = 0x40, NS_CMD_LED = 0x41, NS_CMD_BUZZ = 0x42,
    NS_CMD_ERROR = 0x7F
};
enum {
    NS_OK = 0, NS_ERR_BAD_CMD = 1, NS_ERR_BAD_LEN = 2, NS_ERR_UNSAFE_VOLTAGE = 3,
    NS_ERR_OVERTEMP = 4, NS_ERR_BUSY = 5, NS_ERR_POE_UNPOWERED = 6
};
enum { NS_RELAY_LINK = 0, NS_RELAY_TEST = 1, NS_RELAY_ISOLATE = 2 };

typedef struct {
    uint8_t cmd, seq, len;
    uint8_t payload[NS_MAX_PAYLOAD];
} ns_frame_t;

uint16_t ns_crc16(const uint8_t *data, size_t len);

/* Writes a frame into out (>= len + 6 bytes).  Returns bytes written. */
size_t ns_encode(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint8_t len, uint8_t *out);

/* Scans buf[0..*len) for one valid frame.  On success copies it to *f, removes
 * it and everything before it from buf, updates *len and returns 1.  Otherwise
 * discards bytes that cannot start a frame, keeps a possible partial frame and
 * returns 0. */
int ns_decode(uint8_t *buf, size_t *len, ns_frame_t *f);

#endif
