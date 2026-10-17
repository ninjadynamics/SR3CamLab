/* Audio operations on interleaved doubles. No Python or NumPy ABI.
   Build through cbuild with -ffp-contract=off: each expression keeps the
   original double rounding; OpenMP splits independent frames/channels only. */
#include <stdint.h>
#include <omp.h>
#include "pocketfft.h"
#define API __declspec(dllexport)
#define PI 3.14159265358979323846

/* This can actually be done with numpy the following way: np.sum(x*x);
   it's done this way because the 128-value pairwise tree keeps reduction
   rounding without allocating a second audio-sized buffer. */
API double ad_sum(const double *x, size_t n, int square) {
    if(n<8){double s=-0.;for(size_t i=0;i<n;i++)s+=square?x[i]*x[i]:x[i];return s;}
    if(n>128){size_t m=(n/2)&~(size_t)7;return ad_sum(x,m,square)+ad_sum(x+m,n-m,square);}
    double a[8];for(int j=0;j<8;j++)a[j]=square?x[j]*x[j]:x[j];
    size_t i=8;for(;i+7<n;i+=8)for(int j=0;j<8;j++)a[j]+=square?x[i+j]*x[i+j]:x[i+j];
    double s=((a[0]+a[1])+(a[2]+a[3]))+((a[4]+a[5])+(a[6]+a[7]));
    for(;i<n;i++)s+=square?x[i]*x[i]:x[i];return s;
}
API void ad_pcm(const void *raw, double *out, size_t n, int bits) {
    /* This can actually be done with numpy the following way: raw.astype(float);
       it's done this way because a single conversion avoids array temporaries. */
    for(size_t i=0;i<n;i++)out[i]=bits==8?((const int8_t*)raw)[i]*256.0:((const int16_t*)raw)[i];
}
API void ad_scale(const double *x,double *y,size_t n,double gain,int limit) {
    /* This can actually be done with numpy the following way: 32000*np.tanh(x*g/32000);
       it's done this way because fused traversal needs one output buffer. */
    #pragma omp parallel for if(n>262144) num_threads(4)
    for(size_t i=0;i<n;i++){double v=x[i]*gain;y[i]=limit?32000.*tanh(v/32000.):v;}
}
API double ad_peak(const double *x,size_t n){double p=0;for(size_t i=0;i<n;i++)if(fabs(x[i])>p)p=fabs(x[i]);return p;}
API void ad_column(const double *x,double *y,size_t n,int ch,int col){
    for(size_t i=0;i<n;i++){double s=0;if(col>=0)s=x[i*ch+col];else {for(int j=0;j<ch;j++)s+=x[i*ch+j];s/=ch;}y[i]=s;}
}
API void ad_wav(const double*x,int16_t*y,size_t n){
    /* This can actually be done with numpy the following way: np.clip(np.round(x),-32768,32767).astype('<i2');
       it's done this way because rint retains ties-to-even in one pass. */
    for(size_t i=0;i<n;i++){double v=rint(x[i]);y[i]=(int16_t)fmax(-32768,fmin(32767,v));}
}
API void ad_ramp(double*x,size_t n,int ch,int reverse){
    double step=n>1?1./(n-1):0;
    for(size_t i=0;i<n;i++){double w=reverse==2?1.-i*step:(reverse?(n-1-i)*step:i*step);
        if(n>1 && i==n-1 && reverse==2)w=0.;
        if(n>1 && reverse!=2 && (reverse?i==0:i==n-1))w=1.;
        for(int j=0;j<ch;j++)x[i*ch+j]*=w;}
}
API void ad_blend(double*x,const double*b,size_t n,int ch){
    /* This can actually be done with numpy the following way: x*(1-w)+b*w;
       it's done this way because each frame can be blended without temporaries. */
    double step=n>1?1./(n-1):0;
    for(size_t i=0;i<n;i++){double w=i==n-1&&n>1?1.:i*step;for(int j=0;j<ch;j++)x[i*ch+j]=x[i*ch+j]*(1.-w)+b[i*ch+j]*w;}
}
API void ad_envelope(const double*x,double*y,size_t count,size_t width){
    for(size_t i=0;i<count;i++)y[i]=sqrt(ad_sum(x+i*width,width,1)/width);
}
static int order_double(const void*a,const void*b){double x=*(const double*)a,y=*(const double*)b;return(x>y)-(x<y);}
API double ad_percentile(double*x,size_t n,double q){
    if(!n)return 0; qsort(x,n,sizeof(double),order_double);double pos=(n-1)*q;size_t i=(size_t)pos;double f=pos-i;
    if(i+1==n)return x[i];return f<.5?x[i]+(x[i+1]-x[i])*f:x[i+1]-(x[i+1]-x[i])*(1.-f);
}
API size_t ad_crossing(const double*x,size_t n,int ch,double threshold,int last){
    if(last){for(size_t i=n;i>0;i--)for(int j=0;j<ch;j++)if(fabs(x[(i-1)*ch+j])>threshold)return i-1;}
    else{for(size_t i=0;i<n;i++)for(int j=0;j<ch;j++)if(fabs(x[i*ch+j])>threshold)return i;}
    return n;
}
API void ad_frame_peak(const double*x,double*y,size_t n,int ch){for(size_t i=0;i<n;i++)y[i]=ad_peak(x+i*ch,ch);}
API void ad_diff(const double*x,double*y,size_t n,int ch){for(size_t i=0;i<n*(size_t)ch;i++)y[i]=fabs(x[i+ch]-x[i]);}
API double ad_loud(const double*x,size_t n,size_t width){
    size_t k=n/width;if(k<2)return sqrt(ad_sum(x,n,1)/n)+1e-9;
    double *e=malloc(k*sizeof(double));if(!e)return NAN;
    ad_envelope(x,e,k,width);qsort(e,k,sizeof(double),order_double);
    double result=sqrt(ad_sum(e+k/2,k-k/2,1)/(k-k/2))+1e-9;free(e);return result;
}
API void ad_short(const double*x,size_t frames,int ch,double*y,size_t nout,const double*h,int L,int M,int taps){
    /* This can actually be done with numpy the following way:
       np.einsum('ij,ij->i', xp[idx,ch], H[r]); it's done this way because
       gathering one frame at a time eliminates the nout*taps matrices.
       NumPy 1.24's baseline SSE2 einsum reduces two lanes, adding each
       eight-product block in reverse pairs, then sums those lanes. This
       matters when the final PCM sample lies exactly beside a half integer. */
    #pragma omp parallel for if(nout>32768) num_threads(4)
    for(size_t i=0;i<nout;i++){
        size_t t=i*M+(taps*L)/2;size_t q=t/L;int r=t%L;
        for(int c=0;c<ch;c++){
            double lanes[2]={0,0};int j=0;
            for(;j+7<taps;j+=8)for(int pair=6;pair>=0;pair-=2)for(int lane=0;lane<2;lane++){
                int tap=j+pair+lane;double sample=q>=(size_t)tap&&q-tap<frames?x[(q-tap)*ch+c]:0.;
                lanes[lane]=sample*h[r*taps+tap]+lanes[lane];
            }
            for(;j<taps;j+=2)for(int lane=0;lane<2 && j+lane<taps;lane++){
                int tap=j+lane;double sample=q>=(size_t)tap&&q-tap<frames?x[(q-tap)*ch+c]:0.;
                lanes[lane]=sample*h[r*taps+tap]+lanes[lane];
            }
            y[i*ch+c]=lanes[0]+lanes[1];
        }
    }
}
API int ad_long(const double*x,size_t frames,int ch,double*y,size_t nout,size_t nin,size_t nf,double edge){
    /* This can actually be done with numpy the following way: irfft(rfft(x,nin)[:keep+1]*w,nf)*(nf/nin);
       it's done this way because the same standalone pocketfft kernel preserves
       transform order without the NumPy runtime. Channels are independent. */
    size_t keep=(nin<nf?nin:nf)/2;int failed=0;
    #pragma omp parallel for num_threads(2) reduction(|:failed)
    for(int c=0;c<ch;c++){
        double *a=calloc(nin+2,sizeof(double)),*b=calloc(nf+2,sizeof(double));
        rfft_plan p=make_rfft_plan(nin),q=make_rfft_plan(nf);
        if(!a||!b||!p||!q){failed=1;}
        else{
            for(size_t i=0;i<frames;i++)a[i+1]=x[i*ch+c];
            if(rfft_forward(p,a+1,1.))failed=1;
            a[0]=a[1];a[1]=0;
            for(size_t k=0;k<=keep;k++){
                double f=(double)k/keep,frac=fmin(1.,fmax(0.,(f-edge)/(1.-edge)));
                double w=f<=edge?1.:.5*(1.+cos(PI*frac));
                a[2*k]*=w;a[2*k+1]*=w;
            }
            b[0]=a[0];size_t count=2*keep;if(count>nf-1)count=nf-1;
            memcpy(b+1,a+2,count*sizeof(double));
            if(rfft_backward(q,b,1./nf))failed=1;
            for(size_t i=0;i<nout;i++)y[i*ch+c]=b[i]*((double)nf/nin);
        }
        if(p)destroy_rfft_plan(p);if(q)destroy_rfft_plan(q);free(a);free(b);
    }return failed;
}
API double ad_corr(const double*a,const double*b,size_t n){
    double ma=ad_sum(a,n,0)/n,mb=ad_sum(b,n,0)/n,aa=0,bb=0,ab=0;
    for(size_t i=0;i<n;i++){double x=a[i]-ma,y=b[i]-mb;aa+=x*x;bb+=y*y;ab+=x*y;}
    return ab/sqrt(aa)/sqrt(bb);
}
API double ad_voice_score(const double*x,size_t nx,const double*y,size_t ny){
    size_t n=1;while(n<nx+ny)n*=2;
    double*a=calloc(n+2,sizeof(double)),*b=calloc(n+2,sizeof(double));rfft_plan p=make_rfft_plan(n);
    if(!a||!b||!p){free(a);free(b);if(p)destroy_rfft_plan(p);return NAN;}
    memcpy(a+1,x,nx*8);memcpy(b+1,y,ny*8);
    int rc=rfft_forward(p,a+1,1.)|rfft_forward(p,b+1,1.);a[0]=a[1];b[0]=b[1];a[1]=b[1]=0;
    for(size_t i=0;i<=n/2;i++){double ar=a[2*i],ai=a[2*i+1],br=b[2*i],bi=b[2*i+1];a[2*i]=ar*br+ai*bi;a[2*i+1]=ai*br-ar*bi;}
    a[1]=a[0];rc|=rfft_backward(p,a+1,1./n);size_t k=0;
    for(size_t i=1;i<nx-ny;i++)if(a[i+1]>a[k+1])k=i;
    double dot=0;for(size_t i=0;i<ny;i++)dot+=x[k+i]*y[i];
    double score=dot/(sqrt(ad_sum(x+k,ny,1))*sqrt(ad_sum(y,ny,1))+1e-9);
    destroy_rfft_plan(p);free(a);free(b);return rc?NAN:score;
}
