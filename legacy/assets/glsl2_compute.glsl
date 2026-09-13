// TD GLSL parameters required by this shader:
// camera/projection:
//   uMapLng, uMapLat, uMapZoom, uZoomAdd
//   uMapW, uMapH, uPixelW, uPixelH
// data/options:
//   uNysInputMode, uNysMaxInfluences, uNysFastMercator, uNysRevealZoom
// field:
//   uMagRadius, uMagAttract, uMagRepel, uMagTwist
//   uMagMorph, uMagLift, uMagSink, uMagZoomSpread
//
// If a TD custom parameter row is accidentally named as an OP path, delete it
// and recreate it with the exact uniform name above. In the current parameter
// set, the row after uMagAttract should be uMagRepel.

uniform float uMapLng;
uniform float uMapLat;
uniform float uMapZoom;
uniform float uZoomAdd;

uniform float uMapW;
uniform float uMapH;
uniform float uPixelW;
uniform float uPixelH;

// 0: input1 P.x/y are lng/lat. 1: input1 P.x/y are already map-space tx/ty.
uniform float uNysInputMode;

// 0 or below means use all points in input1.
uniform float uNysMaxInfluences;

// 0: exact Mercator. 1: fast local Mercator approximation around map center.
uniform float uNysFastMercator;

// Zoom at which individual places begin to separate.
uniform float uNysRevealZoom;

// Magnetic field radius in map-space units.
uniform float uMagRadius;

// Radial pull toward each pin core.
uniform float uMagAttract;

// Radial push around the outer field.
uniform float uMagRepel;

// Rotational swirl around each pin, like a field line torsion.
uniform float uMagTwist;

// Global XY morph strength. This is the main "world rearrangement" amount.
uniform float uMagMorph;

// Z lift of active field areas.
uniform float uMagLift;

// Z sinking of non-field areas.
uniform float uMagSink;

// Low-zoom field expansion. Higher values make zoomed-out views more dramatic.
uniform float uMagZoomSpread;

const float TILE_SIZE = 256.0;
const float PI = 3.141592653589793;

vec2 mercator(float lng, float lat, float zoom) {
    float world = TILE_SIZE * pow(2.0, zoom);

    float x = (lng + 180.0) / 360.0 * world;

    lat = clamp(lat, -85.05112878, 85.05112878);
    float latRad = radians(lat);

    float y = (
        1.0 - log(tan(latRad) + 1.0 / cos(latRad)) / PI
    ) * 0.5 * world;

    return vec2(x, y);
}

vec2 lngLatToMapExact(float lng, float lat, float zoom, vec2 centerPx) {
    vec2 objPx = mercator(lng, lat, zoom);
    vec2 dpx = objPx - centerPx;

    float tx = dpx.x / uPixelW * uMapW;
    float ty = -dpx.y / uPixelH * uMapH;

    return vec2(tx, ty);
}

vec2 lngLatToMapFast(float lng, float lat, float zoom) {
    float world = TILE_SIZE * pow(2.0, zoom);

    float dx = (lng - uMapLng) / 360.0 * world;

    float centerLat = clamp(uMapLat, -85.05112878, 85.05112878);
    float centerLatRad = radians(centerLat);
    float mercatorScale = max(cos(centerLatRad), 0.01);
    float dy = -(lat - uMapLat) * world / (360.0 * mercatorScale);

    float tx = dx / uPixelW * uMapW;
    float ty = -dy / uPixelH * uMapH;

    return vec2(tx, ty);
}

vec2 influenceCenter(vec3 geo, float zoom, vec2 centerPx) {
    if(uNysInputMode > 0.5) {
        return geo.xy;
    }

    if(uNysFastMercator > 0.5) {
        return lngLatToMapFast(geo.x, geo.y, zoom);
    }

    return lngLatToMapExact(geo.x, geo.y, zoom, centerPx);
}

float hash11(float n) {
    return fract(sin(n) * 43758.5453123);
}

float stableSeed(vec3 geo) {
    return dot(geo.xyz, vec3(12.9898, 78.233, 37.719));
}

float sat(float v) {
    return clamp(v, 0.0, 1.0);
}

void main() {
    const uint id = TDIndex();

    vec3 p = TDIn_P();

    float zoom = uMapZoom + uZoomAdd;
    float revealZoom = uNysRevealZoom > 0.01 ? uNysRevealZoom : 12.28;

    float globalView = 1.0 - smoothstep(3.0, 7.0, zoom);
    float clusterView = smoothstep(4.5, 10.0, zoom) * (1.0 - smoothstep(11.5, 14.5, zoom));
    float localView = smoothstep(9.5, revealZoom + 1.5, zoom);

    vec2 centerPx = mercator(uMapLng, uMapLat, zoom);

    uint n = TDInputNumPoints(1);
    uint maxInfluences = n;
    if(uNysMaxInfluences > 0.5) {
        maxInfluences = min(n, uint(floor(uNysMaxInfluences)));
    }

    float baseRadius = max(uMagRadius, 0.0001);
    float spread = max(uMagZoomSpread, 0.0);
    float radius = baseRadius * mix(1.0 + spread * 1.65, 0.42, localView);
    radius = max(radius, 0.018);

    vec2 totalMove = vec2(0.0);
    float field = 0.0;
    float core = 0.0;

    for(uint i = 0u; i < maxInfluences; i++) {
        vec3 geo = TDIn_P(1, i);
        float strength = geo.z > 0.00001 ? geo.z : 1.0;

        float fi = stableSeed(geo);
        float rRand = mix(0.78, 1.34, hash11(fi * 17.31));
        float localRadius = radius * rRand;

        vec2 c = influenceCenter(geo, zoom, centerPx);
        vec2 toPin = c - p.xy;
        float d2 = dot(toPin, toPin);
        float d = sqrt(max(d2, 0.0000001));

        float m = 1.0 - smoothstep(0.0, localRadius, d);
        float wide = 1.0 - smoothstep(0.0, localRadius * mix(3.4, 1.85, localView), d);
        float halo = 1.0 - smoothstep(localRadius * 0.38, localRadius * 2.75, d);

        float fieldActive = mix(wide * 0.62, max(m, halo * 0.52), localView) * strength;
        field += fieldActive;
        core = max(core, m * strength);

        vec2 dirToPin = toPin / d;
        vec2 tangent = vec2(-dirToPin.y, dirToPin.x);

        float swirlSign = hash11(fi * 5.71) > 0.5 ? 1.0 : -1.0;
        float ring = wide * (1.0 - smoothstep(0.36, 0.92, m));
        float gravity = (m * 0.72 + halo * 0.22) * localView;
        float pressure = ring * (0.35 + globalView * 0.55);

        vec2 pullMove = dirToPin * gravity * max(uMagAttract, 0.35);
        vec2 pushMove = -dirToPin * pressure * max(uMagRepel, 0.0);
        vec2 twistMove = tangent * ring * uMagTwist * swirlSign * mix(0.7, 1.8, sat(clusterView + localView));

        totalMove += (pullMove + pushMove + twistMove) * fieldActive;
    }

    field = sat(field);
    core = sat(core);

    float background = 1.0 - field;
    float morph = max(uMagMorph, 0.0);

    vec2 magneticMove = totalMove * morph * mix(0.055, 0.19, localView);

    float maxMove = mix(0.035, 0.16, localView);
    float moveLen = length(magneticMove);
    if(moveLen > maxMove) {
        magneticMove = magneticMove / moveLen * maxMove;
    }

    p.xy += magneticMove;

    float lift = pow(core, mix(0.5, 1.15, localView)) * max(uMagLift, 0.0) * mix(0.75, 2.2, localView);
    float sink = -background * max(uMagSink, 0.0) * mix(0.35, 1.35, localView);
    sink -= field * (1.0 - core) * max(uMagSink, 0.0) * 0.45 * clusterView;

    p.z += lift + sink;

    mask[id] = clamp(field, 0.0, 1.0);
    P[id] = p;
}
