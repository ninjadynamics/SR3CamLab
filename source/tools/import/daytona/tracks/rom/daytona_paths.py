"""Paths used by the daytona_*.py tools. Nothing here is SEGA data.

SCRATCH   working folder (default <work>/tmp/daytona) (ROM chips unpacked from daytona.zip, region images, work files)
COURSES   where the extracted courses are written (<data>/classic/courses/daytona) (outside the git repository; never committed)
Override either with the environment variables DAYTONA_SCRATCH / DAYTONA_COURSES.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "core"))
import common                                   # tools/import/settings.json

ZIP = common.rom_zip("daytona")
SCRATCH = os.environ.get("DAYTONA_SCRATCH", os.path.join(common.TMP, "daytona"))
ROMS = SCRATCH + "/roms"
OUT = SCRATCH + "/out"
WORK = SCRATCH + "/work"
COURSES = os.environ.get("DAYTONA_COURSES", os.path.join(common.CLASSIC, "courses", "daytona"))
