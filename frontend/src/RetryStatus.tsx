import type {RiskRetry} from './types';
// Retry scheduling stays in the backend; cooldown details are intentionally quiet.
export default function RetryStatus(_props:{retry?:RiskRetry|null;compact?:boolean}){return null;}
