"""All SEGA Rally 2 pace notes in one table: ../sr2_pace_notes.csv"""
import json, csv, os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
w = csv.writer(open(os.path.join(OUT, 'sr2_pace_notes.csv'), 'w', newline=''))
w.writerow(['course_index', 'course', 'section', 'distance_m', 'x', 'y', 'z(-gameZ)', 'condition', 'distance_call', 'delay_frames', 'request', 'vo_name', 'spoken', 'icon1', 'icon2'])
n = 0
for k in range(5):
    J = json.load(open(os.path.join(OUT, 'course%d' % k, 'gameplay.json')))
    for p in J['pace_notes']['list']:
        w.writerow([k, J['internal_name'], p['section'], p['distance_m'], *p['position'], p['condition'], p['distance_call'], p['delay_frames_before_note'], p['request'], p['vo_name'], p['spoken'], p['icon1'], p['icon2']]); n += 1
print(n, 'notes')
