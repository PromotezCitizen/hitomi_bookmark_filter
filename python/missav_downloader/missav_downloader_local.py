import math
import re
from typing import TypedDict
from bs4 import BeautifulSoup
import cloudscraper
import requests
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import subprocess
import gc

INFO_DOMAIN = 'surrit.com'

class PageMetadata(TypedDict):
    videoid: str
    tag: str
    title: str

class VideoMetadata(TypedDict):
    frame: str
    last_idx: int

class VideoInfo(PageMetadata, VideoMetadata):
    pass

class MissavDownloader():
    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
    
    def run(self, url: str):
        #####   ========================== 동영상 정보 획득 =============================
        video_info = self.get_video_info(url)

        #####   ========================== 동영상 RAW 다운로드 =============================
        byte_datas = self.download_video_raw(video_info)

        #####   ========================== 동영상 저장 =============================
        step = 300 # 300 * 4초 == 1200초 == 20분
        self._create_directory()
        self.save_middle_video(video_info, byte_datas, step)
        self.save_concated_video(video_info)

    def get_video_info(self, url: str) -> VideoInfo:
        page_metadata: PageMetadata = self._get_video_id_and_tag_and_title(url)
        video_metadata: VideoMetadata = self._get_available_video_info(page_metadata['videoid'])
        
        return { **page_metadata, **video_metadata }

    def _get_video_id_and_tag_and_title(self, url: str) -> PageMetadata:
        while True:
            response = self.scraper.get(url)

            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.find('title')
            if title.text != 'Just a moment...':
                title = re.sub(r'[<>:"/\\|?*]+', '', title.text)
                break

        tag = url.split('/')[-1]
        tag = '-'.join(tag.split('-', 3)[:3] if tag.startswith('fc2') else tag.split('-', 2)[:2])

        for script in soup.find_all('script'):
            attr_list = script.get_attribute_list('type')
            if len(attr_list) > 0 and attr_list[0] == 'text/javascript':
                script: str = script.text
                matched = re.search(r'urls:\s*\[(.*?)\]', script, re.DOTALL)
                if matched:
                    videoid = re.search(r'"https?://[^/]+/([^/]+)', matched.group(0).replace('\\/', '/')).group(1)
                    break

        return PageMetadata(videoid=videoid, tag=tag, title=title)

    def _get_available_video_info(self, video_id) -> VideoMetadata:
        frames = ['720p', '480p', '360p']
        for frame in frames:
            response = requests.get(f'https://{INFO_DOMAIN}/{video_id}/{frame}/video.m3u8')
            if response.status_code < 400:
                break

        last_info = response.text.strip().splitlines()[-2]
        last_idx = int(re.findall(r'\d+', last_info)[0])
        return VideoMetadata(frame=frame, last_idx=last_idx)

    def download_video_raw(self, video_info: VideoInfo):
        last_idx = video_info['last_idx']
        byte_datas = [b''] * (last_idx+1)
        with ThreadPoolExecutor(16) as executor:
            futures = [ executor.submit(self._fetch_video, video_info, byte_datas, idx) for idx in range(last_idx + 1) ]
            
            for _ in tqdm(as_completed(futures), total=len(futures), desc=f"Downloading Raw    - {video_info['tag']}"):
                pass

        return byte_datas

    def _fetch_video(self, video_info: VideoInfo, byte_datas: list, idx: int):
        response = requests.get(f'https://{INFO_DOMAIN}/{video_info["videoid"]}/{video_info["frame"]}/video{idx}.jpeg')
        byte_datas[idx] = response.content

    def save_middle_video(self, video_info: VideoInfo, byte_datas: list, step: int):
        tag = video_info['tag']
        last_idx = video_info['last_idx']
        #####   20분씩 자른 동영상 저장
        temp_file_paths = []
        max_step = math.ceil((last_idx+1) / step)
        for i in tqdm(range(max_step), desc=f"Processing Sub mp4 - {tag}"):
            temp_file_name = f'{tag}_{i}.mp4'
            temp_file_path = f'./temp/{temp_file_name}'
            ffmpeg_command = [
                'ffmpeg', 
                '-y', 
                '-hwaccel', 'cuda', 
                '-i', '-', 
                '-c:v', 'h264_nvenc', 
                '-c:a', 'copy', 
                '-f', 'mp4',
                temp_file_path
            ]
            process = subprocess.Popen(
                ffmpeg_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            process.stdin.write(b''.join(byte_datas[step*i:step*(i+1)]))

            stdout, stderr = process.communicate()

            try:
                if process.returncode != 0:
                    print(f"Error occurred: {stderr.decode()}")
                    break
            finally:
                del process, stdout, stderr
                gc.collect()

            temp_file_paths.append(f"file '{temp_file_name}'")

        #####   합치기 위한 동영상 목록
        with open(f'./temp/{tag}.txt', 'w') as f:
            f.write("\n".join(temp_file_paths))

    def save_concated_video(self, video_info: VideoInfo):
        tag = video_info['tag']
        title = video_info['title']
        result = subprocess.run([
            'ffmpeg',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', f'./temp/{tag}.txt',
            '-c', 'copy',
            f'./output/{title}.mp4'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        if result.returncode != 0:
            print(f"Error occurred: {result.stderr.decode()}")
        else:
            with open(f'./temp/{tag}.txt', 'r') as f:
                files = [ filename.strip().split("'")[1] for filename in f.readlines() if filename.strip() ]
            for file in files:
                if not file.startswith('.'):
                    os.remove(f'./temp/{file}')
                else:
                    os.remove(file)
            os.remove(f'./temp/{tag}.txt')

    def _create_directory(self):
        if not os.path.exists('./temp'):
            os.makedirs('./temp', exist_ok=True)
        if not os.path.exists('./output'):
            os.makedirs('./output', exist_ok=True)

if __name__ == "__main__":
    url = "https://missav.ai/ko/kbj-24100858"
    downloader = MissavDownloader()
    downloader.run(url)

    # subprocess.Popen(['ffmpeg', '-hwaccels'])
