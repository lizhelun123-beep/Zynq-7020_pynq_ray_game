#ifndef BGR_REVERSE_H
#define BGR_REVERSE_H
#include <stddef.h>
#include <stdint.h>
#ifdef _WIN32
#define DEMO_API __declspec(dllexport)
#else
#define DEMO_API
#endif
#ifdef __cplusplus
extern "C" {
#endif
DEMO_API uint32_t bgr_abi_version(void);
/* CPU buffers only. Return 0 success, -1 invalid geometry/span, -2 overlap. */
DEMO_API int bgr_reverse(const uint8_t *src, size_t src_size, size_t src_stride,
                        uint8_t *dst, size_t dst_size, size_t dst_stride,
                        size_t width, size_t height);
#ifdef __cplusplus
}
#endif
#endif
