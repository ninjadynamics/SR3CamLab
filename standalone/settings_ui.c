/* SR3Lab settings companion. Copyright (c) 2026 Ninja Dynamics. MIT.
 * Immediate-mode raylib 5.5, CamLab's palette and system Segoe UI fonts.
 * No browser, service, Python runtime, or external UI DLL.
 */
#include "raylib.h"
#include "rlgl.h"
#include "settings.h"
#include "launch.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static const Color BG={20,22,28,255}, PANEL={28,31,39,255}, TEXT={236,238,244,255};
static const Color SUB={158,164,178,255}, FAINT={104,110,124,255}, ACCENT={255,138,76,255};
static Font regular,semibold;
static float scale=1;
static Sr3Settings current,saved;
static char yamlPath[SR3_PATH],status[512]="",edit[SR3_PATH];
static unsigned long diskHash;
static int valid,tab,editing=-1,picker=-1,closing,quit;
static const char *const bindingNames[]={"Unassigned","Cross / A","Circle / B","Square / X","Triangle / Y","Create / Back","PS / Guide","Options / Start","L3 / Left stick","R3 / Right stick","L1 / Left shoulder","R1 / Right shoulder","D-pad up","D-pad down","D-pad left","D-pad right","Left stick left","Left stick right","Left stick up","Left stick down","Right stick left","Right stick right","Right stick up","Right stick down","L2 / Left trigger","R2 / Right trigger"};
static const char *const axisNames[]={"Left stick X","Left stick Y","Right stick X","Right stick Y","L2 / Left trigger","R2 / Right trigger"};
static Rectangle rect(float x,float y,float w,float h){return (Rectangle){x*scale,y*scale,w*scale,h*scale};}
static void text(const char *str,float x,float y,float size,Color color,int bold){DrawTextEx(bold?semibold:regular,str,(Vector2){roundf(x*scale),roundf(y*scale)},size*scale,0,color);}
static void box(Rectangle r,Color c){DrawRectangleRounded(r,0.24f,8,c);}
static int hover(Rectangle r){return CheckCollisionPointRec(GetMousePosition(),r);}
static int button(const char *label,float x,float y,float w,int accent,int enabled){
    Rectangle r=rect(x,y,w,38);int hot=enabled && hover(r);
    Color c=accent?ACCENT:(hot?(Color){50,54,65,255}:(Color){38,41,51,255});
    box(r,enabled?c:PANEL);
    text(label,x+14,y+9,15,enabled?(accent?BG:TEXT):FAINT,1);
    if(hot)SetMouseCursor(MOUSE_CURSOR_POINTING_HAND);
    return hot && IsMouseButtonReleased(MOUSE_BUTTON_LEFT);
}
static int dirty(void){return memcmp(&current,&saved,sizeof(current))!=0;}
static const char *choiceLabel(const Sr3Field *field,int value){
    const char *v=field->choices[value];
    if(field->choices==sr3_buttons)return bindingNames[value];
    if(field->choices==sr3_axes)return axisNames[value];
    if(!strcmp(v,"true"))return "On";
    if(!strcmp(v,"false"))return "Off";
    if(!strcmp(v,"linear"))return "Linear";
    if(!strcmp(v,"teknoparrot"))return "TeknoParrot";
    return v;
}
static const char *labelValue(int f){
    const Sr3Field *field=&sr3_fields[f];int value=*sr3_value(&current,f);
    if(field->choices)return choiceLabel(field,value);
    return TextFormat("%d",value);
}
static int commitEdit(void){
    if(editing<0)return 1;
    if(editing==sr3_field_count){
        if(!edit[0]){strcpy(status,"Choose the private Rally.exe path.");return 0;}
        snprintf(current.game_path,sizeof(current.game_path),"%s",edit);
    }else{
        char *end;long n=strtol(edit,&end,10);const Sr3Field *f=&sr3_fields[editing];
        if(end==edit || *end || n<f->min || n>f->max){snprintf(status,sizeof(status),"%s must be between %d and %d.",f->label,f->min,f->max);return 0;}
        *sr3_value(&current,editing)=(int)n;
    }
    editing=-1;status[0]=0;return 1;
}
static int save(void){
    if(!valid || !commitEdit())return 0;
    if(sr3_fingerprint(yamlPath)!=diskHash){strcpy(status,"The selected settings file changed outside this app. Reload before saving.");return 0;}
    if(!sr3_save(yamlPath,&current,status,sizeof(status)))return 0;
    saved=current;diskHash=sr3_fingerprint(yamlPath);strcpy(status,"Saved. Changes apply on the next game launch.");return 1;
}
static void reload(void){
    Sr3Settings loaded;
    if(sr3_load(yamlPath,&loaded,status,sizeof(status))){current=saved=loaded;valid=1;diskHash=sr3_fingerprint(yamlPath);editing=picker=-1;snprintf(status,sizeof status,"Loaded %s.",strrchr(yamlPath,'\\')?strrchr(yamlPath,'\\')+1:yamlPath);}
    else valid=0;
}
static int page(int i){
    const char *s=sr3_fields[i].section,*key=sr3_fields[i].key;
    if(!strcmp(s,"display"))return 0;
    if(!strcmp(s,"game"))return 2;
    if(!strcmp(s,"runtime"))return 3;
    if(!strcmp(s,"input")){
        if(!strcmp(key,"controller") || !strcmp(key,"deadzone") || !strcmp(key,"threshold") || !strcmp(key,"background") || !strcmp(key,"dpad") || !strcmp(key,"curve"))return 3;
        return 1;
    }
    return -1;
}
static void fieldRow(int index,float x,float y,int blocked){
    const Sr3Field *f=&sr3_fields[index];Rectangle r=rect(x,y+24,350,35);int active=editing==index;
    int changed=*sr3_value(&current,index)!=*sr3_value(&saved,index),hot=!blocked && hover(r);
    text(f->label,x,y,13,SUB,0);box(r,active?(Color){48,45,43,255}:PANEL);
    if(active)DrawRectangleRoundedLinesEx(r,0.24f,8,scale,ACCENT);
    text(active?edit:labelValue(index),x+12,y+31,15,changed || active?ACCENT:TEXT,0);
    text(f->choices?"v":"edit",x+310,y+33,12,FAINT,0);
    if(hot){SetMouseCursor(MOUSE_CURSOR_POINTING_HAND);if(IsMouseButtonReleased(MOUSE_BUTTON_LEFT) && editing!=index && commitEdit()){
        if(f->choices)picker=index;
        else {editing=index;snprintf(edit,sizeof(edit),"%d",*sr3_value(&current,index));}
    }}
}
static void inputText(void){
    int c;size_t len=strlen(edit);
    if(editing<0)return;
    if(IsKeyDown(KEY_LEFT_CONTROL) && IsKeyPressed(KEY_A)){edit[0]=0;len=0;}
    while((c=GetCharPressed())>0){if(c>=32 && c<127 && len+1<sizeof(edit) && (editing==sr3_field_count || (c>='0' && c<='9'))){edit[len++]=(char)c;edit[len]=0;}}
    if((IsKeyPressed(KEY_BACKSPACE) || IsKeyPressedRepeat(KEY_BACKSPACE)) && len)edit[len-1]=0;
    if(IsKeyPressed(KEY_ENTER) && !IsKeyDown(KEY_LEFT_CONTROL))commitEdit();
    if(IsKeyPressed(KEY_ESCAPE))editing=-1;
}
static void draw(void){
    int i,n=0,oldPicker=picker,blocked=picker>=0 || closing || !valid;
    SetMouseCursor(MOUSE_CURSOR_DEFAULT);
    ClearBackground(BG);
    text("SR3LAB",32,25,13,ACCENT,1);
    text("Settings",32,48,30,TEXT,1);
    text(TextFormat("%d x %d  /  %s",current.width,current.height,current.windowed?"Windowed":"Fullscreen"),32,91,14,SUB,0);
    if(dirty())text("UNSAVED",680,61,12,ACCENT,1);
    {const char *tabs[]={"Display","Controls","Game","Advanced"};
        for(i=0;i<4;i++){
            float x=32+i*194;Rectangle r=rect(x,128,184,36);
            if(i==tab){box(r,PANEL);DrawRectangleRec(rect(x+12,162,160,2),ACCENT);}
            text(tabs[i],x+12,137,14,i==tab?TEXT:SUB,1);
            if(!blocked && hover(r) && IsMouseButtonReleased(MOUSE_BUTTON_LEFT) && commitEdit())tab=i;
        }
    }
    for(i=1;i<sr3_field_count;i++)if(page(i)==tab){fieldRow(i,32+(n%2)*390,192+(n/2)*75,blocked);n++;}
    if(tab==0){
        text("Quick resolution",32,447,13,SUB,0);
        if(button("1080p",32,472,110,0,!blocked) && commitEdit()){current.width=1920;current.height=1080;}
        if(button("1440p",152,472,110,0,!blocked) && commitEdit()){current.width=2560;current.height=1440;}
        if(button("4K",272,472,110,0,!blocked) && commitEdit()){current.width=3840;current.height=2160;}
        text("Fullscreen uses the selected resolution and refresh rate.",32,537,13,SUB,0);
        text("Other graphics quality settings stay in the game's config.ini.",32,559,13,FAINT,0);
    }
    if(tab==1){text("Positions work across controller brands. Cross = A; Options = Start.",32,583,13,SUB,0);}
    if(tab==2){
        Rectangle r=rect(32,471,740,38);text("Private game executable (relative to this settings file, or absolute)",32,447,13,SUB,0);
        box(r,PANEL);BeginScissorMode((int)(42*scale),(int)(475*scale),(int)(720*scale),(int)(32*scale));
        text(editing==sr3_field_count?edit:current.game_path,44,481,14,editing==sr3_field_count?ACCENT:TEXT,0);EndScissorMode();
        if(!blocked && hover(r) && IsMouseButtonReleased(MOUSE_BUTTON_LEFT) && editing!=sr3_field_count && commitEdit()){editing=sr3_field_count;snprintf(edit,sizeof(edit),"%s",current.game_path);}
        text("Enter confirms a field. Ctrl+A clears it for replacement.",32,537,13,FAINT,0);
    }
    if(tab==3){
        const char *watch=sr3_patch_value(&current,"watchdog");
        int on=!(watch && (!_stricmp(watch,"off") || !_stricmp(watch,"false") || !strcmp(watch,"0") || !_stricmp(watch,"no")));
        if(button(on?"Auto watchdog: on":"Auto watchdog: off",32,492,220,0,!blocked) && commitEdit()){
            strcpy(current.patches[8],on?"off":"on");current.patches_present|=1u<<8;
        }
        if(button("Start with watchdog",272,492,220,0,!blocked) && save()){
            if(sr3_launch_mode(yamlPath,&current,1,status,sizeof status))strcpy(status,"Watchdog host started; report logs are in the mod folder's crash directory.");
        }
        text("Ctrl+Scroll Lock starts the watchdog while playing with mods.",32,544,13,SUB,0);
        text("Controller 0 is the first connected SDL gamepad.",32,570,13,SUB,0);
        text("TeknoParrot curve + deadzone 0 preserves the imported steering conversion.",32,592,13,FAINT,0);}
    DrawLineEx((Vector2){32*scale,623*scale},(Vector2){772*scale,623*scale},scale,(Color){53,57,68,255});
    BeginScissorMode((int)(32*scale),(int)(635*scale),(int)(740*scale),(int)(30*scale));
    text(status[0]?status:(dirty()?"Unsaved changes":yamlPath),32,639,13,valid?SUB:ACCENT,0);EndScissorMode();
    if(button("Reload",32,678,100,0,picker<0 && !closing)){if(dirty())closing=2;else reload();}
    if(button("Save",548,678,100,dirty(),!blocked)){save();}
    if(button("Save & play",660,678,112,1,!blocked)){if(save()){if(sr3_launch(yamlPath,&current,status,sizeof(status)))strcpy(status,"Game launched. Close the game before starting another instance.");}}
    text("Ctrl+S save  /  Ctrl+Enter play",154,690,12,FAINT,0);
    if(picker>=0){
        const Sr3Field *f=&sr3_fields[picker];int count=f->max-f->min+1,columns=count>10?3:2,rows=(count+columns-1)/columns;
        DrawRectangle(0,0,GetScreenWidth(),GetScreenHeight(),(Color){0,0,0,180});
        box(rect(45,180,714,(float)(100+rows*38)),PANEL);text(f->label,65,198,20,TEXT,1);
        for(i=f->min;i<=f->max;i++){
            int j=i-f->min;float x=65+(j%columns)*(674.0f/columns),y=242+(j/columns)*38;
            const char *label=choiceLabel(f,i);
            Rectangle r=rect(x,y,674.0f/columns-10,32);int hot=hover(r);
            if(hot || *sr3_value(&current,picker)==i)box(r,hot?(Color){65,57,51,255}:BG);
            text(label,x+8,y+7,13,*sr3_value(&current,picker)==i?ACCENT:TEXT,0);
            if(oldPicker>=0 && hot && IsMouseButtonReleased(MOUSE_BUTTON_LEFT)){*sr3_value(&current,picker)=i;picker=-1;break;}
        }
        if(IsKeyPressed(KEY_ESCAPE))picker=-1;
    }
    if(closing){
        DrawRectangle(0,0,GetScreenWidth(),GetScreenHeight(),(Color){0,0,0,190});box(rect(130,265,544,180),PANEL);
        text("Unsaved changes",154,287,23,TEXT,1);text(closing==2?"Reload discards your edits in this window.":"Save your settings before closing?",154,326,14,SUB,0);
        if(button("Keep editing",154,381,140,0,1))closing=0;
        if(button("Discard",306,381,110,0,1)){if(closing==2){reload();closing=0;}else quit=1;}
        if(closing==1 && button("Save & close",430,381,160,1,valid)){if(save())quit=1;else closing=0;}
    }
}
int main(int argc,char **argv){
    const char *preview=NULL;char fontPath[SR3_PATH];const char *win=getenv("WINDIR");int frames=0;
    Sr3LaunchOptions options; (void)argc; (void)argv;
    if(!sr3_current_options(1,&options,status,sizeof status)){
        sr3_option_error(status);return 1;
    }
    strcpy(yamlPath,options.settings);if(options.preview[0]){preview=options.preview;tab=options.preview_tab;}
    sr3_defaults(&current);saved=current;reload();
    SetTraceLogLevel(LOG_WARNING);SetConfigFlags(FLAG_MSAA_4X_HINT|(preview?FLAG_WINDOW_HIDDEN:0));
    InitWindow(804,744,TextFormat("SR3Lab Settings - %s",strrchr(yamlPath,'\\')?strrchr(yamlPath,'\\')+1:yamlPath));if(!IsWindowReady())return 2;
    SetExitKey(KEY_NULL);
    {int monitor=GetCurrentMonitor();Vector2 dpi=GetWindowScaleDPI();scale=fminf(dpi.x,fminf(GetMonitorWidth(monitor)/850.0f,GetMonitorHeight(monitor)/800.0f));if(scale<0.75f)scale=0.75f;SetWindowSize((int)(804*scale),(int)(744*scale));}
    snprintf(fontPath,sizeof(fontPath),"%s/Fonts/segoeui.ttf",win?win:"C:/Windows");regular=LoadFontEx(fontPath,(int)(20*scale),NULL,0);
    snprintf(fontPath,sizeof(fontPath),"%s/Fonts/seguisb.ttf",win?win:"C:/Windows");semibold=LoadFontEx(fontPath,(int)(30*scale),NULL,0);
    SetTextureFilter(regular.texture,TEXTURE_FILTER_BILINEAR);SetTextureFilter(semibold.texture,TEXTURE_FILTER_BILINEAR);SetTargetFPS(30);
    while(!quit){
        if(WindowShouldClose()){if(dirty() || editing>=0)closing=1;else break;}
        if(!closing && picker<0){inputText();if(IsKeyDown(KEY_LEFT_CONTROL) && IsKeyPressed(KEY_S))save();
            if(IsKeyDown(KEY_LEFT_CONTROL) && IsKeyPressed(KEY_ENTER) && save())sr3_launch(yamlPath,&current,status,sizeof(status));}
        /* Same correction as CamLab: our UI owns DPI scaling, including after
           a fullscreen game changes the monitor mode. Mouse coordinates stay aligned. */
        BeginDrawing();rlLoadIdentity();draw();EndDrawing();
        if(preview && ++frames==3){
            int w=GetRenderWidth(),h=GetRenderHeight();unsigned char *pixels=rlReadScreenPixels(w,h);
            Image img={pixels,w,h,1,PIXELFORMAT_UNCOMPRESSED_R8G8B8A8};int success=pixels?ExportImage(img,preview):0;
            if(pixels)MemFree(pixels);
            if(!success)return 3;
            break;
        }
    }
    UnloadFont(regular);UnloadFont(semibold);CloseWindow();return 0;
}
