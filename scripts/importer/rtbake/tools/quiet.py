"""Run a Python script out of the game's way: on the efficiency cores only (logical CPUs 16 - 31; the launcher keeps the game on 0, 2, 4, 6) and
below normal priority. Whatever it starts inherits both.   python quiet.py <script.py> [arguments ...]"""
import sys, ctypes, runpy, os
k = ctypes.windll.kernel32; h = k.GetCurrentProcess(); k.SetProcessAffinityMask(h, ctypes.c_size_t(0xFFFF0000)); k.SetPriorityClass(h, 0x4000)
os.environ.setdefault('OMP_NUM_THREADS', '16'); sys.argv = sys.argv[1:]; sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0]))); runpy.run_path(sys.argv[0], run_name='__main__')
