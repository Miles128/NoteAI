import hljs from 'highlight.js/lib/core';

const langs = [
    'javascript', 'typescript', 'python', 'bash', 'json', 'xml', 'css',
    'markdown', 'yaml', 'go', 'java', 'c', 'cpp', 'rust', 'sql', 'diff', 'ini',
];
for (const name of langs) {
    import(`highlight.js/lib/languages/${name}`).then(mod => hljs.registerLanguage(name, mod.default));
}

export default hljs;