import {textDiff} from './noteReviewModel';

self.addEventListener('message',({data})=>{
 const {id,before,after}=data as {id:number;before:string;after:string};
 self.postMessage({id,parts:textDiff(before,after)});
});
