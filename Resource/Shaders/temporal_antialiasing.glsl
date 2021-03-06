//=================================================================================================
//
//  MSAA Filtering 2.0 Sample
//  by MJP
//  http://mynameismjp.wordpress.com/
//
//  All code licensed under the MIT license
//
//=================================================================================================

#include "scene_constants.glsl"
#include "quad.glsl"

//----------- CONSTANTS -------------//

const float Pi = 3.141592f;
const int FilterTypes_Box = 0;
const int FilterTypes_Triangle = 1;
const int FilterTypes_Gaussian = 2;
const int FilterTypes_BlackmanHarris = 3;
const int FilterTypes_Smoothstep = 4;
const int FilterTypes_BSpline = 5;
const int FilterTypes_CatmullRom = 6;
const int FilterTypes_Mitchell = 7;
const int FilterTypes_GeneralizedCubic = 8;
const int FilterTypes_Sinc = 9;

const int ClampModes_Disabled = 0;
const int ClampModes_RGB_Clamp = 1;
const int ClampModes_RGB_Clip = 2;
const int ClampModes_Variance_Clip = 3;

const int DilationModes_CenterAverage = 0;
const int DilationModes_DilateNearestDepth = 1;
const int DilationModes_DilateGreatestVelocity = 2;

//---------- INPUT -----------------//

const int ResolveFilterType = FilterTypes_BSpline;
const float ResolveFilterDiameter = 2.0;  // 0.0 ~ 6.0
const float GaussianSigma = 0.25;   // 0.0 ~ 1.0
const float CubicB = 0.33;  // 0.0 ~ 1.0
const float CubicC = 0.33;  // 0.0 ~ 1.0
const float ExposureFilterOffset = 2.0;     // -16.0 ~ 16.0
const float TemporalAABlendFactor = 0.9;    // 0.0 ~ 1.0
const int NeighborhoodClampMode = ClampModes_Variance_Clip;
const float VarianceClipGamma = 1.5;    // 0.0 ~ 2.0
const float LowFreqWeight = 0.25;   // 0.0 ~ 100.0
const float HiFreqWeight = 0.85;    // 0.0 ~ 100.0
const int DilationMode = DilationModes_DilateGreatestVelocity;
const int ReprojectionFilter = FilterTypes_CatmullRom;
const float ExposureScale = 0.0;    // -16.0 ~ 16.0
const float ManualExposure = -2.5;  // -10.0 ~ 10.0

const bool UseStandardReprojection = false;
const bool UseTemporalColorWeighting = false;
const bool InverseLuminanceFiltering = true;
const bool UseExposureFiltering = false;

uniform sampler2D texture_prev;
uniform sampler2D texture_input;
uniform sampler2D texture_velocity;
uniform sampler2D texture_depth;


// All filtering functions assume that 'x' is normalized to [0, 1], where 1 == FilteRadius
float FilterBox(in float x)
{
    return x <= 1.0 ? 1.0 : 0.0;
}

float FilterTriangle(in float x)
{
    return clamp(1.0f - x, 0.0, 1.0);
}

float FilterGaussian(in float x)
{
    const float sigma = GaussianSigma;
    const float g = 1.0f / sqrt(2.0f * 3.14159f * sigma * sigma);
    return (g * exp(-(x * x) / (2 * sigma * sigma)));
}

float FilterCubic(in float x, in float B, in float C)
{
    float y = 0.0f;
    float x2 = x * x;
    float x3 = x * x * x;
    if(x < 1)
        y = (12 - 9 * B - 6 * C) * x3 + (-18 + 12 * B + 6 * C) * x2 + (6 - 2 * B);
    else if (x <= 2)
        y = (-B - 6 * C) * x3 + (6 * B + 30 * C) * x2 + (-12 * B - 48 * C) * x + (8 * B + 24 * C);
    return y / 6.0f;
}

float FilterSinc(in float x, in float filterRadius)
{
    float s;
    x *= filterRadius * 2.0f;
    if(x < 0.001f)
        s = 1.0f;
    else
        s = sin(x * Pi) / (x * Pi);
    return s;
}

float FilterBlackmanHarris(in float x)
{
    x = 1.0f - x;
    const float a0 = 0.35875f;
    const float a1 = 0.48829f;
    const float a2 = 0.14128f;
    const float a3 = 0.01168f;
    return clamp(a0 - a1 * cos(Pi * x) + a2 * cos(2 * Pi * x) - a3 * cos(3 * Pi * x), 0.0, 1.0);
}

float FilterSmoothstep(in float x)
{
    return 1.0f - smoothstep(0.0f, 1.0f, x);
}

float Filter(in float x, in int filterType, in float filterRadius, in bool rescaleCubic)
{
    // Cubic filters naturually work in a [-2, 2] domain. For the resolve case we
    // want to rescale the filter so that it works in [-1, 1] instead
    float cubicX = rescaleCubic ? x * 2.0f : x;

    if(filterType == FilterTypes_Box)
        return FilterBox(x);
    else if(filterType == FilterTypes_Triangle)
        return FilterTriangle(x);
    else if(filterType == FilterTypes_Gaussian)
        return FilterGaussian(x);
    else if(filterType == FilterTypes_BlackmanHarris)
        return FilterBlackmanHarris(x);
    else if(filterType == FilterTypes_Smoothstep)
        return FilterSmoothstep(x);
    else if(filterType == FilterTypes_BSpline)
        return FilterCubic(cubicX, 1.0, 0.0f);
    else if(filterType == FilterTypes_CatmullRom)
        return FilterCubic(cubicX, 0, 0.5f);
    else if(filterType == FilterTypes_Mitchell)
        return FilterCubic(cubicX, 1 / 3.0f, 1 / 3.0f);
    else if(filterType == FilterTypes_GeneralizedCubic)
        return FilterCubic(cubicX, CubicB, CubicC);
    else if(filterType == FilterTypes_Sinc)
        return FilterSinc(x, filterRadius);
    else
        return 1.0f;
}

float Luminance(in vec3 clr)
{
    return dot(clr, vec3(0.299f, 0.587f, 0.114f));
}

// From "Temporal Reprojection Anti-Aliasing"
// https://github.com/playdeadgames/temporal
vec3 ClipAABB(vec3 aabbMin, vec3 aabbMax, vec3 prevSample, vec3 avg)
{
    #if 1
        // note: only clips towards aabb center (but fast!)
        vec3 p_clip = 0.5 * (aabbMax + aabbMin);
        vec3 e_clip = 0.5 * (aabbMax - aabbMin);

        vec3 v_clip = prevSample - p_clip;
        vec3 v_unit = v_clip.xyz / e_clip;
        vec3 a_unit = abs(v_unit);
        float ma_unit = max(a_unit.x, max(a_unit.y, a_unit.z));

        if (ma_unit > 1.0)
            return p_clip + v_clip / ma_unit;
        else
            return prevSample;// point inside aabb
    #else
        vec3 r = prevSample - avg;
        vec3 rmax = aabbMax - avg.xyz;
        vec3 rmin = aabbMin - avg.xyz;

        const float eps = 0.000001f;

        if (r.x > rmax.x + eps)
            r *= (rmax.x / r.x);
        if (r.y > rmax.y + eps)
            r *= (rmax.y / r.y);
        if (r.z > rmax.z + eps)
            r *= (rmax.z / r.z);

        if (r.x < rmin.x - eps)
            r *= (rmin.x / r.x);
        if (r.y < rmin.y - eps)
            r *= (rmin.y / r.y);
        if (r.z < rmin.z - eps)
            r *= (rmin.z / r.z);

        return avg + r;
    #endif
}

vec3 Reproject(vec2 texCoord)
{
    vec2 inv_velocity_tex_size = 1.0 / textureSize(texture_velocity, 0).xy;
    vec2 velocity = vec2(0.0, 0.0);

    if(DilationMode == DilationModes_CenterAverage)
    {
        velocity += texture(texture_velocity, texCoord).xy;
    }
    else if(DilationMode == DilationModes_DilateNearestDepth)
    {
        vec2 inv_depth_tex_size = 1.0 / textureSize(texture_depth, 0).xy;
        float closestDepth = 10.0f;
        for(int vy = -1; vy <= 1; ++vy)
        {
            for(int vx = -1; vx <= 1; ++vx)
            {
                vec2 neighborVelocity = texture(texture_velocity, texCoord + vec2(vx, vy) * inv_velocity_tex_size).xy;
                float neighborDepth = texture(texture_depth, texCoord + vec2(vx, vy) * inv_depth_tex_size).x;
                if(neighborDepth < closestDepth)
                {
                    velocity = neighborVelocity;
                    closestDepth = neighborDepth;
                }
            }
        }
    }
    else if(DilationMode == DilationModes_DilateGreatestVelocity)
    {
        float greatestVelocity = -1.0f;
        for(int vy = -1; vy <= 1; ++vy)
        {
            for(int vx = -1; vx <= 1; ++vx)
            {
                vec2 neighborVelocity = texture(texture_velocity, texCoord + vec2(vx, vy) * inv_velocity_tex_size).xy;
                float neighborVelocityMag = dot(neighborVelocity, neighborVelocity).x;
                if(dot(neighborVelocity, neighborVelocity) > greatestVelocity)
                {
                    velocity = neighborVelocity;
                    greatestVelocity = neighborVelocityMag;
                }
            }
        }
    }

    vec2 texture_prev_size = textureSize(texture_prev, 0).xy;
    vec2 reprojectedUV = texCoord - velocity;
    vec2 reprojectedPos = reprojectedUV * texture_prev_size;

    if(UseStandardReprojection)
    {
        return texture(texture_prev, reprojectedUV).xyz;
    }

    vec3 sum = vec3(0.0f);
    float totalWeight = 0.0f;

    for(int ty = -1; ty <= 2; ++ty)
    {
        for(int tx = -1; tx <= 2; ++tx)
        {
            vec2 samplePos = floor(reprojectedPos + vec2(tx, ty)) + 0.5f;
            vec3 reprojectedSample = texture(texture_prev, samplePos / texture_prev_size).xyz;

            vec2 sampleDist = abs(samplePos - reprojectedPos);
            float filterWeight = Filter(sampleDist.x, ReprojectionFilter, 1.0f, false) *
                                 Filter(sampleDist.y, ReprojectionFilter, 1.0f, false);

            if(InverseLuminanceFiltering)
            {
                float sampleLum = Luminance(reprojectedSample);
                if(UseExposureFiltering)
                {
                    sampleLum *= exp2(ManualExposure - ExposureScale + ExposureFilterOffset);
                }
                filterWeight /= (1.0f + sampleLum);
            }

            sum += reprojectedSample * filterWeight;
            totalWeight += filterWeight;
        }
    }
    return max(sum / totalWeight, 0.0f);
}

vec4 ResolvePS(vec2 texCoord, vec2 pixelPos)
{
    vec3 sum = vec3(0.0f);
    float totalWeight = 0.0f;

    vec3 clrMin = vec3(99999999.0f);
    vec3 clrMax = vec3(-99999999.0f);

    vec3 m1 = vec3(0.0f);
    vec3 m2 = vec3(0.0f);
    float mWeight = 0.0f;

    vec2 texture_input_size = textureSize(texture_input, 0).xy;

    const float filterRadius = ResolveFilterDiameter / 2.0f;

    for(int y = -1; y <= 1; ++y)
    {
        for(int x = -1; x <= 1; ++x)
        {
            vec2 sampleOffset = vec2(x, y);
            vec2 sampleUV = texCoord + sampleOffset / texture_input_size;
            sampleUV = clamp(sampleUV, 0.0, 1.0);

            vec3 sample_color = texture(texture_input, sampleUV).xyz;

            vec2 sampleDist = abs(sampleOffset) / (ResolveFilterDiameter / 2.0f);

            float weight = Filter(sampleDist.x, ResolveFilterType, filterRadius, true) *
                           Filter(sampleDist.y, ResolveFilterType, filterRadius, true);
            clrMin = min(clrMin, sample_color);
            clrMax = max(clrMax, sample_color);

            if(InverseLuminanceFiltering)
            {
                float sampleLum = Luminance(sample_color);
                if(UseExposureFiltering)
                {
                    sampleLum *= exp2(ManualExposure - ExposureScale + ExposureFilterOffset);
                }
                weight /= (1.0f + sampleLum);
            }

            sum += sample_color * weight;
            totalWeight += weight;

            m1 += sample_color;
            m2 += sample_color * sample_color;
            mWeight += 1.0f;
        }
    }

    vec4 result = texture(texture_input, texCoord);

    vec3 currColor = result.xyz;
    vec3 prevColor = Reproject(texCoord);

    if(NeighborhoodClampMode == ClampModes_RGB_Clamp)
    {
        prevColor = clamp(prevColor, clrMin, clrMax);
    }
    else if(NeighborhoodClampMode == ClampModes_RGB_Clip)
    {
        prevColor = ClipAABB(clrMin, clrMax, prevColor, m1 / mWeight);
    }
    else if(NeighborhoodClampMode == ClampModes_Variance_Clip)
    {
        vec3 mu = m1 / mWeight;
        vec3 sigma = sqrt(abs(m2 / mWeight - mu * mu));
        vec3 minc = mu - VarianceClipGamma * sigma;
        vec3 maxc = mu + VarianceClipGamma * sigma;
        prevColor = ClipAABB(minc, maxc, prevColor, mu);
    }

    vec3 weightA = vec3(clamp(1.0f - TemporalAABlendFactor, 0.0, 1.0));
    vec3 weightB = vec3(clamp(TemporalAABlendFactor, 0.0, 1.0));

    if(UseTemporalColorWeighting)
    {
        vec3 temporalWeight = clamp(abs(clrMax - clrMin) / currColor, 0.0, 1.0);
        weightB = clamp(mix(vec3(LowFreqWeight), vec3(HiFreqWeight), temporalWeight), 0.0, 1.0);
        weightA = 1.0f - weightB;
    }

    if(InverseLuminanceFiltering)
    {
        weightA /= (1.0f + Luminance(currColor));
        weightB /= (1.0f + Luminance(prevColor));
    }

    result.xyz = (currColor * weightA + prevColor * weightB) / (weightA + weightB);

    return result;
}


#ifdef GL_FRAGMENT_SHADER
layout (location = 0) in VERTEX_OUTPUT vs_output;
layout (location = 0) out vec4 fs_output;

void main() {
    fs_output = ResolvePS(vs_output.tex_coord.xy, gl_FragCoord.xy);
}
#endif // GL_FRAGMENT_SHADER