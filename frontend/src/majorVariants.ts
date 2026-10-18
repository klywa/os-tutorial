import type {Meta,MajorVariant} from './types';
export const majorDimensions={heroes:'英雄组成',mechanism:'成长／输出机制',tempo:'运营节奏',equipment:'装备',talents:'天赋',skills:'技能'} as const;
export function majorRemovalBlocked(meta:Meta,key:'late_variant_ids'|'operation_route_ids',id:string){return (meta.major_variants??[]).some(v=>v[key].includes(id));}
export function emptyMajorDifferences():MajorVariant['differences']{const empty=()=>({status:'unknown' as const,claim_refs:[] as string[]});return {heroes:empty(),mechanism:empty(),tempo:empty(),equipment:empty(),talents:empty(),skills:empty()};}
