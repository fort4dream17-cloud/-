import {readFileSync} from 'node:fs';
import {validateDataset} from '../dist/engine.js';
const d=validateDataset(JSON.parse(readFileSync(process.argv[2],'utf8')));
if(d.meta.data_kind!=='empty'&&d.meta.data_kind!=='real')throw Error('운영 데이터에는 예시 데이터를 게시할 수 없습니다.');
console.log(`검증 완료: ${d.rows.length}행 / ${d.groups.length}종목 / ${d.meta.as_of??'미연결'}`);
