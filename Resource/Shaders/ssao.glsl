#version 430 core

#include "utility.glsl"
#include "scene_constants.glsl"
#include "quad.glsl"

uniform sampler2D texture_normal;
uniform sampler2D texture_depth;
uniform sampler2D texture_linear_depth;

#ifdef FRAGMENT_SHADER
in VERTEX_OUTPUT vs_output;
out vec4 fs_output;

const int uSampleKernelSize = 64;

void main() {
    vec2 texcoord = vs_output.texcoord.xy;
    vec2 random_coord = texcoord.xy * 10.001;
    float depth = texture(texture_linear_depth, texcoord).x;

    if(depth >= near_far.y)
    {
        fs_output = vec4(1.0);
        return;
    }

    vec4 clip_coord = vec4(texcoord * 2.0 - 1.0, 0.0, 1.0);
    vec4 view_ray = inv_view_origin * inv_perspective * clip_coord;
    view_ray.xyz = normalize(view_ray.xyz);
    vec3 world_pos = view_ray.xyz * depth;
    vec3 normal = texture(texture_normal, texcoord).xyz * 2.0 - 1.0;

    vec3 randomVec = normalize(vec3(rand(random_coord.xy * 0.5) * 2.0 - 1.0, rand(random_coord.xy * 3.14515) * 2.0 - 1.0, rand(random_coord.yx * 1.14) * 2.0 - 1.0));

    vec3 tangent   = normalize(randomVec - normal * dot(randomVec, normal));
    vec3 bitangent = cross(normal, tangent);
    mat3 tbn = mat3(tangent, normal, bitangent);

    float occlusion = 0.0;
    float uRadius = 0.2;
    for (int i = 0; i < uSampleKernelSize; ++i) {
        // get sample position:
        vec3 pos = tbn * normalize(vec3(rand(random_coord.xy * 0.75 + vec2(float(uSampleKernelSize) * 0.1)) * 2.0 - 1.0, rand(random_coord.yx * 5.7 + vec2(float(uSampleKernelSize) * 0.2)), rand(random_coord.yx * 0.9 + vec2(float(uSampleKernelSize) * 0.3)) * 2.0 - 1.0));
        pos = pos * uRadius * rand(random_coord.xy * 0.31 + vec2(float(uSampleKernelSize) * 0.3)) + world_pos;

        // project sample position:
        vec4 offset = vec4(pos, 1.0);
        offset = perspective * view_origin * offset;
        offset.xy /= offset.w;
        offset.xy = offset.xy * 0.5 + 0.5;

        // get sample depth:
        float sampleDepth = texture(texture_linear_depth, offset.xy).r;

        // range check & accumulate:
        float rangeCheck = abs(depth - sampleDepth) < uRadius ? 1.0 : 0.0;
        occlusion += (sampleDepth <= depth ? 1.0 : 0.0) * rangeCheck;
    }

    occlusion = 1.0 - occlusion / (float(uSampleKernelSize) - 1.0);
    fs_output.xyz = vec3(occlusion);
    fs_output.w = 1.0;

}
#endif // FRAGMENT_SHADER