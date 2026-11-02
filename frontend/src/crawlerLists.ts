import type {Creator,CrawlJob} from './types';

type Loaders={
 fetchJobs:()=>Promise<CrawlJob[]>;fetchCreators:()=>Promise<Creator[]>;
 onJobs:(value:CrawlJob[])=>void;onCreators:(value:Creator[])=>void;
 onJobsError:(error:unknown)=>void;onCreatorsError:(error:unknown)=>void;
};

// Each endpoint publishes independently and has at most one request in flight.
// A slow/failing job projection must never hide an existing creator list.
export function createCrawlerListRefresh(loaders:Loaders){
 let jobs:Promise<void>|null=null,creators:Promise<void>|null=null;
 return async()=>{
  jobs??=Promise.resolve().then(loaders.fetchJobs).then(loaders.onJobs,loaders.onJobsError).finally(()=>{jobs=null;});
  creators??=Promise.resolve().then(loaders.fetchCreators).then(loaders.onCreators,loaders.onCreatorsError).finally(()=>{creators=null;});
  await Promise.all([jobs,creators]);
 };
}
