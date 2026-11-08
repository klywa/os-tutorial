import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {useReaderLoader} from '../src/useReaderLoader';
import type {Note} from '../src/types';
function Harness(){
 const [selected,setSelected]=useState('n');
 const loader=useReaderLoader({selected,dirty:false,onSelect:setSelected});
 function save(){const note={...loader.detail!,revision:'r2'};loader.accept(note);window.dispatchEvent(new CustomEvent('wxq:knowledge-saved',{detail:{noteId:note.id,revision:note.revision}}));}
 return <><button onClick={save}>Accept save</button><button onClick={()=>window.dispatchEvent(new Event('wxq:knowledge-saved'))}>External save</button><button onClick={()=>setSelected('')}>Clear selection</button><output data-testid="state">{JSON.stringify({revision:loader.detail?.revision,reader:loader.reader?.revision,checking:loader.checking,verified:loader.verified})}</output></>;
}
createRoot(document.getElementById('root')!).render(<Harness/>);
