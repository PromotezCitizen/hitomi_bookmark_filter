from urllib.parse import urlparse

def get_urls():
    with open('anime.txt', encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines]

urls = get_urls()
urls = [ url.split("/")[-1] for url in urls ]
urls = [ "".join(url.split(".")[:-1]) for url in urls ]
urls = [ "type:anime "+" ".join(url.split("-")[:-2]) for url in urls ]

with open("result.txt", "w") as f:
    for url in urls:
        f.write(url+"\n")

print(urls)