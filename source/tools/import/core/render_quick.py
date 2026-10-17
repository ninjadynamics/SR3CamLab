"""Quick look while tuning: python render_quick.py <step> <prefix> view view ...  (centre-line indices, see bl_render.py)"""
import sys
import preview_obj, render_all as RA
if __name__ == '__main__':
    RA.render(preview_obj.main(sys.argv[1]), sys.argv[2], [int(v) for v in sys.argv[3:]])
