# 新闻订阅源托管方案

> 目标：让「经济新闻」页每天自动更新。
> 原理：小程序不联网抓取（微信审核与合规限制），而是**拉取一个你托管好的静态 JSON**。
> 这个 JSON 由本目录的脚本每天自动生成。

---

## 一、整体链路

```
公开 RSS/Atom/JSON 源
        │  build_feed.py 每天定时跑一次
        ▼
   feed.json  ← 你把它放到任意静态托管（GitHub Pages / 对象存储 / Nginx）
        │  小程序 wx.request 拉取
        ▼
  小程序「经济新闻」页（增量合并、自动分类、离线降级到内置种子）
```

**关键点**：`feed.json` 是一个普通静态文件，放哪里都行，不涉及任何云开发、不写爬虫跑在小程序里。

> ### 💡 最重要的一件事：每天的更新在 GitHub 服务器上跑
>
> `refresh-feed.yml` 是 **GitHub Actions** 工作流。它由 GitHub 自己的服务器执行，
> **跟你本地网络、跟你电脑开不开机完全无关**。
>
> 所以你只需要**成功推送一次**，之后每天 UTC 07:17（北京 15:17）
> GitHub 会自动跑聚合脚本、提交新的 `feed.json`、重新部署 Pages。
>
> 推完之后，你的电脑可以关机、旅行、断网，都不影响新闻每天更新。

---

## 二、生成 feed.json

```bash
cd tools/news-feed
python3 build_feed.py            # 读取 sources.json，输出 feed.json
python3 build_feed.py --dry-run  # 只看结果不写文件
python3 build_feed.py -c my.json -o out.json   # 自定义配置与输出
```

* 只依赖 Python 3 标准库，**不需要 pip install**。
* 单个源失败会自动跳过并报告，不影响整体。
* 输出格式：`[{ title, summary, url, date, category, source }, ...]`
  —— 与小程序端 `utils/newsFeed.js` 的解析器完全兼容（已实测）。

### 调整订阅源

编辑 `sources.json`：

```jsonc
{
  "filter": {
    "enabled": true,                 // 只想收宠物相关就保持 true
    "includeAny": ["宠物", "猫粮"],   // 垂类强词：命中任一即保留（中英双语）
    "includeAll": ["标准", "电商"],   // 宽泛词：必须和强词同时命中才有效
    "excludeAny": ["球队", "明星"]    // 命中即丢弃
  },
  "sources": [
    {
      "name": "来源显示名",
      "url": "https://.../rss",
      "category": "data",
      "tier": "vertical",             // 见下方说明
      "enabled": true
    }
  ]
}
```

#### tier：垂类源 vs 泛资讯源（重要）

| tier | 含义 | 行为 |
|------|------|------|
| `vertical` | 本身就是宠物 / 食品行业的垂类媒体 | **整源放行**，不做关键词过滤 |
| `general` | 泛资讯源（财经 / 社会 / 时事） | 必须命中 `filter.includeAny` 才保留 |

> **为什么需要 tier**：早期版本对所有源统一用关键词过滤，结果两个反向错误：
> 1. 泛化词（"进口""标准""政策"）让时事新闻大量混入 —— "海南自贸港再迎政策支持"也算命中；
> 2. 英文垂类源（Petfood Industry / PET worldwide）标题里没有中文关键词，10 条全被误杀。
>
> 分层之后：垂类源直接放行，泛资讯源走严格白名单，实测时事新闻 100% 拦下，
> 行业新闻 40 条全保留。

**不要往 `includeAny` 里加泛化词**（如 "进口""出口""标准""电商"），
那些词放 `includeAll` 才有意义。

`category` 是兜底分类，取值：`policy` 政策法规 / `factory` 工厂产能 /
`capital` 资本融资 / `data` 行业数据 / `brand` 品牌动态。
标题或摘要命中关键词时会自动改判，所以 `category` 只在匹配不到时生效。
分类词表同时含中英文（英文垂类源必须靠英文词才能正确归类），
与小程序端 `utils/newsFeed.js` 的 `CATEGORY_RULES` 保持一致。

#### 当前内置的源

| 源 | tier | 说明 |
|----|------|------|
| Petfood Industry | vertical | 美国宠物食品行业杂志，主力源 |
| Pet Food Processing | vertical | 宠物食品加工技术（产线、配方、设备） |
| PET worldwide | vertical | 欧洲宠物行业，覆盖品牌与渠道 |
| Pet Food Institute | vertical | 美国宠物食品协会官方 |
| Food Dive | general | 泛食品媒体，靠关键词捞宠物相关 |
| 国家统计局 / 中新网 / 界面 / 人民网 | general | 泛资讯，靠关键词捞政策与数据 |

**中文垂类源目前没找到可用的公开 RSS**（派读、狗民网、宠业家等均已失效或无 RSS），
所以内容以英文行业媒体为主。如果你有更对口的源，直接加进 `sources.json` 即可。

---

## 三、托管 feed.json（四种方式，任选其一）

### 方式 A：GitHub Pages（推荐，零成本）

**① 新建仓库 —— 你已经建好了**

仓库 `yr020816/petfood-news-feed` 已创建（Public，默认分支 `main`），
地址 <https://github.com/yr020816/petfood-news-feed>，可直接用，无需再建。

**② 推送本目录内容 —— 双击 `一键推送.bat`（推荐）**

就在本目录里，双击 **`一键推送.bat`** 即可。

它会：
1. 自动定位 Python（不需要装 Git，也不需要配任何凭据）
2. 提示你粘贴一个 **Personal Access Token**（`ghp_` 开头，粘贴时不显示字符）
3. 走 `api.github.com` 把 8 个文件推上去（**绕开 `github.com` 主站**，
   国内网络下主站经常超时，API 反而通）
4. 顺手调用一次 Pages 接口，把 Source 设成 GitHub Actions
5. 全程输出同时打到屏幕和同目录的 `push_log.txt`

Token 只输一次，之后会存到 `~/.news_feed_token` 自动复用。

> **找不到 Python 也能用**：脚本会自动切到内置的 PowerShell 通道
> （`push_via_powershell.ps1`，Windows 自带，不需要装任何东西），
> 功能完全一样。

> **窗口一闪就没了？** 说明脚本异常退出了。`push_log.txt` 里会记下
> 最后一次运行的情况；如果连日志都没有，多半是文件被杀毒软件拦了，
> 右键 → 属性 → 勾选"解除锁定"再试。

**Token 怎么拿**（主站打不开时用镜像）：

1. 浏览器打开 <https://github.com/settings/tokens/new>
   （若打不开，改用镜像 <https://gh-proxy.net/https://github.com/settings/tokens/new>）
2. Note 填 `petfood-feed`，Expiration 选长期
3. **必须勾选两项权限**（少勾一项就会推送失败）：
   - `repository` → **`repo`**（Full control of private repositories）
   - `workflow` → **`workflow`**（Add/update workflow files）
4. Generate token 后复制那串 `ghp_...` 字符

> **权限没勾够会怎样？** GitHub 对「只有读权限」的令牌，
> 写操作会返回 **404**（故意不返回 403，以免泄露资源是否存在），
> 报错看起来像「文件不存在」，非常难查。
> 脚本现在会自动诊断这种情况并直接告诉你怎么改。
>
> **补救不用重新生成 Token**：经典 PAT 修改权限时**字符串不变**，
> 打开 <https://github.com/settings/tokens> → 点进 `petfood-feed`
> → 勾上 `repo` 和 `workflow` → 滚到底点 **Update token** 即可，
> 现在这份继续用。

**Token 怎么录入**（脚本按这个顺序找，找到能用的就停）：

| 顺序 | 方式 | 说明 |
|---|---|---|
| 1 | 命令行 `--token` | 自动化场景用 |
| 2 | 环境变量 `GITHUB_TOKEN` | CI 场景用 |
| 3 | **剪贴板** | 复制好 token，直接回车即可（**最省事**） |
| 4 | **`token.txt` 文件** | 把 token 粘进同目录的 `token.txt` 保存 |
| 5 | 手动输入 | 兜底；控制台粘贴可能混入控制字符，脚本会自动清洗 |
| 6 | `~/.news_feed_token` | 上次保存的，自动复用 |

> **为什么不让你在控制台里粘贴？** Windows 控制台的 `getpass`
> 是**逐字符**读取的，粘贴进来的内容会混入 `\x16` 之类的控制字符，
> 有时还会被复制两遍，存下来的 token 直接损坏 → 401。
> 现在脚本会自动剥掉控制字符、拆开重复段，
> 并把每个候选都拿去 GitHub 校验一遍，所以**粘贴坏了也能救回来**。
>
> **推荐用法**：把 token 复制到剪贴板 → 双击 `一键推送.bat` → 直接回车。

> Token 只存在你自己的电脑上（`~/.news_feed_token`），只用于这个公开仓库。
> 用完想撤销：GitHub 右上角头像 → Settings → Developer settings →
> Personal access tokens → 点进该 token → Delete。
> `token.txt` 已加入 `.gitignore`，不会被推送到仓库。

**方式 A1 — 命令行（想看详细过程时）**

```bash
# 推荐：走 API，不需要 Git 凭据
python upload_via_api.py --save-token

# 没有 Python 时用 PowerShell 通道（Windows 自带）
powershell -ExecutionPolicy Bypass -File .\push_via_powershell.ps1

# 或者用 git push（需要本机已配好 GitHub 凭据）
bash push_to_github.sh
```

**方式 A2 — PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File .\push_to_github.ps1
```

**方式 A3 — 手动 git 命令**

```bash
cd tools/news-feed
git init -b main
git add -A
git commit -m "feat: 新闻订阅源聚合"
git remote add origin https://github.com/yr020816/petfood-news-feed.git
git push -u origin main
```

> **分支名必须是 `main`**：GitHub 新仓库默认分支是 `main`，而**定时触发的
> GitHub Actions 只在默认分支上运行**。推成 `master` 的话，手动点 Run workflow
> 能跑，但每天 15:17 的自动刷新会静默失效。脚本已内置自动规范。

> **首次推送会弹出浏览器窗口**，登录 GitHub 并点授权即可。
> 本机已装 Git Credential Manager 2.9.0，无需额外配置。
> 如果没弹窗，改用方式 A3（API + Token），或在 Git Bash 里执行：
> `git credential-manager github login`

> **脚本会自动切换网络通道**：直连 → 本地代理（7890/10809/1080/8080 等）
> → 加速镜像（gh-proxy.com / ghfast.top / gitclone.com）。
> 推送前会打印实际选中的通道，比如 `推送通道：镜像 https://gh-proxy.com`。

**③ 开启 Pages**

仓库右上角 **Settings → 左侧 Pages → Source 选 “GitHub Actions” → Save**。

**④ 开启工作流写权限**

**Settings → 左侧 Actions → General → Workflow permissions 选
“Read and write permissions”**。
（不设这一项的话，脚本能跑通但自动提交 feed.json 会失败。）

**⑤ 确认自动触发已生效**

工作流目前有三个触发器，**任选其一**即可：

| 触发方式 | 什么时候跑 | 说明 |
|---------|-----------|------|
| `schedule` | 每天北京时间 **15:17** | 主力，无需干预 |
| `push` | 你推 `build_feed.py` / `sources.json` / `index.html` / workflow 文件到 `main` 时 | 改配置后自动重建 |
| `workflow_dispatch` | 手动点 **Actions → 左侧「刷新新闻订阅源」→ Run workflow** | 随时立即刷新 |

> **注意**：自动提交 `feed.json` 本身**不会**触发 `push` 触发器
> （`feed.json` 不在 `paths` 白名单里），否则会形成无限循环。

验证：浏览器打开

```
https://yr020816.github.io/petfood-news-feed/
```

能看到一个新闻列表页（`index.html`），说明托管成功。
对应的数据文件地址是：

```
https://yr020816.github.io/petfood-news-feed/feed.json
```

**⑥ 配置微信 request 合法域名**

见下面「四、在小程序里配置」。要点：域名只填 `https://yr020816.github.io`，
**不带仓库名、不带路径**。

> 关于备案：`github.io` 是境外域名，微信对 request 合法域名不做 ICP 备案校验
> （境内 `.cn`/`.com` 才需要），所以这条链路不需要额外备案。
> 如果后台仍然拒绝，改用下面的方式 B（对象存储默认域名自带备案）。

### 方式 B：对象存储 COS / OSS（国内更快，自带备案）

1. 把 `feed.json` 上传到桶的静态网站目录，开启「静态网站托管」。
2. 得到形如 `https://<bucket>.cos.<region>.myqcloud.com/feed.json` 的地址。
3. 写一个定时任务每天覆盖上传（同样可以用 GitHub Actions，末尾加一条 `coscmd`/`ossutil` 步骤）。
4. COS 默认域名已在腾讯侧完成备案，可直接填入 request 合法域名。

### 方式 C：自己的服务器

Nginx 放一个 `feed.json`，写个 crontab：

```cron
*/30 * * * *  cd /srv/news-feed && /usr/bin/python3 build_feed.py >> /var/log/feed.log 2>&1
```

### 方式 D：Gitee 码云（国内直连，域名已备案）

如果微信后台拒绝 `github.io`（境外域名偶有被拒），Gitee 是稳妥替代：
`gitee.com` 在国内直连稳定，且已完成 ICP 备案，能直接填进 request 合法域名。

1. 注册 <https://gitee.com>，新建一个**公开**仓库（如 `petfood-news-feed`）
2. 把本目录内容推上去：
   ```bash
   cd tools/news-feed
   git init -b main
   git add -A
   git commit -m "feat: 新闻订阅源聚合"
   git remote add origin https://gitee.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
3. 数据文件地址（用 raw 访问，无需开启 Pages 服务）：
   ```
   https://gitee.com/<你的用户名>/<仓库名>/raw/main/feed.json
   ```
4. 微信后台 request 合法域名填 `https://gitee.com`

> **取舍**：Gitee 解决了备案和连通性，但**没有免费的定时任务**
> （Gitee 流水线是付费功能）。若走 Gitee，需要把「每天自动更新」
> 改成小程序端拉取时顺带触发，或在自己的服务器上跑 crontab 后推给 Gitee。
>
> 如果你希望「完全自动 + 每天更新 + 零成本」，**优先用方式 A（GitHub Pages）**：
> 每日刷新由 GitHub Actions 在 GitHub 服务器上执行，不依赖你的电脑和网络。

---

## 四、在小程序里配置

### 4.1 微信后台加 request 合法域名

登录 <https://mp.weixin.qq.com>，路径：

```
开发管理（或「开发与服务」）→ 开发设置 → 服务器域名 → request 合法域名 → 修改
```

填入你的托管域名，**只填域名本身**：

| 托管方式 | 填写的值 |
|---|---|
| GitHub Pages | `https://yr020816.github.io` |
| COS / OSS | `https://<bucket>.cos.<region>.myqcloud.com` |
| 自建服务器 | `https://news.你的域名.com` |

规则：**必须 https；不能带路径；不能带端口；不能是 IP；不能有下划线**。

若微信要求做归属权校验（下载 `MP_verify_xxxx.txt` 放到域名根目录），
详见 `WECHAT_VERIFY.md`。GitHub Pages 方案把它放在本目录即可，
因为工作流是**整目录发布**，根目录就是 `tools/news-feed/`。

> request 合法域名每月可修改 50 次，别反复试错；先在开发者工具里验证好再提交。

### 4.2 小程序里添加订阅源

**默认已经配好了，不用手动加。**

首次启动时 `store.init()` 会自动写入内置订阅源
（`utils/newsFeed.js` 的 `DEFAULT_FEEDS[0]`）：

| 字段 | 值 |
|---|---|
| 名称 | 猫粮行业动态（每日更新） |
| 地址 | `https://yr020816.github.io/petfood-news-feed/feed.json` |
| 分类 | brand（仅在标题匹配不到关键词时作为兜底） |

打开小程序 → **经济新闻** 页，它会**自动静默同步**一次
（距上次同步超过 `autoHours` 才拉，拉取失败不打扰用户）。
想立刻看效果，进 **设置 → 新闻订阅源 → 立即同步**。

> 域名还没在微信后台配好、或真机被拦截时，同步会失败并提示
> 「请检查网络与 request 合法域名配置」——这不影响其他功能，
> 先把 4.1 的域名配上即可。

如果你想改用别的源（自己的接口 / 别的 RSS），
在 **设置 → 新闻订阅源 → 添加订阅源** 里加就行，多个源会一起同步。

| 字段 | 填什么 |
|---|---|
| 名称 | 随意，如「宠物行业聚合」 |
| 地址 | `https://yr020816.github.io/petfood-news-feed/feed.json` |
| 类型 | **JSON** |
| 启用 | 打开 |

### 4.3 验证

- 浏览器打开 `https://yr020816.github.io/petfood-news-feed/` → 能看到新闻列表 = 托管正常
- 小程序同步后新增了条目 = 全链路打通
- 同步失败且提示 `url not in domain list` → 回 4.1 检查域名
- 同步失败但提示超时 → 网络问题，或该域名在国内访问慢（换方式 B）

---

## 五、注意事项

| 事项 | 说明 |
|---|---|
| 合法域名 | 小程序只允许请求**已在后台配置**的域名，本地 `localhost` 或 IP 在真机上一定失败 |
| 开发者工具调试 | 工具里勾选「不校验合法域名」才能本地调试（项目配置已默认 `urlCheck: false`） |
| 离线降级 | 拉取失败时小程序会继续显示内置的 14 条种子新闻，功能不缺失 |
| 增量合并 | 远端按「标题 + 链接」去重，重复同步不会产生重复条目 |
| CDN 缓存 | 小程序请求会自动追加时间戳绕开缓存（`utils/newsFeed.js` 的 `withCacheBust`），保证能拿到当天的更新 |
| 自动同步间隔 | 可在订阅源页设为 1/3/6/12/24 小时，默认 6 小时 |
| 审核 | 联网只用于拉取这个 JSON，属于工具类常规能力；类目建议「工具 > 实用工具」 |
| 第三方源可用性 | 公开 RSS 可能随时失效，脚本会自动跳过并在日志中报告，建议定期看一眼 |
| 修改次数 | request 合法域名每月 50 次上限，别反复试错 |

---

## 五、常见问题

**Q：Actions 跑完了但 Pages 上的 feed.json 还是旧的？**
A：先看 workflow 的「提交更新」这一步是不是 success。如果是 success 但内容没变，
说明聚合器抓到的内容和线上一样（正常）；如果这一步 failure，看日志里的具体报错：

| 日志关键字 | 原因 | 解决 |
|-----------|------|------|
| `! [rejected] main -> main (fetch first)` | checkout 用了默认浅克隆（`fetch-depth: 1`），本地没有远端历史，push 被拒 | workflow 里给 `actions/checkout` 加 `fetch-depth: 0`，并在 push 前 `git pull --rebase`（本项目已修） |
| `Permission denied` / `403` | Actions 的 workflow 权限是只读 | Settings → Actions → General → Workflow permissions 选 “Read and write permissions” |
| `nothing to commit` | 内容确实没变化 | 正常，不是错误 |

**Q：workflow 一天只跑一次，能不能多跑？**
A：改 `refresh-feed.yml` 里的 `cron`。注意 **cron 是 UTC**，
北京时间 = UTC + 8 小时。当前是 `"17 7 * * *"` = 北京时间 15:17。
GitHub 整点任务排队严重，故意避开整点。

**Q：改了 sources.json 但线上没变？**
A：`sources.json` 在 `push` 触发器的 `paths` 白名单里，推上去就会自动重建。
如果没生效，检查 Actions 里是不是有一个**旧 run 还在排队**（并发会串行化），
或者手动点一次 Run workflow。

**Q：推送时提示「暂时连不上 github.com」？**
A：git push 访问的是 **github.com 主站**（不是 api.github.com），国内通常需要代理。
脚本已内置三级探测：**直连 → 本地代理 → 加速镜像**
（代理端口扫 7890 / 10809 / 1080 / 8080 / 50085 / 7897 / 1087 / 10808；
镜像试 gh-proxy.com / ghfast.top / gitclone.com）。
推送前会打印实际选中的通道，例如 `推送通道：镜像 https://gh-proxy.com`。

若仍失败，三条出路：
1. 打开代理软件后重跑脚本；
2. 手动指定端口（换成你软件实际用的那个）：
   ```bash
   git config --global http.proxy http://127.0.0.1:7890
   git config --global https.proxy http://127.0.0.1:7890
   ```
3. **改用 API 上传**（`api.github.com` 通常是通的，且不需要代理）：
   ```bash
   bash upload_via_api.sh
   ```
   按提示粘贴一个 `ghp_` 开头的 Token 即可。

**Q：api.github.com 能通，但 git push 还是失败？**
A：这是国内网络环境的典型情况 —— 两者走的不是同一条链路。
`git push` 必须访问 `github.com` 主站，而 API 走 `api.github.com`。
直接用 `bash upload_via_api.sh` 走 API 上传即可，功能完全等价，
后续每日更新照样由 GitHub Actions 自动完成。

**Q：Token 要怎么生成？会不会泄露？**
A：Token 在 GitHub 网页生成，只存在你自己的电脑上，脚本不会上传到任何地方。
粘贴时终端不显示字符（防泄露），这是正常现象。
它只需要 `repo` 权限；如果以后不用了，可以在
<https://github.com/settings/tokens> 一键吊销。

**Q：仓库名已被占用？**
A：换个名字，比如 `petfood-news-2026`，不影响功能。

**Q：提示需要验证邮箱？**
A：去 `github.com/settings/emails` 点验证链接，再回来建仓库。

**Q：推送时所有写操作都报 404 Not Found？**
A：**99% 是 Token 权限没勾够。** GitHub 对「只能读、不能写」的令牌，
写操作会返回 **404**（故意不返回 403，以免泄露资源是否存在），
报错看起来像「文件不存在」，极具迷惑性。

打开 <https://github.com/settings/tokens> → 点进 `petfood-feed`
→ 勾选 `repository → repo` 和 `workflow → workflow` → **Update token**。
**经典 PAT 改权限后字符串不变**，现在这份继续用，不用重新生成。

脚本现在会自动检测这种情况并直接给出修复指引。

**Q：提示「所有候选 Token 都不可用」？**
A：说明找到的 token 全部校验失败。常见原因：
① 控制台粘贴混入控制字符（脚本已自动清洗，仍失败说明 token 本身不对）；
② token 已被删除或过期；
③ 复制时漏了末尾几位。
**推荐改用剪贴板方式**：复制好 token → 双击 `一键推送.bat` → 直接回车。

**Q：推送后 Pages 404？**
A：检查 ①仓库 Settings → Pages → Source 是否选了 "GitHub Actions"；
②Actions 里「刷新新闻订阅源」是否跑绿；③首次部署约需 1~2 分钟。

**Q：自动提交 feed.json 失败（permission denied）？**
A：Settings → Actions → General → Workflow permissions 改成
"Read and write permissions"。

**Q：微信后台不让加 github.io，说要备案？**
A：理论上境外域名不需要备案，若仍被拒，说明你的小程序主体是境内企业且微信做了额外校验。
改用方式 B（COS 默认域名自带备案），或用你自己的已备案域名 CNAME 到该 Pages 地址。

**Q：域名校验文件放了还是失败？**
A：见 `WECHAT_VERIFY.md`。最常见的错是放在子目录——必须和 feed.json 同一层。

**Q：小程序里同步，一直报「拉取失败」？**
A：按 4.3 的四条逐条排查。最常见是域名填成了带路径的形式
（正确：`https://xxx.github.io`，错误：`https://xxx.github.io/repo`）。

**Q：想让新闻更垂直（只收宠物行业）？**
A：编辑 `sources.json` 的 `filter.includeAny`，把无关关键词删掉；
或把 `filter.enabled` 设为 `false` 收全量再靠小程序端分类。

---

## 六、已实测可用的源（2026-10 验证）

| 名称 | 地址 | 条数 |
|---|---|---|
| 国家统计局 | http://www.stats.gov.cn/sj/sjjd/rss.xml | 500 |
| 人民网·财经 | http://www.people.com.cn/rss/finance.xml | 100 |
| 人民网·社会 | http://www.people.com.cn/rss/society.xml | 100 |
| 中新网·财经 | https://www.chinanews.com.cn/rss/finance.xml | 30 |
| 中新网·社会 | https://www.chinanews.com.cn/rss/scroll-news.xml | 30 |
| 钛媒体 | https://www.tmtpost.com/feed | 19 |
| 新浪科技 | https://rss.sina.com.cn/tech/rollnews.xml | 15 |
| Petfood Industry（宠物食品专业媒体） | https://www.petfoodindustry.com/rss | 10 |

> 中文宠物行业垂直 RSS 公开可用的很少，因此默认混合了财经/政策/农业统计源，
> 再用关键词过滤 + 小程序端自动分类收敛到宠物食品垂类。
> 若你有更对口的源（企业公众号接口、行业媒体 RSS），直接替换 `sources.json` 即可。
