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

INFO_DOMAIN = 'surrit.com'
NODEJS_INTERPRETER = 'bun'
UNCENSORED_TAG = '-uncensored-leak'

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
    
    def run(self, url: str):
        #####   ========================== 동영상 다운로드 주소 초기화 =============================
        self._init_args()

        self.tag = url.split('/')[-1].replace('-uncensored-leak', '')
        if not self.is_mul_proc:
            print(f'Downloading {self.tag} start!')
        #####   ========================== 동영상 정보 획득 =============================
        soup = self._get_html(url)
        self.title = soup.find('title').text

        eval_script = self._get_url_eval_func(soup)
        if not eval_script:
            return
        
        m3u8_uri = self._get_m3u8(eval_script)
        if not m3u8_uri:
            return
        
        last_idx = self._get_last_jpeg_index(m3u8_uri)
        self.download_uri = m3u8_uri.rsplit('/', 1)[0]

        #####   ========================== 동영상 RAW 다운로드 =============================
        byte_datas = self._download_video_raw(last_idx)

        #####   ========================== 동영상 저장 =============================
        step = 300 # 300 * 4초 == 1200초 == 20분
        self._create_directory()
        self._save_middle_video(byte_datas, last_idx, step)
        self._save_concated_video()

    def _init_args(self):
        self.title = ''
        self.last_idx = -1
        self.tag = ''
        self.download_uri = None
    
    def _get_html(self, url: str) -> BeautifulSoup:
        sku_url = url.split('/')[-1].replace(UNCENSORED_TAG, '')
        url = url if url.endswith(UNCENSORED_TAG) else url + UNCENSORED_TAG

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0',
            'Connection': 'keep-alive',
            'Accept': '*/*',
        }
        while True:
            for attemp in range(3):
                response = self.scraper.get(url, headers=headers)
                print(response, url)
                if response.status_code == 404:
                    url = url[:-len(UNCENSORED_TAG)]
                    continue
                if response.status_code != 200:
                    continue
                soup = BeautifulSoup(response.text, 'html.parser')
                sku_soup = soup.find('title').text.split()[0].lower()
                if sku_soup == sku_url:
                    return soup
            time.sleep(1)
    
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
            process = subprocess.Popen(
                ffmpeg_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            if process.stderr:
                threading.Thread(target=read_stderr, args=(process.stderr,), daemon=True).start()

            for chunk in byte_datas:
                process.stdin.write(chunk)
                process.stdin.flush()
            process.stdin.close()
            
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
        with open(f'./temp/{self.tag}.txt', 'w') as f:
            f.write("\n".join(temp_file_paths))

    def _save_concated_video(self):
        result = subprocess.run([
            'ffmpeg',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', f'./temp/{self.tag}.txt',
            '-c', 'copy',
            f'./output/{re.sub(r'[\\/:"*?<>|]+', '', self.title)}.mp4'
        ], stderr=subprocess.PIPE)

        if result.returncode != 0:
            if not self.is_mul_proc:
                print(f"Error occurred: {result.stderr.decode()}")
        else:
            with open(f'./temp/{self.tag}.txt', 'r') as f:
                files = [ filename.strip().replace("'", '').split()[1] for filename in f.readlines() if filename.strip() ]
            for file in files:
                if not file.startswith('.'):
                    os.remove(f'./temp/{file}')
                else:
                    os.remove(file)
            os.remove(f'./temp/{self.tag}.txt')
            if not self.is_mul_proc:
                print(f'Save {self.tag} finished!')

def mulProcDownload(urls: list[str]):
    def _proc(url: str):
        MissavDownloader(is_mul_proc=True).run(url)

    with ProcessPoolExecutor(4) as executor:
        future_to_tag = {
            executor.submit(_proc, url): url.split('/')[-1].replace(UNCENSORED_TAG, '')
            for url in urls
        }
        for future in tqdm(as_completed(future_to_tag), total=len(future_to_tag)):
            try:
                future.result()
            except Exception as e:
                print(f'Error occured: {e}')

def singProcDownload(urls: list[str]):
    for url in urls:
        MissavDownloader().run(url)
    
def normalize_url_get_host(url):
    if not re.match(r'^https?://', url):
        url = 'https://' + url
    parsed = urlparse(url)
    return parsed.scheme + '://' + parsed.netloc

if __name__ == "__main__":
    download_file_path = './download-list.txt'
    with open(download_file_path, 'r') as f:
        urls = list(dict.fromkeys( line.strip() for line in f.readlines() if line.strip() ))

    if len(urls) == 0:
        exit(-1)
    
    hosts = list(set(normalize_url_get_host(url) for url in urls))

    error_hosts = []
    for host in hosts:
        try:
            requests.get(host)
        except requests.exceptions.ConnectionError as ce:
            error_hosts.append(host)
    if len(error_hosts) > 0:
        print('접근 불가능한 링크')
        error_hosts = map(lambda x: f'- {x}', error_hosts)
        print('\n'.join(error_hosts))

    # mulProcDownload(urls)

    singProcDownload(urls)

    with open(download_file_path, 'w') as f:
        f.write('')
