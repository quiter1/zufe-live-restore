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

## 安装

1. 给 Edge/Chrome 装 **Tampermonkey** 扩展
   - Edge 商店：<https://microsoftedge.microsoft.com/addons/detail/iikmkjmpaadaobahmlepeloendndfphd>
2. **新版 Edge 必须额外开一步**：`edge://extensions/` → Tampermonkey → 详细信息 → 打开 **「允许用户脚本」**
3. 安装脚本（二选一）：
   - 把 `zufe-live-restore.user.js` 拖进浏览器 → 点【安装】
   - 或油猴面板 → `+` 新建脚本 → 全选删除 → 粘贴本文件 → `Ctrl+S`
4. 打开直播间页面，例如：
   ```
   https://psp-zelda.chaoxing.com/vri-zelda/index?speechid=…&enc=…
   ```

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

## 已知限制

- **需要登录**：没登录时服务端不会下发 `args`，脚本也无能为力（会在徽标上提示）。
- **CORS**：流地址在 `live.zufe.edu.cn`，跨域拉流需要对方允许。若控制台出现 `Failed to fetch`，需改用 `GM_xmlhttpRequest` 版本。
- **容器定位**：优先用现有 `<video>` 的父容器，其次按 class / 面积启发式取两块最大区域。定位不准时用 `?zufe_debug=1` 看描框，再调整选择器。
- 依赖 `cdn.jsdelivr.net` 上的 mpegts.js（脚本里 `@require`）。

## 免责声明

- 仅供个人学习研究、方便自己回看课堂画面使用。
- 请遵守学校相关规定；因使用本脚本产生的任何后果由使用者自负。
- 本项目与超星/浙江财经大学官方无关。

## License

[MIT](LICENSE)
