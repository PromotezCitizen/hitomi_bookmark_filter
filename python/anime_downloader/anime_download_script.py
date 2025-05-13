import math
from typing import TypedDict
import requests
import json
import re
from utils import Downloader

class GalleryInfo(TypedDict):
    title: str
    videofilename: str
    galleryurl: str

USERAGEN='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
@Downloader.register
class DownloaderHitomiAnime(Downloader):
    type = 'hitomianime'
    URLS = ['hitomi.la/anime']

    def init(self) -> None:
        pass

    def read(self) -> None:
        hitomi_path = self.url
        galleryid = self.get_galleryid(hitomi_path)
        galleryinfo = self.get_galleryinfo(galleryid)
        self.download_video(galleryinfo['videofilename'], hitomi_path)

    def run(self, hitomi_path: str):
        galleryid = self.get_galleryid(hitomi_path)
        galleryinfo = self.get_galleryinfo(galleryid)
        self.download_video(galleryinfo['videofilename'], hitomi_path)

    def get_galleryid(self, hitomi_path: str) -> str:
        if not hitomi_path.endswith('.html'):
            hitomi_path = hitomi_path[:hitomi_path.rfind('#')]
        
        hitomi_path = hitomi_path[:hitomi_path.rfind('.html')].strip()
        return re.search(r'(\d+)$', hitomi_path).group(0)
    
    def get_galleryinfo(self, id: str) -> GalleryInfo:
        galleryinfo_path = f'https://ltn.gold-usergeneratedcontent.net/galleries/{id}.js'
        response = requests.get(galleryinfo_path)
        body = response.text
        data: GalleryInfo = json.loads(body[body.find('{'):])
        return data

    def download_video(self, videofilename: str, hitomi_path: str):
        url = f'https://streaming.gold-usergeneratedcontent.net/videos/{videofilename}'
        response = requests.get(url, headers={
            'Range': 'bytes=0-0',
            'Referer': hitomi_path
        })
        content_range = response.headers['Content-Range']
        max_chunk_length = int(content_range.split('/')[1])
        chunk_size = 10_000_000
        
        with open(f'animes/{videofilename}', 'wb') as f:
            for i in range(math.ceil(max_chunk_length / chunk_size)):
                range_header = f"bytes={i*chunk_size}-{min((i+1)*chunk_size-1, max_chunk_length-1)}"
                print(range_header)
                response = requests.get(url, headers={
                    'Referer': hitomi_path,
                    'Range': range_header
                })
                if response.status_code in [200, 206]:
                    f.write(response.content)
                else:
                    break

