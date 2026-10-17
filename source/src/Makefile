# CamLab - builds ../camlab.exe (next to PLAY.bat, patch.ps1 and the profiles it uses).
#
# Needs MinGW-w64 gcc, windres and raylib 5.5. The easiest way is raylib's Windows
# installer: its w64devkit has all three, so from that shell (or with C:\raylib\w64devkit\bin
# on the PATH) just run "make" in this folder, or "make -C src" from the repo root.
# If raylib lives elsewhere: make RAYLIB=path/to/raylib (with include/ and lib/ inside).
#
#   make            camlab.exe with its icon (from ../res/icon.png, or drawn by CamLab)
#   make noicon     camlab.exe without an icon (one gcc call, no windres)
#   make selftest   camlab_test.exe: the simulation without a window (prints statistics)
#   make clean

CC      = gcc
WINDRES = windres
OUT     = ../camlab.exe
ICONPNG = $(wildcard ../res/icon.png)

CFLAGS  = -O2 -std=c99 -Wall -Wextra -Wpedantic -Wshadow
LDFLAGS = -s -static -mwindows
LDLIBS  = -lraylib -lopengl32 -lgdi32 -lwinmm
ifdef RAYLIB
CFLAGS  += -I$(RAYLIB)/include
LDFLAGS += -L$(RAYLIB)/lib
endif

.PHONY: all noicon selftest clean

all: $(OUT)

# the icon is written by CamLab itself, so build it once without one first
camlab_tool.exe: camlab.c
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS) $(LDLIBS)

camlab.ico: camlab_tool.exe $(ICONPNG)
	./camlab_tool.exe --write-icon $@ $(ICONPNG)

camlab_res.o: camlab.ico
	echo 'GLFW_ICON ICON "camlab.ico"' > camlab.rc
	$(WINDRES) camlab.rc -O coff -o $@

$(OUT): camlab.c camlab_res.o
	$(CC) $(CFLAGS) camlab.c camlab_res.o -o $@ $(LDFLAGS) $(LDLIBS)

noicon: camlab.c
	$(CC) $(CFLAGS) $< -o $(OUT) $(LDFLAGS) $(LDLIBS)

selftest: camlab_test.exe
camlab_test.exe: camlab.c
	$(CC) $(CFLAGS) -DCAMLAB_SELFTEST $< -o $@ $(LDLIBS)

clean:
	rm -f camlab_tool.exe camlab.ico camlab.rc camlab_res.o camlab_test.exe
