#include <stdint.h>

void add_bias(uint32_t x, uint32_t bias, uint32_t *y);

int main() {
    const uint32_t values[][2] = {{0, 0}, {3, 4}, {0xffffffffu, 1}, {0x80000000u, 0x80000000u}};
    for (unsigned i = 0; i < sizeof(values) / sizeof(values[0]); ++i) {
        uint32_t y = 0;
        add_bias(values[i][0], values[i][1], &y);
        if (y != uint32_t(values[i][0] + values[i][1])) return 1;
    }
    return 0;
}
