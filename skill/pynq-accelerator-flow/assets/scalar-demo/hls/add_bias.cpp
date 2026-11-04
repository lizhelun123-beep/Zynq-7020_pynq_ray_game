#include <stdint.h>

void add_bias(uint32_t x, uint32_t bias, uint32_t *y) {
#pragma HLS INTERFACE s_axilite port=x bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=bias bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=y bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=return bundle=control
    *y = x + bias;
}
