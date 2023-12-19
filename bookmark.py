import json
from urllib.parse import urlparse
import re
import requests
import struct
import hashlib
from datetime import datetime
import time
from functools import partial

import sys

nozomiextension = '.nozomi'
domain = 'ltn.hitomi.la'
compressed_nozomi_prefix = 'n'

max_node_size = 464
B = 16

search_serial = 0
search_result_index = -1


tag_index_version, galleries_index_version, languages_index_version, nozomiurl_index_version = '', '', '', ''
galleriesdir, index_dir, galleries_index_dir, languages_index_dir, nozomiurl_index_dir = 'galleries', 'tagindex', 'galleriesindex', 'languagesindex', 'nozomiurlindex'

def decodeURIComponent(uri: str) -> list[str]:
    return re.sub(r'^\?', '', uri.replace("%3A", ":").replace("%20", " "))

def makeTerms(text: str) -> list[str]:
    terms = re.split(r'\s+', text.lower().strip())
    negative_terms, positive_terms = [], []

    for term in terms:
        term = re.sub(r'_', ' ', term)
        if re.match(r'^-', term):
            negative_terms.append(re.sub(r'^-', '', term))
        else:
            positive_terms.append(term)

    return positive_terms, negative_terms

def get_index_version(name = 'tagindex'):
    while True:
        url = f"https://{domain}/{name}/version?_={datetime.now()}"
        response = requests.get(url)

        if response.status_code == 200 and response.text:
            tag_index_version = response.text
            return
        
def get_galleryids_from_nozomi(area, tag, language):
    nozomi_address = 'https://'+'/'.join( [ domain, compressed_nozomi_prefix, '-'.join( [ tag, language ] ) ] )+nozomiextension
    if area:
        nozomi_address = 'https://'+'/'.join( [ domain, compressed_nozomi_prefix, area, '-'.join( [ tag, language ] ) ] )+nozomiextension

    res = []
    response = requests.get(nozomi_address)
    if response.status_code == 200:
        array_buffer = response.content
        total = len(array_buffer) // 4

        for i in range(total):
            res.append(struct.unpack('>i', array_buffer[i*4:(i+1)*4])[0])

    return res

def get_galleryids_for_query(query):
    query = query.replace('_', ' ')
    
    if ':' in query:
        sides = query.split(':')
        ns = sides[0]
        tag = sides[1]
        
        area = ns
        language = 'all'
        if ns == 'female' or ns == 'male':
            area = 'tag'
            tag = query
        elif ns == 'language':
            area = None
            language = tag
            tag = 'index'
        
        return get_galleryids_from_nozomi(area, tag, language)
    
    key = hash_term(query)
    field = 'galleries'
    
    node = get_node_at_address(field, 0)
    if not node:
        return []
    
    data = B_search(field, key, node)
    if not data:
        return []
    
    return get_galleryids_from_data(data)

def hash_term(term):
    sha_signature = hashlib.sha256(term.encode()).digest()
    return sha_signature[:4]

def get_node_at_address(field, address, serial=None):
    if serial:  # not used in the python code
        pass

    if field == 'galleries':
        url = f'https://{domain}/{galleries_index_dir}/galleries.{galleries_index_version}.index'
    elif field == 'languages':
        url = f'https://{domain}/{languages_index_dir}/languages.{languages_index_version}.index'
    elif field == 'nozomiurl':
        url = f'https://{domain}/{nozomiurl_index_dir}/nozomiurl.{nozomiurl_index_version}.index'
    else:
        url = f'https://{domain}/{index_dir}/{field}.{tag_index_version}.index'

    nodedata = get_url_at_range(url, [address, address+max_node_size-1])
    return decode_node(nodedata) if nodedata else None

def compare_arraybuffers(dv1, dv2):
    return (dv1 > dv2) - (dv1 < dv2)

def locate_key(key, node):
    cmp_result = -1
    for i, node_key in enumerate(node.keys):
        cmp_result = compare_arraybuffers(key, node_key)
        if cmp_result <= 0:
            break
    return cmp_result == 0, i

def is_leaf(node):
    return all(subnode_address == 0 for subnode_address in node.subnode_addresses)

def B_search(field, key, node, serial=None):
    if serial:  # not used in the python code
        pass

    if not node or not node.keys:
        return False

    there, where = locate_key(key, node)
    if there:
        return node.datas[where]
    elif is_leaf(node):
        return False
    
    if node.subnode_addresses[where] == 0:
        print('non-root node address 0')
        return False

    return B_search(field, key, get_node_at_address(field, node.subnode_addresses[where]))

def get_galleryids_from_data(data):
    if not data:
        return []

    url = f'https://{domain}/{galleries_index_dir}/galleries.{galleries_index_version}.data'
    offset, length = data
    if length > 100000000 or length <= 0:
        print(f"length {length} is too long")
        return []

    inbuf = get_url_at_range(url, [offset, offset+length-1])
    if not inbuf:
        return []

    galleryids = []
    pos = 0
    view = struct.unpack(">i", inbuf[pos:pos+4])[0]
    pos += 4
    number_of_galleryids = view

    expected_length = number_of_galleryids * 4 + 4
    if number_of_galleryids > 10000000 or number_of_galleryids <= 0:
        print(f"number_of_galleryids {number_of_galleryids} is too long")
        return []
    elif len(inbuf) != expected_length:
        print(f"inbuf.byteLength {len(inbuf)} !== expected_length {expected_length}")
        return []

    for i in range(number_of_galleryids):
        galleryids.append(struct.unpack(">i", inbuf[pos:pos+4])[0])
        pos += 4

    return galleryids

def get_url_at_range(url, range):
    headers = {'Range': f'bytes={range[0]}-{range[1]}'}
    response = requests.get(url, headers=headers)

    if response.status_code in [200, 206]:
        return bytearray(response.content)
    else:
        raise Exception(f'get_url_at_range({url}, {range}) failed, status_code: {response.status_code}')

def decode_node(data):
    node = {
        'keys': [],
        'datas': [],
        'subnode_addresses': [],
    }

    pos = 0
    number_of_keys = struct.unpack(">i", data[pos:pos+4])[0]
    pos += 4

    keys = []
    for _ in range(number_of_keys):
        key_size = struct.unpack(">i", data[pos:pos+4])[0]
        pos += 4

        if not key_size or key_size > 32:
            print("fatal: !key_size || key_size > 32")
            return

        keys.append(data[pos:pos+key_size])
        pos += key_size

    number_of_datas = struct.unpack(">i", data[pos:pos+4])[0]
    pos += 4

    datas = []
    for _ in range(number_of_datas):
        offset = struct.unpack(">Q", data[pos:pos+8])[0]
        pos += 8

        length = struct.unpack(">i", data[pos:pos+4])[0]
        pos += 4

        datas.append([offset, length])

    number_of_subnode_addresses = B+1
    subnode_addresses = []
    for _ in range(number_of_subnode_addresses):
        subnode_address = struct.unpack(">Q", data[pos:pos+8])[0]
        pos += 8

        subnode_addresses.append(subnode_address)

    node['keys'] = keys
    node['datas'] = datas
    node['subnode_addresses'] = subnode_addresses

    return node

def get_negative_tags():
    with open('negative_list.txt', encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines]

def get_negative_galleryids_worker(term):
    return get_galleryids_for_query(term)

def get_galleryids_count_worker(negatives, term):
    results_origin = get_galleryids_for_query(term)
    results = [galleryid for galleryid in results_origin if galleryid not in negatives]

    return [term.split(':')[1].replace(" ", "_"), len(results)]

import multiprocessing
import parmap
import os

URL = "https://hitomi.la/search.html"
BOOKMAKRS = 'export.json'

def main():
    get_index_version()

    for filename in os.listdir("./"):
        if filename.startswith('export'):
            os.rename(filename, 'export.json')
            break
    
    with open(BOOKMAKRS, encoding="utf-8") as f:
        bookmarks = json.load(f)
    # os.remove(BOOKMAKRS) # remove old bookmark

    negative_terms = get_negative_tags()

    # get negative tag gallary id
    with multiprocessing.Pool(processes=process) as pool:
        results = pool.map(get_negative_galleryids_worker, negative_terms)

    # append to set, it will remove duplicate data
    negatives = set()
    for result in results:
        negatives.update(result)

    tags = set()
    urls = []
    negative_terms_str = "%20".join([ "-"+n.replace(":", "%3A") for n in negative_terms ])
    for last_idx, bookmark in enumerate(bookmarks['bookmarks']):
        if bookmark['title'].startswith("_"):
            continue
        paths = urlparse(bookmark['url']).path.split("/")
        if paths[-1].startswith("search"):
            uri = urlparse(bookmark['url']).query
            d = bookmark['url']
        else:
            if not (paths[-2].startswith('artist') or paths[-2].startswith('group')):
                continue
            tag, artist = paths[-2], "-".join(paths[-1].split('-')[:-1]).replace("%20", "_") # remove -all.html

            uri = tag+":"+artist
            d = URL+"?"+uri.replace(":", "%3A")+"%20"+negative_terms_str

        decoded_uri = decodeURIComponent(uri)
        positive_terms, _ = makeTerms(decoded_uri)

        urls.append(d)
        tags.update(positive_terms)

    func = partial(get_galleryids_count_worker, negatives)
    results = parmap.map(func, tags, pm_pbar=True, pm_processes=process)

    results.sort(key = lambda x: x[1])

    result_dict = {}
    prefix_len = len("http://hitomi.la/search.html")
    for result in results:
        artist, count = result
        for url in urls:
            if url[prefix_len:prefix_len + 30].find(artist) > -1:
                result_dict[artist] = [count, url]
    
    result = {
        "bookmarks": [],
        "groupings": [
            {
                "groupingId": 3,
                "groups": []
            }
        ],
        "library": [],
        "queue": [],
        "renamingRules": []
    }

    i = 1
    for key, value in result_dict.items():
        result["bookmarks"].append({
            "order": i,
            "site": "HITOMI",
            "title": f'''{key}_{value[0]}''',
            "url": value[1]
        })
        i += 1

    with open("result.json", "w") as f:
        json.dump(result, f, indent=2)
    
    os.remove(BOOKMAKRS) # remove old bookmark


def check_max_process(cpu_count):
    mx = multiprocessing.cpu_count()
    if cpu_count > mx:
        cpu_count = mx
    elif cpu_count < 1:
        cpu_count = mx // 2 if mx > 1 else 1
    return cpu_count


if __name__ == "__main__":
    assert len(sys.argv) <= 2, "python bookmark.py <process_num>"
    cpu_count = 32
    if len(sys.argv) == 2:
        temp = sys.argv[-1]
        assert int(temp), "second argv must be int"
        cpu_count = int(temp)

    if len(sys.argv) == 1:
        print("python bookmark.py <process_num>, default process num is 4")

    process = check_max_process(cpu_count)

    start = time.time()
    main()
    print(time.time() - start)