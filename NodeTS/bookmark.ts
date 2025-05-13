import fs from 'fs';

const negative_result_set = new Set();

// common.js
const domain2 = 'gold-usergeneratedcontent.net';
const domain = 'ltn.' + domain2;
const nozomiextension = '.nozomi';
// searchlib.js
const compressed_nozomi_prefix = 'n';

interface ExportType {
    library?: any[],
    queue?: any[],
    groupings?: any[],
    bookmarks?: BookmarkType[],
    renamingRules?: any[]
}

const BOOKMARK_SIZE = 'HITOMI'
interface BookmarkType {
    site: string,
    title: string,
    url: string,
    order: number
}

interface QueryState {
    area: string,
    tag: string,
    language: string,
    orderby: string,
    orderbykey: string,
    orderbydirection: string,
}

const state: QueryState = {
    area: 'all',
    tag: 'index',
    language: 'all',
    orderby: 'date',
    orderbykey: 'added',
    orderbydirection: 'desc',
};

// IIEF 패턴
// Immediately Invoked Function Expression
(async () => {
    try {
        const files = fs.readdirSync('.').filter(name => /^export-.*\.json$/.test(name))
        if (!Array.isArray(files) || files.length === 0) return;
        const export_file_name = files.pop() as string

        const export_file_json: ExportType = JSON.parse(fs.readFileSync(export_file_name, { encoding: 'utf-8' }))
        const artist_or_group_url_list = export_file_json.bookmarks?.map(bookmark => bookmark.url.replace(/https:\/\/hitomi.la\//g, '')) || []

        const artist_or_group_list = artist_or_group_url_list.map(item => {
            if (/^search.html/.test(item)) {
                item = item.replace(/^search.html\?/, '')
                return decodeURIComponent(item.split("%20").at(0) as string)
            } else {
                return item.replace(/-all.html$/, '').replace('/', ':')
            }
        })

        const negative_terms = read_negatives_from_file();
        const negative_terms_str = negative_terms.map(term => `-${term}`).join(" ");
        await generate_negative_result_set(negative_terms);

        const search_promise = artist_or_group_list.map(item => do_search(item))
        const results = await Promise.all(search_promise)
        results.sort((a, b) => a[1] - b[1])

        const bookmark_append_data: BookmarkType[] = results.map((item, idx) => {
            const [tag, item_count] = item
            const artist_name = tag.split(':')[1]
            const encoded_query = encodeURIComponent(`${tag} ${negative_terms_str}`)
            return {
                site: BOOKMARK_SIZE,
                title: `${artist_name}_${item_count}`,
                url: `https://hitomi.la/search.html?${encoded_query}`,
                order: idx + 1
            }
        })

        console.log(bookmark_append_data.at(0))

        const import_data: ExportType = {
            bookmarks: bookmark_append_data
        }

        fs.writeFileSync('result.json', JSON.stringify(import_data))
    } catch (err) {
        console.error('Unhandled error in main async IIFE:', err)
    }
})()

function read_negatives_from_file(path = 'D:\\hentoid\\negative_list.txt') {
    return fs.readFileSync(path, { encoding: 'utf-8' })
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean)
}

async function generate_negative_result_set(negative_terms: string[]) {
    const negative_list_promise = negative_terms.map(async term => {
        try {
            const query_result = await get_galleryids_for_query(term, state);
            query_result.forEach(item => negative_result_set.add(item))
        } catch (err) {
            console.error(`Failed to get results for term "${term}":`, err)
        }
    })
    await Promise.allSettled(negative_list_promise)
}

async function do_search(tag_of_artist_or_group: string): Promise<[string, number]> {
    const term = tag_of_artist_or_group;
    const local_result_length = (await get_galleryids_for_query(term, state))
        .filter(item => !negative_result_set.has(item))
        .length;

    return [term, local_result_length]
}

async function get_galleryids_from_nozomi(state: QueryState | { [x: string]: string }) {
    const address = nozomi_address_from_state(state)

    const response = await fetch(address, { method: 'GET' })
    if (!response.ok) {
        console.error(response);
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const arrayBuffer = await response.arrayBuffer()
    const view = new DataView(arrayBuffer)
    const total = view.byteLength / 4;
    const nozomi: number[] = [];
    for (let idx = 0; idx < total; idx++) {
        nozomi.push(view.getInt32(idx * 4, false)) // big-endian
    }
    return nozomi
};

function nozomi_address_from_state(state: QueryState | { [x: string]: string }) {
    const common_domain = `https://${domain}/${compressed_nozomi_prefix}/`
    const path_segment = state.area === 'all' ? '' : state.area + '/'
    const common_tag = `${state.tag}-${state.language}`

    return `${common_domain}${path_segment}${common_tag}${nozomiextension}`
};

async function get_galleryids_for_query(query: string, { ...state }) {
    query = query.replace(/_/g, ' ');
    if (query.indexOf(':') > -1) {
        const [left_side, right_side, _] = query.split(':');

        if (left_side?.endsWith('male')) {
            state['area'] = 'tag';
            state['tag'] = query;
        } else if ('language' === left_side) {
            state['language'] = right_side;
        } else {
            state['area'] = left_side;
            state['tag'] = right_side;
        }
        return await get_galleryids_from_nozomi(state)
    }
    return [];
};