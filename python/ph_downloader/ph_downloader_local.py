from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests
from bs4 import BeautifulSoup
import re
import json
import subprocess
from tqdm import tqdm
import os
import io

# response = requests.get('https://www.pornhub.com/model/notsoamateur/videos?o=mr', cookies={
#     'accessAgeDisclaimerPH': '1',
# })

MOST_RESCENT = 'o=mr'
VIDEOS_PER_MODEL_PAGE = 40
VIDEOS_PER_CHANNEL_PAGE = 36
def download_from_channel(url: str):
    # 추후 urllib으로 변경
    parsed_url = url.split('/')[:5]
    url = '/'.join(parsed_url) + '/videos'
    if parsed_url[3] == 'channels':
        url += '?'
        video_container_selector = 'showAllChanelVideos'
    elif parsed_url[3] == 'pornstar':
        url += '/upload?o=mr'
        video_container_selector = 'moreData'
    elif parsed_url[3] == 'model':
        url += '?o=mr'
        video_container_selector = 'mostRecentVideosSection'

    channel_name = ' '.join(word.capitalize() for word in parsed_url[4].split('-'))
    page = 1
    channel_video_hrefs = []
    while True:
        response = requests.get(
            url + f'&page={page}',
            cookies={
                'accessAgeDisclaimerPH': '1',
            })
        bs = BeautifulSoup(response.text, 'html.parser')
        with open('asdf.html', 'w', encoding='utf-8') as f:
            f.write(response.text)

        video_container = bs.find('ul', {
            "id": video_container_selector
        })
        if not video_container:
            video_container = bs.find('ul', {
                "id": 'moreData'
            })
            if not video_container:
                break
        
        channel_video_hrefs.extend([ li.select_one('a').get('href') for li in video_container.select('li') ])
        page += 1

    channel_name = f'[{parsed_url[3].capitalize()}] {channel_name}'
    
    output_folder_path = f'./output/{channel_name}'
    if not os.path.exists(output_folder_path):
        os.makedirs(output_folder_path, exist_ok=True)

    if len(channel_video_hrefs) == 0:
        return

    for href in tqdm(channel_video_hrefs, total=len(channel_video_hrefs), desc=f"Downloading Raw - {channel_name}"):
        download_from_video_page('https://www.pornhub.com' + href, channel_name)

def fetch_video(byte_datas: list[bytes], idx: int, url: str):
    response = requests.get(url)
    byte_datas[idx] = response.content

def download_from_video_page(url: str, channel: str = ''):
    response = requests.get(
        url, 
        cookies={
            'accessAgeDisclaimerPH': '1',
        })

    bs = BeautifulSoup(response.text, 'html.parser')
    title = bs.select_one('.title-container').text.strip()

    js_scripts = [ 
        script.text
        for script in bs.select_one('#player').select('script')
        if script.get('type')  == 'text/javascript'
    ]
    del bs

    flashvars_script = next(
        (script for script in js_scripts if 'flashvars' in script),
        ''
    )

    if flashvars_script == '':
        print('Error! Script is not found')
        return

    flashvar_js_obj = re.search(r'var\s+\w+\s*=\s*(\{.*?\});', flashvars_script)
    flashvar_obj = json.loads(flashvar_js_obj.group(1))

    with open('test.json', 'w', encoding='utf-8') as f:
        json.dump(flashvar_obj, f)

    video_id = flashvar_obj.get('link_url', '').split('?')[-1].split('=')[-1]
    thumbnail_url = flashvar_obj.get('image_url', '')


    qualities = sorted(flashvar_obj.get('defaultQuality', [720]), reverse=True)
    for quality in qualities:
        max_quality_vid_download_uri: str = next(
            filter(
                lambda x: x['quality'] == f'{quality}', 
                flashvar_obj.get('mediaDefinitions', [{}])
            ),
            ''
        ).get('videoUrl', '')

        ## get chunk video data m3u8u
        master_m3u8_response = requests.get(max_quality_vid_download_uri)
        if master_m3u8_response.status_code == 200:
            break
    m3u8_uri = re.sub(r'^#.*$', '', master_m3u8_response.text, flags=re.MULTILINE).strip()

    question_index = max_quality_vid_download_uri.index('?')
    splitted_uri = max_quality_vid_download_uri[:question_index]
    base_uri = '/'.join(splitted_uri.split('/')[:-1])

    index_m3u8_response = requests.get(f'{base_uri}/{m3u8_uri}')
    ts_uris = [ 
        uri 
        for uri in re.sub(r'^#.*$', '', index_m3u8_response.text, flags=re.MULTILINE).strip().split('\n') 
        if uri
    ]

    ## download chunk video datas
    ts_datas = [None] * len(ts_uris)
    with ThreadPoolExecutor(128) as executor:
        futures = [ 
            executor.submit(fetch_video, ts_datas, idx, f'{base_uri}/{ts_uri}')
            for idx, ts_uri in enumerate(ts_uris)
        ]
        for _ in as_completed(futures) if channel else tqdm(as_completed(futures), total=len(futures), desc=f"Downloading Raw - {video_id}"):
            pass

    ## concat chunk videos
    middle_file_name = f'{video_id}.middle.mp4'
    middle_cmd = [
        'ffmpeg',
        '-y',
        '-i', '-',
        '-c', 'copy',
        f'./temp/{middle_file_name}'
    ]
    middle_process = subprocess.Popen(
        middle_cmd, 
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    if middle_process.stderr:
      threading.Thread(target=read_stderr, args=(middle_process.stderr,), daemon=True).start()

    for ts_data in ts_datas:
        middle_process.stdin.write(ts_data)
    middle_process.communicate()

    ## concat with thumbnail
    output_file_name = f'{title} ({video_id}).mp4'
    thumbnail_response = requests.get(thumbnail_url)
    thumb_cmd = [
        'ffmpeg',
        '-y',
        '-i', f'./temp/{middle_file_name}',
        '-i', '-',
        '-map', '0',
        '-map', '1',
        '-c', 'copy',
        '-c', 'copy',
        "-disposition:v:1", "attached_pic",
        f'./output/{channel}/{output_file_name}' if channel else f'./output/{output_file_name}'
    ]
    thumb_process = subprocess.Popen(thumb_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    thumb_process.communicate(input=thumbnail_response.content)

    os.remove(f'./temp/{middle_file_name}')

def read_stderr(stream):
    try:
        if stream is None:
            return
        for line in io.TextIOWrapper(stream, encoding='utf-8'):
            pass
    except Exception as e:
        pass

if __name__ == "__main__":
    download_from_channel('https://www.pornhub.com/channels/miley-weasel')
    # download_from_channel('https://www.pornhub.com/model/notsoamateur')