#define SDL_MAIN_HANDLED
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <stdio.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"SDL check %d: %s (%s)\n",__LINE__,#x,SDL_GetError());SDL_Quit();return 1;}}while(0)
int main(void){
    SDL_VirtualJoystickDesc desc;SDL_JoystickID id;SDL_Gamepad *pad;SDL_Joystick *joy;
    SDL_SetMainReady();CHECK(SDL_Init(SDL_INIT_GAMEPAD));
    SDL_INIT_INTERFACE(&desc);
    desc.type=SDL_JOYSTICK_TYPE_GAMEPAD;desc.naxes=6;desc.nbuttons=15;
    desc.axis_mask=0x3f;desc.button_mask=0x7fff;desc.name="SR3Lab virtual controller test";
    id=SDL_AttachVirtualJoystick(&desc);CHECK(id!=0);CHECK(SDL_IsGamepad(id));
    pad=SDL_OpenGamepad(id);CHECK(pad!=NULL);joy=SDL_GetGamepadJoystick(pad);CHECK(joy!=NULL);
    CHECK(SDL_SetJoystickVirtualAxis(joy,SDL_GAMEPAD_AXIS_LEFTX,-32768));
    CHECK(SDL_SetJoystickVirtualAxis(joy,SDL_GAMEPAD_AXIS_LEFT_TRIGGER,-32768));
    CHECK(SDL_SetJoystickVirtualAxis(joy,SDL_GAMEPAD_AXIS_RIGHT_TRIGGER,32767));
    CHECK(SDL_SetJoystickVirtualButton(joy,SDL_GAMEPAD_BUTTON_START,true));
    SDL_UpdateGamepads();
    CHECK(SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_LEFTX)==-32768);
    CHECK(SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_LEFT_TRIGGER)==0);
    CHECK(SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_RIGHT_TRIGGER)==32767);
    CHECK(SDL_GetGamepadButton(pad,SDL_GAMEPAD_BUTTON_START));
    CHECK(SDL_DetachVirtualJoystick(id));SDL_UpdateGamepads();CHECK(!SDL_GamepadConnected(pad));SDL_CloseGamepad(pad);
    id=SDL_AttachVirtualJoystick(&desc);CHECK(id!=0);
    pad=SDL_OpenGamepad(id);CHECK(pad!=NULL);CHECK(SDL_GamepadConnected(pad));
    SDL_CloseGamepad(pad);CHECK(SDL_DetachVirtualJoystick(id));SDL_Quit();
    puts("SDL: virtual gamepad, steering, independent triggers, Start, disconnect and reconnect pass.");return 0;
}
