export type DiffSnapshot={before:string;after:string};
export function createDiffDebouncer(render:(value:DiffSnapshot)=>void,delay=2000){
 let timer:ReturnType<typeof setTimeout>|undefined;
 function cancel(){if(timer!==undefined)clearTimeout(timer);timer=undefined;}
 return {cancel,update(value:DiffSnapshot,composing=false){cancel();if(!composing)timer=setTimeout(()=>{timer=undefined;render(value);},delay);}};
}
