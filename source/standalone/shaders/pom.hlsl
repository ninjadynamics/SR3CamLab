// Ultimate Race Lab -- opt-in opaque relief shader.
// Paired draw-scoped replacement; see ../POM.md.
// c10 repurposes gf3ReflCol as (depth_u, depth_v, edge_fade_uv).
// Normal RGB + linear height A in s1. Height 1 = reference surface, 0 = recessed.
#ifndef POM_STEPS
#define POM_STEPS 32
#endif
float3 Ambient : register(c0);
float3 Sun : register(c1);
float BumpScale : register(c3);
float4 Fog : register(c4);
float3 Relief : register(c10);
float Exposure : register(c31);
float4 Controls : register(c30); // depth multiplier, enabled, reserved
float4 ShadowParams : register(c12);
sampler2D Albedo : register(s0);
sampler2D NormalHeight : register(s1);
sampler2D Lightmap : register(s3);
sampler2D DynamicShadow : register(s4);
sampler2D StaticShadow : register(s5);
struct Input {
 float4 weights : COLOR0; float4 tint : COLOR1;
 float4 uv : TEXCOORD0; float4 lightFake : TEXCOORD1;
 float4 oldView : TEXCOORD2;
 float3 world : TEXCOORD5; float3 eye : TEXCOORD6;
 float3 sunWorld : TEXCOORD7;
 float4 shadow:TEXCOORD3; float2 lm:TEXCOORD8;
};
// Explicit LOD is computed once; ray samples avoid repeated gradient setup.
float Height(float2 uv, float lod) {return 1-tex2Dlod(NormalHeight,float4(uv,0,lod)).a;}
float2 Trace(float2 uv, float3 v, float lod, float scale) {
#if POM_STEPS == 0
 return uv;
#else
 float2 ray=v.xy/max(v.z,0.08)*Relief.xy*scale;
 // Spend samples on visible map detail, not empty resolution. Keep a larger
 // budget for long grazing rays; binary refinement and interpolation stabilize edges.
 float texels=length(ray*Controls.zw)*exp2(-lod);
 float steps=clamp(8+texels*.65,8,48);
 float dz=1/steps;float2 delta=ray*dz;
 float2 p=uv;float z=0;float h=Height(p,lod);float previous=h;
 if(h<=0.0001)return uv;
 [loop] for(int i=0;i<48;++i){
  if(z>=h || z>=1)break;
  previous=h;p-=delta;z+=dz;h=Height(p,lod);
 }
 float2 lo=p+delta,hi=p;float zlo=z-dz,zhi=z;
 float hlo=previous,hhi=h;
 [unroll] for(int j=0;j<2;++j){
  float2 mid=(lo+hi)*.5;float zm=(zlo+zhi)*.5;float hm=Height(mid,lod);
  if(zm<hm){lo=mid;zlo=zm;hlo=hm;}else{hi=mid;zhi=zm;hhi=hm;}
 }
 float above=max(0,hlo-zlo),below=max(0,zhi-hhi);
 return lerp(lo,hi,saturate(above/max(above+below,0.000001)));
#endif
}
float4 main(Input a) : COLOR0 {
 // Derivatives are evaluated before any divergent ray-march flow.
 float2 gx=ddx(a.uv.xy), gy=ddy(a.uv.xy);
 float2 dx=gx*Controls.zw,dy=gy*Controls.zw;
 float lod=max(0,.5*log2(max(max(dot(dx,dx),dot(dy,dy)),0.000001)));
 float3 px=ddx(a.world), py=ddy(a.world);
 float det=gx.x*gy.y-gx.y*gy.x;
 float valid=step(0.0000000001,abs(det));
 float inv=valid/(abs(det)>0.0000000001?det:1);
 float3 t=(px*gy.y-py*gx.y)*inv;
 float3 b=(py*gx.x-px*gy.x)*inv;
 float3 v=normalize(a.eye);
 float3 n=normalize(cross(px,py)+float3(0,0,0.00000001));
 n*=dot(n,v)<0?-1:1;
 t=normalize(t+float3(0.00000001,0,0));
 b=normalize(b-t*dot(b,t)+float3(0,0.00000001,0));
 float3 viewTS=float3(dot(v,t),dot(v,b),abs(dot(v,n)));
 // oldView.w falls from 1 at eye to 0 at 60 world units in the original VS.
 // Fade by projected texel footprint, not the original shader's 60-unit
 // specular-distance channel. Keep relief through useful grazing views.
 float distanceFade=1-smoothstep(0.015,0.04,max(length(gx),length(gy)));
 float angleFade=smoothstep(0.012,0.045,viewTS.z);
 float2 edge=min(frac(a.uv.xy),1-frac(a.uv.xy));
 // Relief.z=0 for repeat; >0 for non-tileable facades.
 float edgeFade=(Relief.z>0 && Relief.z!=0.0009765625)?saturate(min(edge.x,edge.y)/Relief.z):1;
 float strength=valid*distanceFade*angleFade*edgeFade*Controls.x*Controls.y;
 float2 uv=a.uv.xy;
 [branch] if(strength>0.0001)uv=Trace(a.uv.xy,viewTS,lod,strength);
 float4 tex=tex2Dgrad(Albedo,uv,gx,gy);
 float4 surfaceSample=tex2Dgrad(NormalHeight,uv,gx,gy);
 float3 nt=surfaceSample.rgb*2-1;
 nt.xy*=BumpScale*Controls.x*Controls.y; nt=normalize(nt);
 float3 mapped=normalize(t*nt.x+b*nt.y+n*nt.z);
 float3 L=normalize(a.sunWorld);
 // Preserve accepted brightness-rule lighting. Only local relief perturbs it.
 float local=clamp(dot(mapped,L)-dot(n,L),-0.35,0.35)*valid*distanceFade*Controls.y;
 // Soft height-field self-shadow adds local depth without bleaching the albedo.
 // Only direct illumination is occluded; ambient and existing baked shadows stay.
 float reliefShadow=1;
 float3 lightTS=float3(dot(L,t),dot(L,b),dot(L,n));
 [branch] if(strength>0.0001 && lightTS.z>0.08) {
  float surface=surfaceSample.a;
  float stepHeight=(1-surface)/4;
  float2 ray=lightTS.xy/max(lightTS.z,0.15)*Relief.xy*strength*stepHeight;
  [unroll] for(int k=1;k<=4;++k){
   float hh=1-Height(uv+ray*k,lod);
   float blocked=smoothstep(0.025,0.12,hh-(surface+stepHeight*k));
   reliefShadow=min(reliefShadow,1-0.65*blocked);
  }
 }
 float3 lighting=saturate(Sun*a.weights.w*saturate(a.lightFake.z)+a.lightFake.w);
 // Preserve the inspected T_Lpse_Tdnl_Sds variance/static-shadow equations.
 // Neither shadow lookup moves with the relief ray.
 float3 shadowCoord=a.shadow.xyz/a.shadow.w;
 float receiver=saturate(shadowCoord.z);
 float2 moments=tex2D(DynamicShadow,shadowCoord.xy).xy;
 float variance=saturate(moments.y-moments.x*moments.x+ShadowParams.y);
 float delta=receiver-moments.x;
 float probability=variance/max(variance+delta*delta,0.00000001);
 float dynamic=receiver<=moments.x?1:pow(probability,ShadowParams.z);
 dynamic=saturate(dynamic+a.weights.z);
 float2 stat=tex2D(StaticShadow,a.lm).xy;
 float visibility=saturate(min(dynamic,stat.y)+ShadowParams.x);
 lighting=saturate(lighting+Sun*a.weights.w*local)*visibility*reliefShadow+Ambient*(1-stat.x);
 float3 lit=tex.rgb*lighting*a.tint.rgb*tex2D(Lightmap,a.uv.zw).rgb*2;
 return float4(lerp(lit,Fog.rgb,a.weights.y)*Exposure,tex2Dgrad(Albedo,a.uv.xy,gx,gy).a*a.tint.a);
}
