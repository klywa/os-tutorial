import {useEffect, useId, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {api} from './model';
import {DiffText} from './ReviewFields';
import type {Note} from './types';
import './sectionSync.css';

type Candidate = {
  id: string; title: string; player: string; revision: string;
  status: 'missing'|'same'|'conflict'|'ambiguous'; latest?: boolean; text?: string; reason?: string;
};
type Preview = {historical: boolean; source_text: string; candidates: Candidate[]};
type Result = {id: string; status: 'saved'|'latest'|'failed'|'unknown'; error?: string};
type ConflictDraft = {candidate: Candidate; sourceText: string; revision: string; text: string};
const labels = {missing:'空缺', same:'一致', conflict:'冲突', ambiguous:'位置不明确'};
const resultLabels = {saved:'已同步', latest:'已是最新', failed:'同步失败', unknown:'待核对'};

function ConflictEditor({draft, saving, disabled, error, needsRefresh, onChange, onSave, onRefresh, onClose}: {
  draft: ConflictDraft; saving: boolean; disabled: boolean; error: string; needsRefresh: boolean;
  onChange: (text: string)=>void; onSave: ()=>void; onRefresh: ()=>void; onClose: ()=>void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [composing, setComposing] = useState(false);
  useEffect(()=>{
    const node = dialog.current;
    node?.showModal();
    return ()=>node?.close();
  }, []);
  return <dialog ref={dialog} className="section-sync-editor" aria-label="编辑同步冲突"
    onCancel={event=>{event.preventDefault();onClose();}}>
    <header><h2>编辑同步冲突</h2><p>保存到 {draft.candidate.title}</p></header>
    <div className="section-sync-comparison">
      <section><h3>源笔记当前内容</h3><pre>{draft.sourceText}</pre></section>
      <section><h3>目标笔记现有内容</h3><pre>{draft.candidate.text}</pre></section>
    </div>
    <label className="section-sync-draft">编辑稿<textarea rows={7} value={draft.text} disabled={saving}
      onCompositionStart={()=>setComposing(true)} onCompositionEnd={()=>setComposing(false)}
      onChange={event=>onChange(event.target.value)}/></label>
    <section><h3>目标现有内容与编辑稿的差异</h3>
      <DiffText before={draft.candidate.text ?? ''} after={draft.text} composing={composing} delay={150}/>
    </section>
    {error&&<p role="alert">{error}</p>}
    <footer className="section-sync-footer">
      {needsRefresh && <button type="button" disabled={saving} onClick={onRefresh}>重新读取版本</button>}
      <button type="button" disabled={saving} onClick={onClose}>取消</button>
      <button type="button" className="primary" disabled={saving||disabled||needsRefresh||composing}
        onClick={onSave}>{saving?'处理中…':'同步并保存'}</button>
    </footer>
  </dialog>;
}

export default function SectionSync({note, nodeId, disabled}: {note: Note; nodeId: string; disabled: boolean}) {
  const anchor = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const action = useRef(false);
  const conflictOpen = useRef(false);
  const sequence = useRef(0);
  const id = useId();
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({left: 8, top: 8, maxHeight: 300});
  const [preview, setPreview] = useState<Preview>();
  const [result, setResult] = useState<Result[]>();
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<ConflictDraft>();
  const [draftError, setDraftError] = useState('');
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [previewRevision, setPreviewRevision] = useState(note.revision);
  const endpoint = 'notes/'+encodeURIComponent(note.id)+'/section-sync/';
  const source = {node_id: nodeId, revision: note.revision};

  function close(restoreFocus = false) {
    if(action.current) return;
    sequence.current++;
    setOpen(false);
    if(restoreFocus) anchor.current?.focus();
  }

  useEffect(()=>{
    if(!open) return;
    function place() {
      const rect = anchor.current?.getBoundingClientRect();
      if(!rect) return;
      const below = innerHeight - rect.bottom - 16;
      const above = rect.top - 16;
      const maxHeight = Math.min(540, Math.max(100, below < 210 ? Math.max(above, below) : below));
      const height = Math.min(panel.current?.offsetHeight ?? 160, maxHeight);
      const top = below < 210 && above > below ? Math.max(8, rect.top - height - 8) : rect.bottom + 8;
      setCoords({left: Math.max(8, Math.min(rect.left, innerWidth - 440 - 8)), top, maxHeight});
    }
    function outside(event: PointerEvent) {
      const target = event.target as Node;
      if(!panel.current?.contains(target) && !anchor.current?.contains(target)) close();
    }
    function escape(event: KeyboardEvent) {
      if(event.key === 'Escape' && !action.current && !conflictOpen.current) {
        event.stopPropagation();
        close(true);
      }
    }
    place();
    panel.current?.focus();
    const observer = new ResizeObserver(place);
    if(panel.current) observer.observe(panel.current);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return ()=>{
      observer.disconnect();
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  async function load() {
    const request = ++sequence.current;
    setOpen(true);
    setLoading(true);
    setPreview(undefined);
    setSelected([]);
    setResult(undefined);
    setError('');
    try {
      const value = await api<Preview>(endpoint+'preview', 'POST', source);
      if(sequence.current === request) {
        setPreview(value);
        setPreviewRevision(source.revision);
      }
    } catch (err) {
      if(sequence.current === request) setError((err as Error).message);
    } finally {
      if(sequence.current === request) setLoading(false);
    }
  }

  async function sync() {
    if(!preview || !selected.length || action.current || conflictOpen.current || disabled) return;
    action.current = true;
    setSaving(true);
    setError('');
    try {
      const targets = Object.fromEntries(preview.candidates.filter(row=>selected.includes(row.id)).map(row=>[row.id,row.revision]));
      const value = await api<{results: Result[]}>(endpoint+'apply', 'POST', {...source, revision:previewRevision, targets});
      setResult(value.results);
      if(value.results.some(row=>row.status==='saved' || row.status==='unknown')) {
        window.dispatchEvent(new Event('wxq:knowledge-saved'));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      action.current = false;
      setSaving(false);
    }
  }

  function editConflict(candidate: Candidate) {
    if(!preview || action.current || disabled) return;
    conflictOpen.current = true;
    setDraft({candidate, sourceText:preview.source_text, revision:previewRevision, text:candidate.text ?? ''});
    setDraftError('');
    setNeedsRefresh(false);
  }

  function closeConflict() {
    if(action.current || !draft) return;
    if(draft.text !== draft.sourceText && !confirm('放弃这个目标的编辑稿吗？')) return;
    conflictOpen.current = false;
    setDraft(undefined);
  }

  async function refreshConflict() {
    if(!draft || action.current) return;
    action.current = true;
    setSaving(true);
    setDraftError('');
    try {
      const {revision} = await api<{revision:string}>('notes/'+encodeURIComponent(note.id)+'/revision');
      const fresh = await api<Preview>(endpoint+'preview', 'POST', {...source, revision});
      const candidate = fresh.candidates.find(row=>row.id===draft.candidate.id);
      if(!candidate || candidate.text===undefined) throw new Error('目标段落已无法定位，编辑稿仍可复制');
      setDraft({...draft, candidate, sourceText:fresh.source_text, revision});
      setPreview(fresh);
      setPreviewRevision(revision);
      setSelected([]);
      setNeedsRefresh(false);
    } catch (err) {
      setDraftError((err as Error).message);
    } finally {
      action.current = false;
      setSaving(false);
    }
  }

  async function saveConflict() {
    if(!draft || action.current || disabled || needsRefresh) return;
    action.current = true;
    setSaving(true);
    setDraftError('');
    try {
      const {results} = await api<{results: Result[]}>(endpoint+'apply', 'POST', {
        ...source, revision:draft.revision, targets:{[draft.candidate.id]:draft.candidate.revision}, draft:draft.text,
      });
      const item = results[0];
      if(item?.status!=='saved' && item?.status!=='latest') {
        if(item?.status==='unknown') window.dispatchEvent(new Event('wxq:knowledge-saved'));
        throw new Error(item?.error || '保存结果待核对');
      }
      conflictOpen.current = false;
      setDraft(undefined);
      setResult(results);
      if(item.status==='saved') window.dispatchEvent(new Event('wxq:knowledge-saved'));
    } catch (err) {
      setDraftError((err as Error).message);
      setNeedsRefresh(true);
    } finally {
      action.current = false;
      setSaving(false);
    }
  }

  return <>
    <button ref={anchor} type="button" disabled={disabled || saving} aria-haspopup="dialog" aria-expanded={open}
      aria-controls={open ? id : undefined} onClick={()=>open ? close() : void load()}>同步到同阵容笔记</button>
    {open && createPortal(<div id={id} ref={panel} role="dialog" aria-label="同步到同阵容笔记" tabIndex={-1}
      className="section-sync-popover" style={coords} onClick={event=>event.stopPropagation()}>
      {loading && <p role="status">正在读取同阵容笔记…</p>}
      {error && <p role="alert">{error}</p>}
      {preview && !result && <>
        {!preview.historical && !!preview.candidates.length && <p className="muted">未找到修改前版本，状态按当前源段落比较。</p>}
        {!preview.candidates.length && <p>暂无其他棋手的同阵容笔记。</p>}
        <ul>{preview.candidates.map(candidate=><li key={candidate.id}>
          <div className="section-sync-row">
            <label><input type="checkbox" disabled={saving || disabled || candidate.status==='ambiguous' || candidate.status==='conflict'} checked={selected.includes(candidate.id)}
              onChange={event=>{const checked=event.currentTarget.checked;setSelected(ids=>checked ? [...ids,candidate.id] : ids.filter(id=>id!==candidate.id));}}/>
              <span>{candidate.title}<small>{candidate.player}</small></span></label>
            {candidate.status==='conflict' ? <button type="button" className="section-sync-badge" aria-haspopup="dialog"
              disabled={saving||disabled} onClick={()=>editConflict(candidate)}>冲突</button> :
              <span className="section-sync-badge">{labels[candidate.status]}</span>}
          </div>
          {candidate.latest && <small className="muted">已是最新</small>}
          {candidate.reason && <small className="muted">{candidate.reason}</small>}
        </li>)}</ul>
      </>}
      {result && <ul aria-label="同步结果" role="status">{result.map(row=><li key={row.id}>
        {preview?.candidates.find(candidate=>candidate.id===row.id)?.title} · {resultLabels[row.status]}
        {row.error && <p>{row.error}</p>}
      </li>)}</ul>}
      <div className="section-sync-footer">
        {((error && !saving) || result?.some(row=>row.error)) && <button type="button" onClick={()=>void load()}>刷新列表</button>}
        <button type="button" disabled={saving} onClick={()=>close(true)}>{result ? '关闭' : '取消'}</button>
        {!result && preview && !!preview.candidates.length &&
          <button type="button" className="primary" disabled={!selected.length || saving || disabled || !!error}
            onClick={()=>void sync()}>{saving ? '同步中…' : selected.length ? `同步（${selected.length}）` : '同步'}</button>}
      </div>
      {draft && <ConflictEditor draft={draft} saving={saving} disabled={disabled} error={draftError}
        needsRefresh={needsRefresh} onChange={text=>setDraft({...draft,text})}
        onSave={()=>void saveConflict()} onRefresh={()=>void refreshConflict()} onClose={closeConflict}/>}
    </div>, document.body)}
  </>;
}
