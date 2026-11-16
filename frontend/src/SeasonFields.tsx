import {seasons,type Season} from './seasons';

export default function SeasonFields({value,onChange,disabled=false}:{value:Season[];onChange:(value:Season[])=>void;disabled?:boolean}){
 return <fieldset className="season-fields" disabled={disabled}><legend>适用赛季</legend>
  {seasons.map(season=><label key={season}><input type="checkbox" checked={value.includes(season)} onChange={e=>onChange(seasons.filter(item=>item===season?e.target.checked:value.includes(item)))}/>{season}</label>)}
  {!value.length&&<small role="status">请选择至少一个赛季</small>}
 </fieldset>;
}
