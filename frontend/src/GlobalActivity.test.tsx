import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import GlobalActivity from './GlobalActivity';
it('renders the application-owned expansion choice',()=>{
 const render=(expanded:boolean)=>renderToStaticMarkup(<GlobalActivity expanded={expanded} onExpandedChange={()=>{}}/>);
 expect(render(false)).not.toContain('activity-body');expect(render(false)).toContain('aria-expanded="false"');
 expect(render(true)).toContain('activity-body');expect(render(true)).toContain('aria-expanded="true"');
});
