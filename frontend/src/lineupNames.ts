import type {TopicChoice} from './types';
export const lineupLabel=(item:TopicChoice)=>item.display_name||item.common_name||item.name;
export const lineupSearch=(item:TopicChoice)=>[item.name,item.common_name??'',...item.aliases??[],item.description??''].join(' ');
