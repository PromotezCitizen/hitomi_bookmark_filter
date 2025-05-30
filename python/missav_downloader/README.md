> requirements

```
beautifulsoup4 - html 파싱
cloudscraper - cloudflare 기반 웹 페이지 request
tqdm - 진행도
playwright - 웹 크롤링
```

또는

```
pip install -r requirements.txt
```

> system requirements

```
다른 gpu를 쓴다면 그에 맞게 해주셔야합니다. nodejs 인터프리터도 마찬가지
코드 맨 위에 상수로 빼놨으니 그걸 수정하면 됩니다.
```

- NodeJS: bun

    - init 한 뒤 사용

- video processing: ffmpeg

- video accel: cuda(Nvidia gpu)

> playwright 초기 설정

```
pip install playwright
playwright install
```