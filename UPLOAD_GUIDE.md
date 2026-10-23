# GitHub 직접 업로드 / Cloudflare 배포

1. 이 ZIP을 PC에서 압축 해제합니다.
2. https://github.com/fort4dream17-cloud/- 로 이동합니다.
3. Add file → Upload files를 누릅니다.
4. 압축을 푼 폴더 안의 .github, config, dist, scripts, tests 폴더와 README.md, package.json, .gitignore, 이 안내 파일을 모두 드래그합니다.
   ZIP 자체나 바깥 폴더 하나를 올리지 마세요. GitHub 루트에 dist 폴더가 바로 보여야 합니다.
5. Commit changes로 main 브랜치에 저장합니다. 기존 README는 같은 경로에서 교체해도 됩니다.
6. Cloudflare → Workers & Pages → 새 Pages 프로젝트 → Git 저장소 연결 → fort4dream17-cloud/- 선택.
7. 브랜치 main / Framework None / Build command 비움 / Build output directory dist / Root directory 기본값.
8. 배포 완료 후 생성된 pages.dev 주소를 확인합니다.

데이터 연결은 별도 단계입니다. 현재 운영 데이터는 비어 있고, 예시는 버튼을 눌러야 표시됩니다.
KRX_ID와 KRX_PW는 GitHub Settings → Secrets and variables → Actions의 Repository secrets에 직접 등록하세요. 비밀번호를 파일에 넣지 마세요.
자동 수집과 GitHub Pages workflow는 저장소 변수를 활성화하기 전까지 실행되지 않습니다.
현재 저장소는 공개입니다. 실데이터 수집·공개는 공급자 이용권한과 접근범위 확인 후 활성화합니다.

업로드 완료 후 저장소 링크를 보내주시면 폴더 구조를 확인할 수 있습니다.
