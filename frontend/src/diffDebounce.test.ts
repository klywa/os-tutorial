import {afterEach,expect,it,vi} from 'vitest';
import {createDiffDebouncer} from './diffDebounce';
afterEach(()=>vi.useRealTimers());
it('waits 2000ms and resets on each input',()=>{
 vi.useFakeTimers();const render=vi.fn();const timer=createDiffDebouncer(render);
 timer.update({before:'原文',after:'新'});vi.advanceTimersByTime(1999);expect(render).not.toHaveBeenCalled();
 timer.update({before:'原文',after:'新文'});vi.advanceTimersByTime(1999);expect(render).not.toHaveBeenCalled();
 vi.advanceTimersByTime(1);expect(render).toHaveBeenCalledExactlyOnceWith({before:'原文',after:'新文'});
});
it('pauses for IME and cancels obsolete previews',()=>{
 vi.useFakeTimers();const render=vi.fn();const timer=createDiffDebouncer(render);
 timer.update({before:'',after:'p'});timer.update({before:'',after:'拼'},true);vi.advanceTimersByTime(3000);expect(render).not.toHaveBeenCalled();
 timer.update({before:'',after:'拼音'});vi.advanceTimersByTime(2000);expect(render).toHaveBeenCalledTimes(1);
 timer.update({before:'',after:'取消'});timer.cancel();vi.advanceTimersByTime(3000);expect(render).toHaveBeenCalledTimes(1);
});
