import json
from urllib.parse import urlparse
import re
import requests
import struct
import hashlib
from datetime import datetime
from functools import partial
import multiprocessing
import os
import parmap

class SearchLogic():
    def __init__(self, processNo):
        self.__nozomiextension = '.nozomi'
        self.__domain = 'ltn.hitomi.la'
        self.__compressed_nozomi_prefix = 'n'

        self.__max_node_size = 464
        self.B = 16

        self.__search_serial = 0
        self.__search_result_index = -1

        self.__tag_index_version = ''
        self.__galleries_index_version = '' 
        self.__languages_index_version = '' 
        self.__nozomiurl_index_version = ''

        self.__galleriesdir = 'galleries'
        self.__index_dir = 'tagindex'
        self.__galleries_index_dir = 'galleriesindex'
        self.__languages_index_dir = 'languagesindex'
        self.__nozomiurl_index_dir = 'nozomiurlindex'

        self.URL = "https://hitomi.la/search.html"
        self.BOOKMAKRS = 'export.json'

        self.__process = processNo

        self.__exception_tag = None
        self.__bookmark = None

    def decodeURIComponent(self, uri: str) -> list[str]:
        return re.sub(r'^\?', '', uri.replace("%3A", ":").replace("%20", " "))

    def makeTerms(self, text: str) -> list[str]:
        terms = re.split(r'\s+', text.lower().strip())
        negative_terms, positive_terms = [], []

        for term in terms:
            term = re.sub(r'_', ' ', term)
            if re.match(r'^-', term):
                negative_terms.append(re.sub(r'^-', '', term))
            else:
                positive_terms.append(term)

        return positive_terms, negative_terms
    

    def getIndexVersion(self, name = 'tagindex'):
        while True:
            url = f"https://{self.__domain}/{name}/version?_={datetime.now()}"
            response = requests.get(url)

            if response.status_code == 200 and response.text:
                self.__tag_index_version = response.text
                return
            
    def getGalleryIdsFromNozomi(self, area, tag, language):
        nozomi_address = 'https://'+'/'.join( [ self.__domain, self.__compressed_nozomi_prefix, '-'.join( [ tag, language ] ) ] )+self.__nozomiextension
        if area:
            nozomi_address = 'https://'+'/'.join( [ self.__domain, self.__compressed_nozomi_prefix, area, '-'.join( [ tag, language ] ) ] )+self.__nozomiextension

        res = []
        response = requests.get(nozomi_address)
        if response.status_code == 200:
            array_buffer = response.content
            total = len(array_buffer) // 4

            for i in range(total):
                res.append(struct.unpack('>i', array_buffer[i*4:(i+1)*4])[0])

        return res
    
    def getGalleryIdsForQuery(self, query):
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
            
            return self.getGalleryIdsFromNozomi(area, tag, language)
        
        key = self.hashTerm(query)
        field = 'galleries'
        
        node = self.getNodeAtAddress(field, 0)
        if not node:
            return []
        
        data = self.B_search(field, key, node)
        if not data:
            return []
        
        return self.getGalleryIdsFromData(data)
        
    def hashTerm(self, term):
        sha_signature = hashlib.sha256(term.encode()).digest()
        return sha_signature[:4]
    

    def getNodeAtAddress(self, field, address, serial=None):
        if serial:  # not used in the python code
            pass

        if field == 'galleries':
            url = f'https://{self.__domain}/{self.__galleries_index_dir}/galleries.{self.__galleries_index_version}.index'
        elif field == 'languages':
            url = f'https://{self.__domain}/{self.__languages_index_dir}/languages.{self.__languages_index_version}.index'
        elif field == 'nozomiurl':
            url = f'https://{self.__domain}/{self.__nozomiurl_index_dir}/nozomiurl.{self.__nozomiurl_index_version}.index'
        else:
            url = f'https://{self.__domain}/{self.__index_dir}/{field}.{self.__tag_index_version}.index'

        nodedata = self.getUrlAtRange(url, [address, address+self.__max_node_size-1])
        return self.decodeNode(nodedata) if nodedata else None

    def compareArraybuffers(self,dv1, dv2):
        return (dv1 > dv2) - (dv1 < dv2)

    def locateKey(self,key, node):
        cmp_result = -1
        for i, node_key in enumerate(node.keys):
            cmp_result = self.compareArraybuffers(key, node_key)
            if cmp_result <= 0:
                break
        return cmp_result == 0, i

    def isLeaf(self,node):
        return all(subnode_address == 0 for subnode_address in node.subnode_addresses)

    def B_search(self, field, key, node, serial=None):
        if serial:  # not used in the python code
            pass

        if not node or not node.keys:
            return False

        there, where = self.locateKey(key, node)
        if there:
            return node.datas[where]
        elif self.isLeaf(node):
            return False
        
        if node.subnode_addresses[where] == 0:
            print('non-root node address 0')
            return False

        return self.B_search(field, key, self.getNodeAtAddress(field, node.subnode_addresses[where]))
    
    def getGalleryIdsFromData(self, data):
        if not data:
            return []

        url = f'https://{self.__domain}/{self.__galleries_index_dir}/galleries.{self.__galleries_index_version}.data'
        offset, length = data
        if length > 100000000 or length <= 0:
            print(f"length {length} is too long")
            return []

        inbuf = self.getUrlAtRange(url, [offset, offset+length-1])
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

    def getUrlAtRange(self, url, range):
        headers = {'Range': f'bytes={range[0]}-{range[1]}'}
        response = requests.get(url, headers=headers)

        if response.status_code in [200, 206]:
            return bytearray(response.content)
        else:
            raise Exception(f'get_url_at_range({url}, {range}) failed, status_code: {response.status_code}')

    def decodeNode(self, data):
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

        number_of_subnode_addresses = self.B+1
        subnode_addresses = []
        for _ in range(number_of_subnode_addresses):
            subnode_address = struct.unpack(">Q", data[pos:pos+8])[0]
            pos += 8

            subnode_addresses.append(subnode_address)

        node['keys'] = keys
        node['datas'] = datas
        node['subnode_addresses'] = subnode_addresses

        return node

    def getNegativeTags(self):
        with open('negative_list.txt', encoding="utf-8") as f:
            lines = f.readlines()
        return [line.strip() for line in lines]

    def getExceptiontagGalleryIds_worker(self, term):
        return self.getGalleryIdsForQuery(term)

    def getGalleryIdsCount_worker(self, negatives, term):
        results_origin = self.getGalleryIdsForQuery(term)
        results = [galleryid for galleryid in results_origin if galleryid not in negatives]

        return [term.split(':')[1].replace(" ", "_"), len(results)]
    
    def setExceptionTag(self, negative):
        self.__exception_tag = negative

    def setBookmark(self, bookmark):
        self.__bookmark = bookmark

    def setFilename(self, filename):
        self.__filename = filename

    def run(self):
        # self.getIndexVersion()

        """ not use for this class
        # # ======== load bookmark - from main dialog ========
        # for filename in os.listdir("./"):
        #     if filename.startswith('export'):
        #         os.rename(filename, 'export.json')
        #         break
        
        # with open(self.BOOKMAKRS, encoding="utf-8") as f:
        #     self.__bookmark = json.load(f)
        # # os.remove(BOOKMAKRS) # remove old bookmark
        # # ==================================================

        # # ====== load negative tags - from main dialog =====
        # self.__exception_tag = self.getNegativeTags()
        # # ==================================================
        """

        # ========== get negative tag gallary id ===========
        negatives = self.makeExceptiontagSet()
        # ==================================================

        # ====== tags - artist or group, urls - url ========
        tags, urls = self.makeSearchQuery()
        # ==================================================

        # ==================================================
        results = self.getResultCounts(tags, negatives)
        # ==================================================

        result_dict = self.makeResult(results, urls)
        
        self.exportResult(result_dict)
        
        os.remove(self.__filename) # remove old bookmark

    def makeExceptiontagSet(self):
        with multiprocessing.Pool(processes=self.__process) as pool:
            results = pool.map(self.getExceptiontagGalleryIds_worker, self.__exception_tag)

        exceptions = set()
        for result in results:
            exceptions.update(result)

        return exceptions
    
    def makeSearchQuery(self):
        tags = set()
        urls = []
        negative_terms_str = "%20".join([ "-"+n.replace(":", "%3A") for n in self.__exception_tag ])
        for _, bookmark in enumerate(self.__bookmark):
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
                d = self.URL+"?"+uri.replace(":", "%3A")+"%20"+negative_terms_str

            decoded_uri = self.decodeURIComponent(uri)
            positive_terms, _ = self.makeTerms(decoded_uri)

            urls.append(d)
            tags.update(positive_terms)

        return tags, urls
    
    def getResultCounts(self, tags, negatives):
        func = partial(self.getGalleryIdsCount_worker, negatives)
        results = parmap.map(func, tags, pm_pbar=True, pm_processes=self.__process)

        results.sort(key = lambda x: x[1])
        return results
    
    def makeResult(self, results, urls):
        result_dict = {}
        prefix_len = len("http://hitomi.la/search.html")
        for result in results:
            artist, count = result
            for url in urls:
                if url[prefix_len:prefix_len + 30].find(artist) > -1:
                    result_dict[artist] = [count, url]

        return result_dict

    def exportResult(self, result_dict):
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

    def printData(self):
        print(self.__filename)
        print(self.__exception_tag)
        print(self.__bookmark[:100])


if __name__ == "__main__":
    logic = SearchLogic(16)
    logic.run()