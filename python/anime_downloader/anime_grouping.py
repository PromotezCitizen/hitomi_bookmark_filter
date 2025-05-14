import os
import re
from collections import defaultdict
import shutil

directory = 'animes'

grouped_files = defaultdict(list)
episode_pattern = r'(?i)(?<!\w)(ep|episode|the|\-|_)(?!\w)'
hwa_pattern = r'\b(\d+)\b'

mp4_files = [ scanned.name for scanned in os.scandir(directory) if scanned.is_file() and scanned.name.endswith('.mp4') ]
for filename in mp4_files:
    matched_eposode_list = list(re.finditer(episode_pattern, filename))
    if len(matched_eposode_list) == 0:
        matched_hwa_list = list(re.finditer(hwa_pattern, filename))
        if len(matched_hwa_list) == 0:
            dirname = filename[:-4]
        else:
            dirname = filename[:matched_hwa_list[-1].span(0)[0]].strip()
    else:
        dirname = filename[:matched_eposode_list[0].span(0)[0]].strip()
        matched_hwa_list = list(re.finditer(hwa_pattern, dirname))
        if len(matched_hwa_list) != 0:
            dirname = dirname[:matched_hwa_list[-1].span(0)[0]].strip()

    dirname = ' '.join(dirname.split(' ', 3)[:3])
    grouped_files[dirname].append(filename)

for dirname, filenames in grouped_files.items():
    target_dir = os.path.join('animes', dirname)
    os.makedirs(target_dir, exist_ok=True)
    for filename in filenames:
        src = os.path.join('animes', filename)
        dst = os.path.join(target_dir, filename)
        shutil.move(src, dst)