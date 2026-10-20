// Isolated VS companion. Do not overwrite shared engine vertex record #303.
// Installed only around a qualified draw; TEX5/6/7 are repurposed.
row_major float4x4 World : register(c0);
row_major float4x4 ViewProj : register(c8);
float3 Eye : register(c16);
float3 Light : register(c17);
row_major float4x4 ShadowProjection : register(c18);
float4 ShadowParams : register(c22);
float4 FogParams : register(c23);
float4 Tint : register(c24);
float4 BlackenDistance : register(c25);
float4 LightmapTransform : register(c26);
float2 UvOffset : register(c27);
bool Blacken : register(b0);
struct Input { float4 pos:POSITION; float3 n:NORMAL; float3 t:BINORMAL; float4 uv:TEXCOORD0; };
struct Output {
 float4 pos:POSITION; float4 weights:COLOR0; float4 tint:COLOR1;
 float4 uv:TEXCOORD0; float4 lightFake:TEXCOORD1; float4 oldView:TEXCOORD2;
 float3 world:TEXCOORD5; float3 eye:TEXCOORD6; float3 sunWorld:TEXCOORD7;
 float2 lm:TEXCOORD8;
 float4 shadow:TEXCOORD3;
};
Output main(Input a) {
 Output o;
 float4 w=mul(float4(a.pos.xyz,1),World);
 o.pos=mul(w,ViewProj); o.world=w.xyz; o.eye=Eye-w.xyz; o.sunWorld=Light;
 float3 b=cross(a.n,a.t)*sign(a.pos.w);
 float3 localL=mul((float3x3)World,Light);
 float3 localV=mul((float3x3)World,normalize(o.eye));
 o.lightFake=float4(normalize(float3(dot(a.t,localL),dot(b,localL),dot(a.n,localL))),0);
 o.oldView=float4(normalize(float3(dot(a.t,localV),dot(b,localV),dot(a.n,localV))),1-min(length(o.eye)/60,1));
 o.uv=float4(a.uv.xy*a.pos.w+UvOffset,a.uv.zw*a.pos.w);
 o.weights=float4(0,min(saturate(o.pos.z*FogParams.x+FogParams.y),FogParams.z),saturate((o.pos.z-ShadowParams.x)*ShadowParams.y),1);
 o.shadow=mul(float4(w.xyz,1),ShadowProjection);
 float2 black=saturate(o.pos.z*BlackenDistance.xz+BlackenDistance.yw);
 [branch] if (Blacken) o.tint=Tint*min(black.x,black.y); else o.tint=Tint;
 o.lm=w.xz*LightmapTransform.zw+LightmapTransform.xy;
 return o;
}

