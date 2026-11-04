#include "bgr_reverse.h"

uint32_t bgr_abi_version(void) { return 1; }

static int span(size_t row, size_t stride, size_t height, size_t size, size_t *out)
{
    if (stride < row || height - 1 > (SIZE_MAX - row) / stride) return -1;
    *out = (height - 1) * stride + row;
    return *out > size ? -1 : 0;
}

int bgr_reverse(const uint8_t *src, size_t src_size, size_t src_stride,
                uint8_t *dst, size_t dst_size, size_t dst_stride,
                size_t width, size_t height)
{
    size_t row, src_span, dst_span, y, x;
    uintptr_t a = (uintptr_t)src, b = (uintptr_t)dst;
    if (!src || !dst || !width || !height || width > SIZE_MAX / 3) return -1;
    row = width * 3;
    if (span(row, src_stride, height, src_size, &src_span) ||
        span(row, dst_stride, height, dst_size, &dst_span)) return -1;
    if (src_span > UINTPTR_MAX - a || dst_span > UINTPTR_MAX - b) return -1;
    if (a < b + dst_span && b < a + src_span) return -2;
    for (y = 0; y < height; ++y) {
        for (x = 0; x < width; ++x) {
            dst[y * dst_stride + x * 3] = src[y * src_stride + x * 3 + 2];
            dst[y * dst_stride + x * 3 + 1] = src[y * src_stride + x * 3 + 1];
            dst[y * dst_stride + x * 3 + 2] = src[y * src_stride + x * 3];
        }
    }
    return 0;
}
