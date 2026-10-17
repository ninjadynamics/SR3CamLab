/* Experimental DLL startup gate. The system-data pointer is set before
 * the native loader opens its 18 video graphs. Do not install the draw hook
 * (which can request that same loader) until those graphs exist.
 * The native boot worker sets 0x9D6F7C at 0x64D602 before loading videos
 * and clears it at 0x64D718 after finishing startup. Graph/control pointers
 * become visible before that work completes. Do not suspend/patch its
 * dependent threads mid-boot. Read only; never call COM on this worker. */
static int startup_videos_ready(GameMem *m) {
    unsigned seen = 0, i, busy;
    if (!m->read(m, 0x9D6F7Cu, &busy, 4) || busy) return 0;
    for (i = 0; i < 18; ++i) {
        unsigned handle, graph, control, object;
        if (!m->read(m, 0x72863Cu + i * 16, &handle, 4) || handle >= 20)
            return 0;
        if (seen & (1u << handle)) return 0;
        seen |= 1u << handle;
        object = 0xAD2F90u + handle * 0x16C;
        if (!m->read(m, object + 0x11C, &graph, 4) || !graph ||
            !m->read(m, object + 0x120, &control, 4) || !control)
            return 0;
    }
    return m->read(m, 0x9D6F7Cu, &busy, 4) && !busy;
}
