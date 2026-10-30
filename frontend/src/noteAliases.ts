export const parseNoteAliases=(value:string)=>[...new Set(value.split(/\r?\n/).map(name=>name.trim()).filter(Boolean))];
