# 最新交付状态

用户要求立即汇总并暂跳过有问题来源。已完成17个P1的全文与关键帧核对、导出和finish；主笔记94条结论、5棋手路线、1主要变阵、6项人工裁决。BV1aAhf6PEew尚未完整审核，暂不纳入；BV1vTeS6nE9c的P2无可复用讲解。正式笔记：knowledge/lineups/河洛花木兰.md。详细19分P状态：raw/reports/heluo-huamulan/来源核查清单.md。

以下为过程历史，旧状态已由本节覆盖。

---

# 河洛花木兰整理进度

用户范围：18链接全部相关分P，无日期截止，冲突交用户裁决；默认不导出HTML。

## 当前状态

- 18链接已登记，元数据全核实；原8条链接有本地档案，10条补采。
- 已完整读取7份P1转写（oQ、W7、vTeS、14Jh、qaJ、EzH、rQ），查看26张关键帧；已写审核与纠错、成功导出7份全文。
- vTeS的P2仅识别“比赛开始”，未确认完整语音，保留待核查，不finish。
- 本批候选47条在build_import.py与import.json，尚未提交。
- 长批prepare会话69325：g9→Jzp→jv→br→aAh→sLp→Nh→bMp→15kp→mw，使用BV锁。
- 短批prepare会话58486：sLp→jv→br，避免长实战阻塞短教学；锁冲突可后续重试。
- 既有后台ota转写进程复用，未重复启动或停止其他采集。
- 补标题登记会话单独运行，保留人工信息。

## 已确认差异与待裁决

- vTeS:p1 656.04秒旧花木兰卡面每4张古币复生；oQ:p1 763.59秒较新卡面每5张。不替换旧数值，补丁日期未知。
- 已通过异步问题请用户裁决明先生五本持续刷新 vs 升六本：qaJ 694–757秒 vs rQ 290–326、664–698秒。未答前并列待确认，不虚构阈值。
- 昭君双输出在q-double保留完整成长差异，不把其他路线7人名单再加司空震拼成8人固定组合。

## 下一步

完成其余11份P1素材转写（含现有ota），逐段读全文与关键帧，补全结论并复查所有引用。读取相关旧笔记及补充有据的语义变化，统一commit；完成文字稿核对后finish有贡献来源；validate与批次审计。

## 候选结论ID

coin-loop, wanner-awaken, revive-budget, shared-core, ban-luna, opening-fighters, first-auction, save-search, missing-mulan, transition-talents, transition-wuzhuang, ming-economy, ming-five, zhuang-three-five, zhuang-six, zhuang-second-cast, zhuang-dream-luna, n-opening, n-five-missing, n-time, n-small-change, coin-machine, n-coins-manual, talent-core, q-start, q-double, q-luna, ying-resource, ying-luna-competition, second-auction, third-auction, luna-slot, luna-recycle, reserve-resources, scout-final-opponent, final-allin, crit-basic, artifact-choice, antiheal, zhong-position, late-scaling-equipment, anti-burst, review-short-revives, review-cost, historical-four, newer-five, ming-six-dispute


## 首批正式提交与校验

正式笔记knowledge/lineups/河洛花木兰.md已生成，53条结论、5路线、1主要变阵、1后期组合。9条P1已finish，workspace.sources确认9 deposited；validate为8篇笔记、949卡牌，errors=[]。正文53条结论各一次展示，昭君棋手5→7条、李信62→63条，其他旧笔记claims未改。

新增待裁决：庄小鱼双人连败vs保血；对嬴政反甲替换凝渊vs替换解控；复生上限10/14口径待核实。前3项已异步问用户，尚无回答。闹闹P2无可靠通用讲解，不finish。


## 补核与剩余队列

- 目前新增jv短教学全文已读并查看16.68/75.5/88.94/120.61秒4帧。独立补ASR会话29179（38–111秒，large-v3 CPU beam5）已恢复41.96–54.96秒开局讲解，待其输出完成后合入纠正版并保存原识别/纠错依据，不改原始ASR。
- 余下Jzp长视频已到约283秒ASR检查点；br短批最后一条约580秒在下载；既有ota进程到约1235秒。主批会话69325、短批58486仍运行。短批结束后可另开Nh/bMp/15kp/mw批以平衡剩余长视频；BV锁避免重复。
- 尚未修改软件代码或前端，所有辅助脚本在raw/reports/heluo-huamulan。

## 当前更新（覆盖旧会话状态）

主笔记56结论，10来源已finish；jv独立补转写完成并合入，原raw不变，13帧已核对。ota后台自然完成，58段全文已读，补视频帧会话88702。Jzp已读30段至857.64秒，未标全文完成。自有旧会话69325/58486已停止，检查点保留；改为serial_process.py会话25890和单独prefetch.py会话17622，原后台进程未停止。新增庄小鱼4名如梦/延后合成/固定12–13升六冲突已询问用户，尚未裁决。

## 12来源已沉淀，人工裁决已采纳

主笔记69结论含4项manual裁决；Jzp50段、16帧核对及finish完成。audit_batch.py确认正文69条各一次、原7笔记旧claims完全不变，仅昭君+2、李信+1，人工保护一致。10个已审来源中的重复未采用候选标签已按现有人工确认记录对齐，仍有真实歧义不自动采纳。15kp预读40段至1535.78，重复识别25段排除。原预取会话17622结束，aAh截断后分段恢复5929；串行25890现处理br，后续mw、Nh、bMp、15kp缓存复用、aAh。
