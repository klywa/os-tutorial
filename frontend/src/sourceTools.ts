export function buildSourcePrompt(name:string,paths:string[]){return `根据以下内容，整理【${name||'{阵容名}'}】阵容的打法知识。

注意：

1. 若已有对应知识笔记，则在原笔记的基础上进行内容补充。若有冲突，则让用户裁决。
2. 甄别内容是否真的与当前阵容相关，无关内容自动忽略

内容如下：

${[...new Set(paths)].map(path=>'- '+path).join('\n')}`;}
export function keepSelection(ids:string[],sources:{id:string;ignored?:boolean}[]){const allowed=new Set(sources.filter(s=>!s.ignored).map(s=>s.id));return [...new Set(ids)].filter(id=>allowed.has(id));}

export async function copyOrFallback(text:string,write:(text:string)=>Promise<void>){try{await write(text);return '';}catch{return text;}}
