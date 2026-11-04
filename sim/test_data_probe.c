/* Offline instrumentation only: use the delivered detector, adapter and solver. */
#include "vision_ps.h"
#include "ray_game.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    const size_t span = 1280U * 720U * 3U;
    unsigned char *frame;
    VisionDetection detections[VISION_MAX_DETECTIONS];
    VisionDetectionDiagnostics diagnostics;
    SceneObject objects[VISION_MAX_DETECTIONS];
    RayGameResult ray;
    RayPoint emitter, direction;
    FILE *input;
    int count, model_count, index, policy, status;
    size_t received;
    if (argc != 7) return 2;
    emitter.x = (float)atof(argv[2]); emitter.y = (float)atof(argv[3]);
    direction.x = (float)atof(argv[4]); direction.y = (float)atof(argv[5]);
    policy = atoi(argv[6]);
    frame = (unsigned char *)malloc(span);
    if (!frame) return 2;
    input = fopen(argv[1], "rb");
    if (!input) { free(frame); return 2; }
    received = fread(frame, 1, span, input);
    status = fgetc(input);
    fclose(input);
    if (received != span || status != EOF) { free(frame); return 2; }
    vision_set_real_scene_profile(VISION_PROFILE_RESTORED);
    count = vision_detect_bgr888(frame, 1280, 720, 3840,
                               detections, VISION_MAX_DETECTIONS);
    free(frame);
    if (count < 0) return 3;
    vision_get_detection_diagnostics(&diagnostics);
    printf("count=%d\n", count);
    for (index = 0; index < count; ++index) {
        const VisionDetection *item = &detections[index];
        printf("%s center=%d,%d angle=%d bbox=%d,%d,%d,%d "
               "axis=%.6f,%.6f size=%.6f,%.6f\n",
               vision_type_name(item->type), item->center_x, item->center_y,
               item->angle_deg, item->bbox_x, item->bbox_y, item->bbox_w,
               item->bbox_h, item->axis_x, item->axis_y, item->major_length,
               item->minor_width);
    }
    for (index = 0; index < 6; ++index)
        printf("DIAGNOSTIC %s candidates=%u geometry=%u markers=%u accepted=%u\n",
               vision_type_name((VisionType)index),
               diagnostics.component_candidates[index], diagnostics.geometry_pass[index],
               diagnostics.marker_pass[index], diagnostics.accepted[index]);
    printf("WALL_DIAGNOSTIC components=%u pairs=%u accepted=%u\n",
           diagnostics.wall_marker_components, diagnostics.wall_marker_pairs_tested,
           diagnostics.wall_marker_accepted);
    model_count = ray_game_scene_from_detections(detections, count, objects,
                                                VISION_MAX_DETECTIONS);
    if (model_count < 0) return 4;
    for (index = 0; index < model_count; ++index) {
        const SceneObject *item = &objects[index];
        printf("MODEL %s center=%.6f,%.6f axis=%.6f,%.6f size=%.6f,%.6f\n",
               vision_type_name(detections[index].type), item->center.x, item->center.y,
               item->axis.x, item->axis.y, item->length, item->width);
    }
    if (ray_game_trace_from_emitter_policy(objects, model_count, 1280, 720,
                                           emitter, direction, policy, &ray)) return 4;
    printf("OFFLINE_RAW_SCENE_RAY (no timed confirmation): "
           "segments=%d interactions=%d termination=%d\n",
           ray.segment_count, ray.interaction_count, (int)ray.termination);
    for (index = 0; index < ray.segment_count; ++index)
        printf("segment%d %.6f,%.6f -> %.6f,%.6f\n", index,
               ray.segments[index].start.x, ray.segments[index].start.y,
               ray.segments[index].end.x, ray.segments[index].end.y);
    for (index = 0; index < ray.hit_count; ++index)
        printf("HIT %d\n", (int)ray.hit_types[index]);
    return 0;
}
