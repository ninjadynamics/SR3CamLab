/* Private render-thread HUD. Cached own text texture; no screen capture, input
   polling, timer thread or retained state block. Released with device resources. */
static int hud_texture(IDirect3DDevice9 *d,int enabled,int tenths) {
 const int width=330,height=36;BITMAPINFO bi;void *pixels=0;HDC dc=0;HBITMAP bm=0;HFONT font=0;HGDIOBJ oldbm=0,oldfont=0;D3DLOCKED_RECT lr;char text[160],mode[32];int y,ok=0;
 if(p.hud && p.hud_on==enabled && p.hud_tenths==tenths)return 1;
 memset(&bi,0,sizeof(bi));bi.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);bi.bmiHeader.biWidth=width;bi.bmiHeader.biHeight=-height;bi.bmiHeader.biPlanes=1;bi.bmiHeader.biBitCount=32;bi.bmiHeader.biCompression=BI_RGB;
 dc=CreateCompatibleDC(0);if(!dc)goto done;
 bm=CreateDIBSection(dc,&bi,DIB_RGB_COLORS,&pixels,0,0);if(!bm || !pixels)goto done;oldbm=SelectObject(dc,bm);
 {int i;for(i=0;i<width*height;++i)((DWORD*)pixels)[i]=0xff202830;}
 font=CreateFontA(-22,0,0,0,FW_SEMIBOLD,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,ANTIALIASED_QUALITY,DEFAULT_PITCH,"Segoe UI");if(!font)goto done;
 oldfont=SelectObject(dc,font);SetBkMode(dc,TRANSPARENT);SetTextColor(dc,RGB(70,235,240));
 if(!enabled)strcpy(mode,"POM OFF");else snprintf(mode,sizeof(mode),"Depth %d.%dx",enabled/10,enabled%10);
 if(tenths<0)snprintf(text,sizeof(text),"FPS  --   %s",mode);else snprintf(text,sizeof(text),"FPS  %d.%d   %s",tenths/10,tenths%10,mode);
 TextOutA(dc,10,5,text,(int)strlen(text));GdiFlush();
 {int i;for(i=0;i<width*height;++i)((DWORD*)pixels)[i]|=0xff000000;}
 if(!p.hud && FAILED(IDirect3DDevice9_CreateTexture(d,width,height,1,0,D3DFMT_A8R8G8B8,D3DPOOL_MANAGED,&p.hud,0)))goto done;
 if(FAILED(IDirect3DTexture9_LockRect(p.hud,0,&lr,0,0)))goto done;
 for(y=0;y<height;++y)memcpy((BYTE*)lr.pBits+y*lr.Pitch,(BYTE*)pixels+y*width*4,width*4);
 if(FAILED(IDirect3DTexture9_UnlockRect(p.hud,0)))goto done;
 p.hud_on=enabled;p.hud_tenths=tenths;ok=1;
done:
 if(oldfont)SelectObject(dc,oldfont);if(font)DeleteObject(font);if(oldbm)SelectObject(dc,oldbm);if(bm)DeleteObject(bm);if(dc)DeleteDC(dc);return ok;
}
void sr3_pom_overlay(IDirect3DDevice9 *d) {
 IDirect3DStateBlock9 *state=0;IDirect3DSurface9 *back=0,*target=0,*depth=0;D3DVIEWPORT9 vp,originalVp;D3DSURFACE_DESC desc;int enabled,tenths,targetChanged=0;HRESULT restore,drawResult;
 struct Vertex {float x,y,z,w,u,v;} v[4];float x,y,right,bottom;
 ++p.stats.hud_calls;p.stats.hud_stage=1;
 if(d!=p.device || p.busy || p.cleaning || p.recording)return;
 p.stats.hud_stage=2;p.stats.hud_error=S_OK;
 {int on;sr3_pom_controls(&on,&enabled);if(!on)enabled=0;}
 if(p.fps_gain!=enabled){p.fps_gain=enabled;p.fps_start.QuadPart=0;}
 {LARGE_INTEGER now;QueryPerformanceCounter(&now);
  if(!p.fps_start.QuadPart){p.fps_start=now;p.fps_frames=0;p.fps_tenths=-1;}
  else {LONGLONG elapsed=now.QuadPart-p.fps_start.QuadPart;++p.fps_frames;
   if(elapsed>=p.fps_frequency.QuadPart/2){p.fps_tenths=elapsed>p.fps_frequency.QuadPart*2?-1:(int)((double)p.fps_frames*10*p.fps_frequency.QuadPart/elapsed+.5);p.fps_start=now;p.fps_frames=0;}}
 }
 tenths=p.fps_tenths;p.busy=1;
 if(!hud_texture(d,enabled,tenths)){p.stats.hud_error=E_FAIL;goto done;}
 p.stats.hud_stage=3;if(FAILED(p.stats.hud_error=IDirect3DDevice9_GetViewport(d,&vp)))goto done;
 originalVp=vp;
 p.stats.hud_stage=4;if(FAILED(p.stats.hud_error=IDirect3DDevice9_CreateStateBlock(d,D3DSBT_ALL,&state)))goto done;
 // SR3 can leave its offscreen post-processing target bound after compositing.
 // A late HUD must explicitly target the displayed backbuffer. RT/depth are
 // NOT part of D3DSBT_ALL; restore them independently before the state block.
 p.stats.hud_stage=5;
 if(FAILED(IDirect3DDevice9_GetBackBuffer(d,0,0,D3DBACKBUFFER_TYPE_MONO,&back)) ||
    FAILED(IDirect3DDevice9_GetRenderTarget(d,0,&target)) ||
    FAILED(IDirect3DSurface9_GetDesc(back,&desc)))goto done;
 IDirect3DDevice9_GetDepthStencilSurface(d,&depth);
 targetChanged=1;p.stats.hud_stage=6;
 if(FAILED(IDirect3DDevice9_SetDepthStencilSurface(d,0)) || FAILED(IDirect3DDevice9_SetRenderTarget(d,0,back)))goto done;
 vp=(D3DVIEWPORT9){0,0,desc.Width,desc.Height,0,1};IDirect3DDevice9_SetViewport(d,&vp);
 right=(float)(vp.X+vp.Width)-12-.5f;x=right-330;if(x<0)x=0;
 y=(float)vp.Y+12-.5f;bottom=y+36;
 v[0]=(struct Vertex){x,y,0,1,0,0};v[1]=(struct Vertex){right,y,0,1,1,0};v[2]=(struct Vertex){x,bottom,0,1,0,1};v[3]=(struct Vertex){right,bottom,0,1,1,1};
 p.stats.hud_stage=7;if(FAILED(p.stats.hud_error=IDirect3DDevice9_BeginScene(d)))goto done;
 IDirect3DDevice9_SetVertexShader(d,0);IDirect3DDevice9_SetPixelShader(d,0);IDirect3DDevice9_SetFVF(d,D3DFVF_XYZRHW|D3DFVF_TEX1);
 IDirect3DDevice9_SetRenderState(d,D3DRS_ZENABLE,FALSE);IDirect3DDevice9_SetRenderState(d,D3DRS_ZWRITEENABLE,FALSE);
 IDirect3DDevice9_SetRenderState(d,D3DRS_ALPHATESTENABLE,FALSE);IDirect3DDevice9_SetRenderState(d,D3DRS_ALPHABLENDENABLE,FALSE);
 IDirect3DDevice9_SetRenderState(d,D3DRS_STENCILENABLE,FALSE);IDirect3DDevice9_SetRenderState(d,D3DRS_SCISSORTESTENABLE,FALSE);
 IDirect3DDevice9_SetRenderState(d,D3DRS_CLIPPLANEENABLE,0);IDirect3DDevice9_SetRenderState(d,D3DRS_VERTEXBLEND,D3DVBF_DISABLE);IDirect3DDevice9_SetRenderState(d,D3DRS_INDEXEDVERTEXBLENDENABLE,FALSE);
 IDirect3DDevice9_SetRenderState(d,D3DRS_FOGENABLE,FALSE);IDirect3DDevice9_SetRenderState(d,D3DRS_LIGHTING,FALSE);
 IDirect3DDevice9_SetRenderState(d,D3DRS_CULLMODE,D3DCULL_NONE);IDirect3DDevice9_SetRenderState(d,D3DRS_FILLMODE,D3DFILL_SOLID);
 IDirect3DDevice9_SetRenderState(d,D3DRS_COLORWRITEENABLE,15);IDirect3DDevice9_SetRenderState(d,D3DRS_SRGBWRITEENABLE,FALSE);
 IDirect3DDevice9_SetTexture(d,0,(IDirect3DBaseTexture9*)p.hud);
 IDirect3DDevice9_SetTextureStageState(d,0,D3DTSS_RESULTARG,D3DTA_CURRENT);IDirect3DDevice9_SetTextureStageState(d,0,D3DTSS_COLOROP,D3DTOP_SELECTARG1);IDirect3DDevice9_SetTextureStageState(d,0,D3DTSS_COLORARG1,D3DTA_TEXTURE);
 IDirect3DDevice9_SetTextureStageState(d,0,D3DTSS_ALPHAOP,D3DTOP_SELECTARG1);IDirect3DDevice9_SetTextureStageState(d,0,D3DTSS_ALPHAARG1,D3DTA_TEXTURE);
 IDirect3DDevice9_SetTextureStageState(d,0,D3DTSS_TEXCOORDINDEX,0);IDirect3DDevice9_SetTextureStageState(d,0,D3DTSS_TEXTURETRANSFORMFLAGS,D3DTTFF_DISABLE);
 IDirect3DDevice9_SetTextureStageState(d,1,D3DTSS_COLOROP,D3DTOP_DISABLE);
 IDirect3DDevice9_SetSamplerState(d,0,D3DSAMP_SRGBTEXTURE,0);IDirect3DDevice9_SetSamplerState(d,0,D3DSAMP_MINFILTER,D3DTEXF_LINEAR);IDirect3DDevice9_SetSamplerState(d,0,D3DSAMP_MAGFILTER,D3DTEXF_LINEAR);IDirect3DDevice9_SetSamplerState(d,0,D3DSAMP_MIPFILTER,D3DTEXF_NONE);
 p.stats.hud_stage=8;drawResult=p.original.DrawPrimitiveUP(d,D3DPT_TRIANGLESTRIP,2,v,sizeof(v[0]));p.stats.hud_error=drawResult;if(SUCCEEDED(drawResult)){++p.stats.hud_draws;p.stats.hud_stage=9;}IDirect3DDevice9_EndScene(d);
done:
 if(targetChanged){int bad=0;if(FAILED(IDirect3DDevice9_SetRenderTarget(d,0,target)))bad=1;if(FAILED(IDirect3DDevice9_SetDepthStencilSurface(d,depth)))bad=1;if(FAILED(IDirect3DDevice9_SetViewport(d,&originalVp)))bad=1;if(bad){p.disabled=1;++p.stats.restore_failures;notice(5);}}
 if(back)IDirect3DSurface9_Release(back);if(target)IDirect3DSurface9_Release(target);if(depth)IDirect3DSurface9_Release(depth);
 if(state){restore=IDirect3DStateBlock9_Apply(state);IDirect3DStateBlock9_Release(state);if(FAILED(restore)){p.disabled=1;++p.stats.restore_failures;notice(5);}}
 p.busy=0;
}
