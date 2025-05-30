import math
import re
from bs4 import BeautifulSoup
from cloudscraper import CloudScraper, create_scraper
import requests
import os
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
from tqdm import tqdm
import subprocess
import threading
import time
import io
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page
import json
from typing import TypedDict, Union
import asyncio

INFO_DOMAIN = 'surrit.com'
NODEJS_INTERPRETER = 'bun'
UNCENSORED_TAG = '-uncensored-leak'
CURRENT_DOMAIN = 'ai'

class VideoMetadata(TypedDict):
    wigth: int
    height: int
    r_frame_rate: str
    bit_rate: str

class MissavDownloader():
    def __init__(self, is_mul_proc: bool = False):
        self.scraper: CloudScraper = create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'android',
                'desktop': False
            },
            delay=10
        )
        self._init_args()
        self.is_mul_proc = is_mul_proc
    
    async def run(self, tag: str) -> bool:
        #####   ========================== 동영상 다운로드 주소 초기화 =============================
        self._init_args()

        self.tag = tag
        
        if not self.is_mul_proc:
            print(f'Downloading "{self.tag}" start!')
        #####   ========================== 동영상 정보 획득 =============================
        try:
            url = f'https://missav.{CURRENT_DOMAIN}/ko/{tag}'
            soup = await self._get_html(url)
            if not soup:
                if not self.is_mul_proc:
                    print(f'{self.tag} video\'s page not found')
                return False
            self._from_soup_get_set_metadata(soup)

            eval_script = self._get_url_eval_func(soup)
            if not eval_script:
                if not self.is_mul_proc:
                    print(f'{self.tag} video\'s eval script not found')
                return False
            
            m3u8_uri = self._get_m3u8(eval_script)
            if not m3u8_uri:
                if not self.is_mul_proc:
                    print(f'{self.tag} video\'s m3u8_uri not found')
                return False
            
            last_idx = self._get_last_jpeg_index(m3u8_uri)
            self.download_uri = m3u8_uri.rsplit('/', 1)[0]

            self._set_output_file_name()

            #####   ========================== 동영상 RAW 다운로드 =============================
            byte_datas = self._download_video_raw(last_idx)

            #####   ========================== 동영상 저장 =============================
            step = 300 # 300 * 4초 == 1200초 == 20분
            self._create_directory()
            self._save_middle_video(byte_datas, last_idx, step)
            self._save_concated_video()
            self._del_temp_files(f'./temp/{self.output_middle_txt_name}')
            self._save_thunbmail_attatched_video()

            return True
        except:
            return True

    def _init_args(self):
        self.title = ''
        self.tag = ''
        self.download_uri = ''
        self.thumbnail_uri = ''

    def _set_output_file_name(self):
        self.output_final_mp4_name = f'{self.title}.mp4'
        self.output_middle_txt_name = f'{self.tag}.middle.txt'
        self.output_middle_mp4_name = f'{self.tag}.middle.mp4'
    
    async def _get_html(self, url: str) -> BeautifulSoup:
        sku_url = url.split('/')[-1].replace(UNCENSORED_TAG, '')
        url = url if url.endswith(UNCENSORED_TAG) else url + UNCENSORED_TAG

        attempt = 0

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0',
            'Connection': 'keep-alive',
            'Accept': '*/*',
        }
        while True:
            for _ in range(3):
                response = self.scraper.get(url, headers=headers)
                if not self.is_mul_proc:
                    print(response, url)
                if response.status_code == 404:
                    url = url[:-len(UNCENSORED_TAG)]
                    attempt = -1
                    break
                if response.status_code != 200:
                    time.sleep(0.5)
                    continue
                soup = BeautifulSoup(response.text, 'html.parser')
                sku_soup = soup.find('title').text.split()[0].lower()
                if sku_soup == sku_url:
                    return soup
            # 시도 횟수가 3회 이상이면 직접 크롤링
            attempt += 1
            if attempt >= 3 and not response.status_code in [200, 404]:
                if not self.is_mul_proc:
                    print('switch to crawling')
                bs = await self._get_html_from_crawling(url if url.endswith(UNCENSORED_TAG) else url + UNCENSORED_TAG)
                if not bs:
                    url = url.replace(UNCENSORED_TAG, '')
                    bs = await self._get_html_from_crawling(url)
                return bs
            time.sleep(1)
        

    async def _get_html_from_crawling(self, url: str) -> Union[BeautifulSoup, None]:
        ATTEMPT = 3
        async def page_goto(page: Page, url: str) -> Union[Page, None]:
            for i in range(ATTEMPT):
                try:
                    await page.goto(url, timeout=5000, wait_until="domcontentloaded")
                    if not await is_default_title(page):
                        return page
                except Exception as e:
                    if not self.is_mul_proc:
                        print(e)
            return None

        async def is_default_title(page: Page):
            if not page:
                return True
            title = await page.title()
            return title.startswith('MissAV') or title.startswith('Just')
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
                viewport={"width": 1280, "height": 800},
                locale="en-US"
            )
            page = await context.new_page()
            try:
                await page_goto(page, url)
                if await is_default_title(page):
                    raise Exception('Title Missmatched')
            except Exception as e:
                await page_goto(page, url)
                if await is_default_title(page):
                    return None
            bs = BeautifulSoup(await page.content(), 'html.parser')
            return bs
        
    def _from_soup_get_set_metadata(self, soup: BeautifulSoup) -> str | None:
        player = soup.select_one('.player')
        self.thumbnail_uri = player.get_attribute_list('data-poster')[0]
        
        self.title = soup.select_one("h1").text

    def _get_url_eval_func(self, soup: BeautifulSoup) -> str | None:
        scripts = [ script for script in soup.find_all('script') if script.get('type') == 'text/javascript' ]

        target_script = next((s for s in scripts if 'source' in s.text), None)
        if not target_script:
            return None

        match = re.search(r'eval.+', target_script.text)
        if not match:
            return None
        eval_code = match.group(0)

        sources = re.findall(r'source\d*', eval_code)

        setup = f"let {','.join(sources)};"
        output = f"console.log({','.join(sources)});"
        eval_script = f"{setup}({eval_code});{output}"

        return re.sub(r'\s{2,}', '', eval_script).replace('\n', '')
    
    def _get_m3u8(self, eval_script: str) -> str | None:
        result = subprocess.run([NODEJS_INTERPRETER, '-e', eval_script], capture_output=True, text=True)
        outputs = result.stdout.split()
        
        filtered = [ x for x in set(outputs) if 'video' in x ]
        return filtered[0] if filtered else None
    
    def _get_last_jpeg_index(self, m3u8_uri: str) -> int:
        response = requests.get(m3u8_uri)
        m3u8_list = response.text.strip().split('\n')
        return int(re.search(r'\d+', m3u8_list[-2]).group(0))
    
    def _download_video_raw(self, last_idx: int) -> list[bytes]:
        byte_datas = [b''] * (last_idx+1)
        with ThreadPoolExecutor(32 if self.is_mul_proc else 128) as executor:
            futures = [ executor.submit(self._fetch_video, byte_datas, idx) for idx in range(last_idx + 1) ]
            tqdm_loop = as_completed(futures) if self.is_mul_proc else tqdm(as_completed(futures), total=len(futures), desc=f"Downloading Raw    - {self.tag}")
            for _ in tqdm_loop:
                pass
        return byte_datas
    
    def _fetch_video(self, byte_datas: list[bytes], idx: int) -> None:
        response = requests.get(f'{self.download_uri}/video{idx}.jpeg')
        byte_datas[idx] = response.content
    
    def _create_directory(self):
        if not os.path.exists('./temp'):
            os.makedirs('./temp', exist_ok=True)
        if not os.path.exists('./output'):
            os.makedirs('./output', exist_ok=True)

    def _save_middle_video(self, byte_datas: list, last_idx: int, step: int):
        def save(byte_datas: list, tag: str, idx: int):
            def read_stderr(stream):
                try:
                    if stream is None:
                        return
                    for line in io.TextIOWrapper(stream, encoding='utf-8'):
                        pass
                except Exception as e:
                    pass

            nonlocal temp_file_paths
            temp_file_name = f'{tag}_{idx}.mp4'
            temp_file_path = f'./temp/{temp_file_name}'
            # 오류나면 -c:v libx264 -c:a aac 로 변경
            ffmpeg_command = [
                'ffmpeg',
                '-y',
                '-i', '-',
                '-c', 'copy',
                '-f', 'mp4',
                temp_file_path
            ]
            process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE)

            # if process.stderr:
            #     threading.Thread(target=read_stderr, args=(process.stderr,), daemon=True).start()

            for chunk in byte_datas:
                process.stdin.write(chunk)
                process.stdin.flush()
            _, stderr = process.communicate()

            try:
                if process.returncode != 0:
                    if not self.is_mul_proc:
                        print(f"Error occurred: {stderr.decode()}", flush=True, end='\n\n')
                    return
            finally:
                del stderr, process
            
            temp_file_paths[idx] = f"file '{temp_file_name}'"
        #####   20분씩 자른 동영상 저장
        max_step = math.ceil((last_idx+1) / step)
        temp_file_paths = [None] * max_step
        with ThreadPoolExecutor(8) as executor:
            futures = [ executor.submit(save, byte_datas[step*idx:step*(idx+1)], self.tag, idx) for idx in range(max_step) ]
            tqdm_loop = as_completed(futures) if self.is_mul_proc else tqdm(as_completed(futures), total=len(futures), desc=f"Processing  Raw    - {self.tag}")
            for _ in tqdm_loop:
                pass
        
        #####   합치기 위한 동영상 목록
        with open(f'./temp/{self.output_middle_txt_name}', 'w') as f:
            f.write("\n".join(temp_file_paths))

    def _save_concated_video(self):
        command = [
            'ffmpeg',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', f'./temp/{self.output_middle_txt_name}',
            '-c', 'copy',
            f'./temp/{self.output_middle_mp4_name}'
        ]
        result = subprocess.run(command, stderr=subprocess.PIPE)

        if result.returncode != 0:
            if not self.is_mul_proc:
                print(f"Error occurred: {result.stderr.decode()}")
        else:
            if not self.is_mul_proc:
                print(f'Save "{self.output_middle_mp4_name}" finished!')

    def _save_thunbmail_attatched_video(self):
        thumb_response = requests.get(self.thumbnail_uri)
        cmd = [
            'ffmpeg',
            '-y',
            '-i', f'./temp/{self.output_middle_mp4_name}',
            '-i', '-',
            '-map', '0',
            '-map', '1',
            '-c', 'copy',
            "-disposition:v:1", "attached_pic",
            f'./output/{self.output_final_mp4_name}'
        ]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        process.communicate(input=thumb_response.content)

        os.remove(f'./temp/{self.output_middle_mp4_name}')

        if not self.is_mul_proc:
            print(f'Save "{self.output_final_mp4_name}" finished!')

    def _del_temp_files(self, file_path: str):
        prefix = '/'.join(file_path.split('/')[:-1])
        with open(file_path, 'r') as f:
            files = [ 
                filename.strip().replace("'", '').split()[1] 
                for filename in f.readlines() if filename.strip() 
            ]
        for file in files:
            os.remove(f'{prefix}/{file}')
        os.remove(file_path)

def _proc(tag: str, is_mul_proc: bool):
    return asyncio.run(MissavDownloader(is_mul_proc).run(tag))
    
def mulProcDownload(tags: list[str], failed_tags: list[str]):

    with ProcessPoolExecutor(4) as executor:
        future_to_tag = {
            executor.submit(_proc, tag, True): tag
            for tag in tags
        }
        for future in tqdm(as_completed(future_to_tag), total=len(future_to_tag)):
            try:
                if not future.result():
                    failed_tags.append(future_to_tag[future])
            except Exception as e:
                print(f'Error occured: {e}')

def singProcDownload(tags: list[str], failed_tags: list[str]):
    for tag in tags:
        succeed = _proc(tag, False)
        if not succeed:
            failed_tags.append(tag)

if __name__ == "__main__":
    download_file_path = './download-list.txt'
    failed_tags: list[str] = []
    
    with open(download_file_path, 'r') as f:
        lines = f.readlines()
    urls = list(dict.fromkeys(
        re.sub(r'(?:dm\d+/|#[\w\-]+)', '', line.strip().split()[-1])
        for line in lines if line.strip()
    ))
    tags = [ url.split('/')[-1].replace(UNCENSORED_TAG, '') for url in urls ]

    # if len(urls) == 0:
    #     exit(-1)
    
    unique_tags = list(set(tags))
    unique_tags = sorted(unique_tags)

    with open('test.txt', 'w') as f:
        f.writelines('\n'.join(unique_tags))

    unique_tags = ["npjs-069"]

    mulProcDownload(unique_tags, failed_tags)

    # unique_tags = ["kbj-25022269"] # 21분짜리 데이터

    # asyncio.run(singProcDownload(unique_tags, failed_tags))

    with open(download_file_path, 'w') as f:
        f.write('')
    with open('failed-tags.txt', 'w') as f:
        f.write('\n'.join(failed_tags))