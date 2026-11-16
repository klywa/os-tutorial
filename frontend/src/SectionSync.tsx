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
type Preview = {historical: boolean; baseline: string; candidates: Candidate[]};
type Result = {id: string; status: 'saved'|'latest'|'failed'|'unknown'; error?: string};
const labels = {missing:'空缺', same:'一致', conflict:'冲突', ambiguous:'位置不明确'};
const resultLabels = {saved:'已同步', latest:'已是最新', failed:'同步失败', unknown:'待核对'};

function ConflictDetails({candidate, preview}: {candidate: Candidate; preview: Preview}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  const id = useId();
  const open = hovered || focused || pinned;
  return <div className="section-sync-conflict" onMouseEnter={()=>setHovered(true)} onMouseLeave={()=>setHovered(false)}>
    <button type="button" className="section-sync-badge" aria-controls={id} aria-expanded={open}
      onFocus={()=>setFocused(true)} onBlur={()=>setFocused(false)} onClick={()=>setPinned(value=>!value)}>冲突</button>
    {open && <div id={id} className="section-sync-conflict-details">
      <strong>目标段落当前内容</strong>
      <pre>{candidate.text}</pre>
      <strong>{preview.historical ? '源段落修改前与目标段落的差异' : '源段落当前内容与目标段落的差异'}</strong>
      <DiffText before={preview.baseline} after={candidate.text ?? ''}/>
    </div>}
  </div>;
}

export default function SectionSync({note, nodeId, disabled}: {note: Note; nodeId: string; disabled: boolean}) {
  const anchor = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const action = useRef(false);
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
      if(event.key === 'Escape' && !action.current) {
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
      if(sequence.current === request) setPreview(value);
    } catch (err) {
      if(sequence.current === request) setError((err as Error).message);
    } finally {
      if(sequence.current === request) setLoading(false);
    }
  }

  async function sync() {
    if(!preview || !selected.length || action.current || disabled) return;
    action.current = true;
    setSaving(true);
    setError('');
    try {
      const targets = Object.fromEntries(preview.candidates.filter(row=>selected.includes(row.id)).map(row=>[row.id,row.revision]));
      const value = await api<{results: Result[]}>(endpoint+'apply', 'POST', {...source, targets});
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
            <label><input type="checkbox" disabled={saving || disabled || candidate.status==='ambiguous'} checked={selected.includes(candidate.id)}
              onChange={event=>{const checked=event.currentTarget.checked;setSelected(ids=>checked ? [...ids,candidate.id] : ids.filter(id=>id!==candidate.id));}}/>
              <span>{candidate.title}<small>{candidate.player}</small></span></label>
            {candidate.status==='conflict' ? <ConflictDetails candidate={candidate} preview={preview}/> :
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
    </div>, document.body)}
  </>;
}
