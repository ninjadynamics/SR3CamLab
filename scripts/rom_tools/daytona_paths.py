"""Paths used by the daytona_*.py tools. Nothing here is SEGA data.

SCRATCH   session scratch folder (ROM chips unpacked from daytona.zip, region images, work files)
COURSES   where the extracted courses are written (outside the git repository; never committed)
Override either with the environment variables DAYTONA_SCRATCH / DAYTONA_COURSES.
"""
import os

ZIP = r"F:/Emulators/SEGA Arcade/Model 2/Games/daytona.zip"
SCRATCH = os.environ.get("DAYTONA_SCRATCH", r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/daytona")
ROMS = SCRATCH + "/roms"
OUT = SCRATCH + "/out"
WORK = SCRATCH + "/work"
COURSES = os.environ.get("DAYTONA_COURSES", r"F:/Jogos/SEGA Rally 3/SR3 track format/classic/courses/daytona")
