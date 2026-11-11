# 智播课堂 · 强制显示直播真实画面（油猴脚本）

一个 Tampermonkey / 油猴用户脚本：**页面显示「直播已结束」时，仍然把真实的直播画面放出来**，并把画面填回页面原来的两个视频窗口。

> 适用于浙江财经大学「智播课堂」（`psp-zelda.chaoxing.com/vri-zelda/*`）。

## 效果

页面上那两个窗口，本来被「直播已结束」盖住了：

| 窗口 | 内容 |
| :--- | :--- |
| 大画面 | 课堂摄像头（对着讲台） |
| 小画面（"视频"页签） | 教室电脑桌面（老师放的课件/视频） |

脚本会把两路直播流直接接管过来，并把「直播已结束」那层遮掉；窗口拉伸、页面缩放时画面**自动跟随**容器尺寸。

## 安装（点一次，之后自动更新）

1. 给 Edge/Chrome 装 **Tampermonkey** 扩展
   - Edge 商店：<https://microsoftedge.microsoft.com/addons/detail/iikmkjmpaadaobahmlepeloendndfphd>
2. **新版 Edge 必须额外开一步**：`edge://extensions/` → Tampermonkey → 详细信息 → 打开 **「允许用户脚本」**
3. 点这个链接安装（油猴会弹出安装页，点【安装】就行）：
   <https://raw.githubusercontent.com/quiter1/zufe-live-restore/main/zufe-live-restore.user.js>
   - 已经装过旧版，再点同一个链接 → 油猴显示的是【更新】，**原地覆盖**，不会出现两个版本，也不用手动删除
4. 打开直播间页面，例如：
   ```
   https://psp-zelda.chaoxing.com/vri-zelda/index?speechid=…&enc=…
   ```

> 不用再「下载文件 → 拖进浏览器」了：脚本头部写了 `@downloadURL`，装过一次之后，油猴会自己去 GitHub 取最新版本。

## 更新（之后都不用手动重装）

- 油猴默认**每 24 小时**检查一次；发现 `@version` 变大就会自动下载并在下次打开页面时生效，不会让你删旧版。
- 想更快：油猴面板 → 设置 → 「检查更新」→ 改成**每小时**。
- 页面右下角如果冒出 `发现新版本 vX.Y.Z，点这里更新`，点一下 → 油猴弹【更新】→ 再点一下即可。
- **还在用 0.4.0 及更早版本的同学**：那几版头部没有 `@downloadURL`，油猴没法自动更新，需要手动点一次上面第 3 步的链接；**这一次之后**也会变成自动更新。

## 使用

- 页面右下角会出现状态徽标 `[直播恢复] …`
- 画面默认**静音**（浏览器自动播放策略），**点一下画面**即可开声音
- 调试模式：地址后加 `&zufe_debug=1`，会把两个候选窗口描出来（红 = main / 蓝 = ppt），并在控制台输出细节

## 原理

1. 页面源码里有一段 `args = {...}`，其中 `args.speech.videos` 写了每一路视频的签名地址：
   - `type: 'main'` → 课堂摄像头
   - `type: 'ppt'` → 电脑桌面
2. 「直播已结束」只是前端根据 `args.speech.settings` 里的时间窗（`starttimestamp/endtimestamp`）做的判断，**服务端下发的流地址本身是好的**。
3. 脚本读 `args`（页面没有就重新 `fetch` 同页源码解析），用 [mpegts.js](https://github.com/xqq/mpegts.js) 把 HTTP-FLV 转成 MSE 播放。
4. 把 `<video>` 绝对定位贴到原来的两个容器里（`inset: 0` + `ResizeObserver` + `window.resize`），遮挡掉「直播已结束」提示层。

## 更新记录

- **v0.4.2**（当前）：更新地址从 jsDelivr 换成 `raw.githubusercontent.com`，避开 CDN 最长 12 小时的缓存（以前推了新版本，油猴可能几小时内都查不到）；右下角新增「发现新版本」提示；`@version` 与代码里的 `VERSION` 由 GitHub Actions 校验一致
- v0.4.1：补上 `@updateURL` / `@downloadURL`，油猴可自动更新
- v0.4.0：页面内悬浮控制条，按钮在「现场画面 / 电脑桌面」之间切换
- v0.3.0：第二路「电脑桌面」不可见时自动开可拖动悬浮窗；描框不再依赖登录态；暴露 `window.__zufe`
- v0.2.0：画面跟随容器缩放（`ResizeObserver` + `window.resize`）；`?zufe_debug=1` 描框
- v0.1.0：初版

## 已知限制

- **需要登录**：没登录时服务端不会下发 `args`，脚本也无能为力（会在徽标上提示）。
- **CORS**：流地址在 `live.zufe.edu.cn`，跨域拉流需要对方允许。若控制台出现 `Failed to fetch`，需改用 `GM_xmlhttpRequest` 版本。
- **容器定位**：优先用现有 `video/canvas` 的父容器，其次按 class / 面积启发式取两块最大区域；第二块不可见时自动改用悬浮窗。定位不准时用 `?zufe_debug=1` 看描框。
- 依赖 `cdn.jsdelivr.net` 上的 mpegts.js（脚本里 `@require`）。

## 维护者：怎么发新版本

1. 改脚本后，把头部 `@version` 和代码里的 `const VERSION` **同时**改成新版本号（两处不一致，CI 会直接失败）；
2. `git commit` + `git push` 到 `main`；
3. `.github/workflows/release.yml` 会自动打 tag `vX.Y.Z`、建一个 GitHub Release，并把 `.user.js` 作为附件传上去；
4. 用户侧：油猴下次检查（默认 24 小时内）自动更新；页面上的更新提示最多 12 小时后出现（每台机器 12 小时只查一次）。

**你只需要 push 代码，不用再让任何人下载文件。**

## 免责声明

- 仅供个人学习研究、方便自己回看课堂画面使用。
- 请遵守学校相关规定；因使用本脚本产生的任何后果由使用者自负。
- 本项目与超星/浙江财经大学官方无关。

## License

[MIT](LICENSE)
