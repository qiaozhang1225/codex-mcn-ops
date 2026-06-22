# 抖音解析Pro API 文档

> 解析抖音相关接口，例如获取抖音详情、获取用户信息、获取用户发布信息等。
>
> **使用前必读**：
> - 所有接口都需要 `app_id` 和 `app_secret`，请访问 [https://www.mxnzp.com](https://www.mxnzp.com) 申请。
> - 网站上有客服，有问题可以咨询。
> - 接口返回格式统一为 **JSON**，请求方式见具体接口说明。

## 1. 解析抖音分享链接

获取抖音分享视频的原始接口返回内容。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/detail`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/detail?url=aHR0cHM6Ly92LmRvdXlpbi5jb20vaXJycXBEVVgv&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `url` | 字符串 | **抖音分享视频链接的Base64编码**。例如：先将 `https://v.douyin.com/irrqpDUX/` 进行Base64加密。 |

### 返回参数

太多，请实际请求接口查看。

## 2. 获取抖音用户信息

获取抖音用户的公开信息。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_info`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/user_info?userId=MS4wLjABAAAAtl8SdLLfSYW1pFGaZHdqDY5CKWaMPkRN2sQnepfdFNU7S50sdKNCLdrbKrmmilcn&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `userId` | 字符串 | 抖音用户的 `sec_uid`（可从解析接口返回内容中获得）或用户的**抖音号**。 |

### 返回参数

太多，请实际请求接口查看。

## 3. 获取抖音用户发布的作品列表

获取指定用户发布的作品信息。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_post`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/user_post?cookie=xxxx&userId=MS4wLjABAAAAtl8SdLLfSYW1pFGaZHdqDY5CKWaMPkRN2sQnepfdFNU7S50sdKNCLdrbKrmmilcn&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `userId` | 字符串 | 抖音用户的 `sec_uid`（可从解析接口返回内容中获得）。 |
| `sortType` | 整型数字 | 排序方式：`0` 默认排序，`1` 按热度排序。 |
| `cursor` | 字符串 | 分页信息。第一次请求传空字符串 `""`，后续传入上一次请求返回的 `data` 下的 `max_cursor`。 |
| `cookie` | 字符串 | **登录抖音后的cookie信息**。参考教程：[https://mxnzp.com/sl/7gJH](https://mxnzp.com/sl/7gJH) |

### 返回参数

太多，请实际请求接口查看。

## 4. 获取指定抖音下的一级评论信息

获取指定视频下的一级评论。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/comments`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/comments?url=aHR0cHM6Ly92LmRvdXlpbi5jb20vaVNEamNISFIv&cursor=0&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `url` | 字符串 | **抖音分享链接的Base64编码**。例如：先将 `https://v.douyin.com/iSDjcHHR/` 进行Base64加密。 |
| `cursor` | 字符串 | 分页信息。第一次请求传空字符串 `""`，后续传入上一次请求返回的 `data` 下的 `cursor`。 |

### 返回参数

太多，请实际请求接口查看。

## 5. 获取指定一级评论下的二级评论信息

获取指定一级评论下的回复。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/child_comments`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/child_comments?url=aHR0cHM6Ly92LmRvdXlpbi5jb20vaVNEamNISFIv&cursor=0&commentId=7428927925795668772&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `url` | 字符串 | **抖音分享链接的Base64编码**。例如：先将 `https://v.douyin.com/iSDjcHHR/` 进行Base64加密。 |
| `cursor` | 字符串 | 分页信息。第一次请求传空字符串 `""`，后续传入上一次请求返回的 `data` 下的 `cursor`。 |
| `commentId` | 字符串 | 一级评论的ID，即评论数组下某一项的 `cid` 值。 |

### 返回参数

太多，请实际请求接口查看。

## 6. 解析抖音分享链接精简版 (V3)

解析抖音链接，返回部分核心内容。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/detail/v3`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/detail/v3?url=aHR0cHM6Ly92LmRvdXlpbi5jb20vaXJycXBEVVgv&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `url` | 字符串 | **抖音分享视频链接的Base64编码**。例如：先将 `https://v.douyin.com/irrqpDUX/` 进行Base64加密。 |

### 返回参数

太多，请实际请求接口查看。

## 7. 解析抖音分享链接精简版 (V4 - POST)

V3的POST版本，**无需对链接进行Base64编码**。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/detail/v4`
- **请求方式**： `POST`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/detail/v4?app_id=您的app_id&app_secret=您的app_secret`
- **Content-Type**： `application/json`
- **请求次数抵扣**： 1:1

### 请求参数 (Body - JSON)

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `url` | 字符串 | 抖音分享视频链接，**无需Base64编码**。 |

### 返回参数

太多，请实际请求接口查看。

## 8. 根据关键字搜索抖音视频作品

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/video/search`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/video/search?cookie=xxx&keyword=琅琊榜&offset=0&search_id=&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:5

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `keyword` | 字符串 | 搜索关键字。 |
| `offset` | 字符串 | 偏移量。第一次传 `"0"`，后续翻页传入返回参数中的 `cursor`。 |
| `search_id` | 字符串 | 搜索ID。第一次传空字符串 `""`，后续翻页传入返回参数中的 `searchId`。 |
| `cookie` | 字符串 | 网页上打开抖音官网，登录你的账号后获取的cookie。 |

### 返回参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `cursor` | 字符串 | 分页指示器，用于下次分页请求。 |
| `hasMore` | 整型数字 | `1` 表示有下一页。 |
| `searchId` | 字符串 | 搜索ID，用于下次分页请求。 |
| `items` | 对象数组 | 视频列表项。 |
| `items.title` | 字符串 | 作品标题。 |
| `items.shareUrl` | 字符串 | 作品分享链接。 |
| `items.collect_count` | 整型数字 | 收藏数量。 |
| `items.comment_count` | 整型数字 | 评论数量。 |
| `items.digg_count` | 整型数字 | 点赞数量。 |
| `items.share_count` | 整型数字 | 分享数量。 |

## 9. 提取视频作品的文案内容

提取视频中的音频文字（需配置阿里云百炼KEY）。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/video_to_text/v2`
- **请求方式**： `POST`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/video_to_text/v2?app_id=您的app_id&app_secret=您的app_secret`
- **Content-Type**： `application/json`
- **请求次数抵扣**： 1:2
- **前置准备**： 您需要配置自己的阿里云百炼KEY。[配置地址](https://www.mxnzp.com/console/user-info)（页面靠底部位置）。

> 本项目实测校正：百炼 KEY 配置在 mxnzp 后台即可，本地封装不需要 `ALIYUN_BAILIAN_API_KEY`，也不会把该 KEY 暴露给 Agent prompt。

### 请求参数 (Body - JSON)

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `url` | 字符串 | 抖音分享视频链接，**无需Base64编码**。 |

### 返回参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `audioInfo` | 字符串 | 提取出来的文本内容。 |
| `douyinInfo` | 对象 | 抖音作品信息。 |
| `douyinInfo.audioUrl` | 字符串 | 作品音频URL。 |
| `douyinInfo.collectCount` | 整型数字 | 作品收藏数量。 |
| `douyinInfo.commentCount` | 整型数字 | 作品评论数量。 |
| `douyinInfo.diggCount` | 整型数字 | 作品点赞数量。 |
| `douyinInfo.shareCount` | 整型数字 | 作品分享数量。 |
| `douyinInfo.cover` | 字符串 | 作品封面。 |
| `douyinInfo.desc` | 字符串 | 作品描述信息。 |
| `douyinInfo.nickName` | 字符串 | 作品作者昵称。 |
| `douyinInfo.videoDataSize` | 整型数字 | 作品视频大小。 |
| `douyinInfo.videoDuration` | 整型数字 | 作品视频时长。 |
| `douyinInfo.videoHeight` | 整型数字 | 作品视频高度。 |
| `douyinInfo.videoWidth` | 整型数字 | 作品视频宽度。 |
| `douyinInfo.videoUrl` | 字符串 | 作品视频播放链接。 |

## 10. 根据关键字搜索抖音用户

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user/search`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/user/search?keyword=阿童木&offset=0&search_id=&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:5

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `keyword` | 字符串 | 搜索关键字。 |
| `offset` | 字符串 | 偏移量。第一次传 `"0"`，后续翻页传入返回参数中的 `cursor`。 |
| `search_id` | 字符串 | 搜索ID。第一次传空字符串 `""`，后续翻页传入返回参数中的 `searchId`。 |

### 返回参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `cursor` | 整型数字 | 分页指示器，用于下次分页请求。 |
| `has_more` | 整型数字 | `1` 表示有下一页。 |
| `search_id` | 字符串 | 搜索ID，用于下次分页请求。 |
| `items` | 对象数组 | 用户列表项。 |
| `items.uid` | 字符串 | 用户ID。 |
| `items.sec_uid` | 字符串 | 用户 `sec_uid`。 |
| `items.unique_id` | 字符串 | 抖音号。 |
| `items.nickname` | 字符串 | 用户昵称。 |
| `items.signature` | 字符串 | 用户签名。 |
| `items.follower_count` | 整型数字 | 粉丝数。 |
| `items.avatar` | 字符串 | 用户头像URL。 |

## 11. 获取用户喜欢的作品列表

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user/favorite/list`
- **请求方式**： `POST`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/user/favorite/list?app_id=您的app_id&app_secret=您的app_secret`
- **Content-Type**： `application/json`
- **请求次数抵扣**： 1:1

### 请求参数 (Body - JSON)

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `shareText` | 字符串 | 抖音用户主页的分享链接，**无需Base64编码**。 |
| `cursor` | 字符串 | 分页指示器。分页时请使用上一次请求返回的 `cursor`。 |

### 返回参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `has_more` | 整型数字 | `1` 表示有下一页。 |
| `cursor` | 字符串 | 分页指示器，分页时需要传入。 |
| `items` | 数组 | 作品列表项。 |
| `items.shareUrl` | 字符串 | 作品分享链接。 |
| `items.desc` | 字符串 | 作品标题。 |
| `items.duration` | 整型数字 | 作品视频时长。 |
| `items.digg_count` | 整型数字 | 点赞数量。 |
| `items.share_count` | 整型数字 | 分享数量。 |
| `items.collect_count` | 整型数字 | 收藏数量。 |
| `items.comment_count` | 整型数字 | 评论数量。 |

## 12. 根据抖音号获取用户信息

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_info/dy_id`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/user_info/dy_id?userCode=cctvnews&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `userCode` | 字符串 | 抖音用户的抖音号。 |

### 返回参数

太多，请实际请求接口查看。

## 13. 根据作品ID获取作品的分享链接

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/share_link`
- **请求方式**： `POST`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/share_link?id=7529523895855107362&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:1

### 请求参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | 字符串 | 作品ID。 |

### 返回参数

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `status` | 字符串 | 状态，成功时为 `"success"`。 |
| `target` | 字符串 | 完整的分享链接。 |
| `short_url` | 字符串 | 分享的短链接。 |

---

## 榜单服务

### 14. 榜单垂直分类标签

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/billboard/vertical_tag`
- **请求方式**： `GET`
- **请求次数抵扣**： 1:1
- **返回参数说明**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `children` | 数组 | 子分类列表。 |
| `children.label` | 字符串 | 子分类名称。 |
| `children.value` | 整型数字 | 子分类value值。 |
| `label` | 字符串 | 分类名称。 |
| `value` | 整型数字 | 分类value值。 |

### 15. 抖音视频榜单列表

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/billboard/video`
- **请求方式**： `GET`
- **请求示例**： `https://www.mxnzp.com/api/douyin_pro/billboard/video?date=24&page=1&pageSize=10&subType=1001&rootTag=628&subTag=62804&app_id=您的app_id&app_secret=您的app_secret`
- **请求次数抵扣**： 1:n。若 `pageSize <= 10` 则 `n=5`；若 `pageSize > 10`，则每超过10次 `n` 的值 `+1`。

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `date` | 整型数字 | 时间范围：`1`(一小时内)，`24`(一天内)，`72`(3天内)，`168`(7天内)。 |
| `page` | 整型数字 | 页码。 |
| `pageSize` | 整型数字 | 每页数据大小，最多50。 |
| `subType` | 整型数字 | 榜单类型：`1001`(视频总榜)，`1002`(低粉爆款)，`1003`(高完播率)，`1004`(高涨粉率)，`1005`(高点赞率)。 |
| `rootTag` | 整型数字 | 垂直分类父标签（从接口14获取 `value`）。 |
| `subTag` | 整型数字 | 垂直分类子标签（从接口14获取 `value`，需与父标签对应）。 |

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `shareUrl` | 字符串 | 作品分享链接。 |
| `title` | 字符串 | 作品标题。 |
| `nickname` | 字符串 | 作者昵称。 |
| `avatarUrl` | 字符串 | 作者头像。 |
| `publishTime` | 长整型 | 作品发布时间（时间戳）。 |
| `publishTimeFormat` | 字符串 | 作品发布时间（格式化）。 |
| `coverUrl` | 字符串 | 作品封面。 |
| `likeRate` | 字符串 | 作品点赞率。 |
| `followRate` | 字符串 | 作品关注率。 |
| `score` | 字符串 | 作品当前评分。 |

### 16. 获取抖音城市列表

用于【抖音同城热点榜单】。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/billboard/city_list`
- **请求方式**： `GET`
- **请求次数抵扣**： 1:1

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `label` | 字符串 | 城市名称。 |
| `value` | 整型数字 | 城市Code。 |

### 17. 获取抖音热点分类

用于【抖音实时上升热点榜】、【抖音同城热点榜单】和【抖音热点总榜】。

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/billboard/hot_category`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `category` | 字符串 | `rise`(上升热点榜分类)，`city`(同城热点榜分类)，`total`(热点总榜分类)。 |

- **请求次数抵扣**： 1:1
- **返回参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `label` | 字符串 | 分类名称。 |
| `value` | 整型数字数组 | 分类value值。 |

### 18. 抖音实时上升热点榜

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/billboard/hot_rise`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `page` | 整型数字 | 页码。 |
| `pageSize` | 整型数字 | 每页数据大小，最多50。 |
| `category` | 整型数字 | 从接口17获取的 `value`。 |
| `order` | 字符串 | `rank`(按热度排名)，`rank_diff`(按排名变化排名)。 |

- **请求次数抵扣**： 1:n。若 `pageSize <= 10` 则 `n=5`；若 `pageSize > 10`，则每超过10次 `n` 的值 `+1`。

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `rank` | 整型数字 | 排名。 |
| `billboardName` | 字符串 | 热点名称。 |
| `billboardId` | 整型数字 | 热点ID（后续接口需要）。 |
| `hotScore` | 整型数字 | 热力值。 |
| `createAt` | 长整型 | 创建时间（时间戳）。 |
| `createAtFormat` | 字符串 | 创建时间（格式化）。 |
| `category` | 整型数字 | 分类value。 |
| `categoryName` | 字符串 | 分类名称。 |

### 19. 抖音同城热点榜单

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/billboard/hot_city`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `page` | 整型数字 | 页码。 |
| `pageSize` | 整型数字 | 每页数据大小，最多50。 |
| `category` | 整型数字 | 从接口17获取的 `value`。 |
| `order` | 字符串 | `rank`(按热度排名)，`rank_diff`(按排名变化排名)。 |
| `cityCode` | 整型数字 | 从接口16获取的城市Code。 |

- **请求次数抵扣**： 同接口18。

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `rank` | 整型数字 | 排名。 |
| `billboardName` | 字符串 | 热点名称。 |
| `billboardId` | 整型数字 | 热点ID（后续接口需要）。 |
| `hotScore` | 整型数字 | 热力值。 |
| `createAt` | 长整型 | 创建时间（时间戳）。 |
| `createAtFormat` | 字符串 | 创建时间（格式化）。 |
| `category` | 整型数字 | 分类value。 |
| `categoryName` | 字符串 | 分类名称。 |

### 20. 抖音热点总榜

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/billboard/hot_total` (注：原文示例中地址与19相同，可能为笔误，实际应为total相关)
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `page` | 整型数字 | 页码。 |
| `pageSize` | 整型数字 | 每页数据大小，最多50。 |
| `category` | 整型数字 | 从接口17获取的 `value`。 |
| `order` | 字符串 | `rank`(按热度排名)，`rank_diff`(按排名变化排名)。 |

- **请求次数抵扣**： 同接口18。
- **返回参数**： 同接口18。

---

## 高级功能

### 21. 抖音视频点赞观众画像

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/aweme_digs_interest`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `workInfo` | 字符串 | 作品ID或作品分享链接。 |
| `type` | 整型数字 | `1`(手机价格分布)，`2`(性别分布)，`3`(年龄分布)，`4`(地域-省份)，`5`(地域-城市)，`6`(城市等级分布)，`7`(手机品牌分布)。 |

- **请求次数抵扣**： 1:n。若 `workInfo` 是链接则 `n=6`；若是作品ID则 `n=5`。
- **返回参数**： 太多，请实际请求查看。

### 22. 抖音用户粉丝画像

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_fans_data`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `userInfo` | 字符串 | 用户 `sec_id` 或用户的作品分享链接。 |
| `type` | 整型数字 | `1`(手机价格分布)，`2`(性别分布)，`3`(年龄分布)，`4`(地域-省份)，`5`(地域-城市)，`6`(城市等级分布)，`7`(手机品牌分布)，`8`(粉丝兴趣)。 |

- **请求次数抵扣**： 1:n。若 `userInfo` 是链接则 `n=6`；若是用户ID则 `n=5`。
- **返回参数**： 太多，请实际请求查看。

### 23. 获取用户合集列表

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_mix`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `userInfo` | 字符串 | 用户 `sec_id` 或用户主页的分享链接。 |
| `count` | 整型数字 | 每页数量，最大值50。 |
| `cursor` | 字符串 | 分页游标，用上一次接口返回的 `cursor` 值。 |

- **请求次数抵扣**： 1:n。若 `count <= 10` 则 `n=2`；若 `count > 10`，则每超过10次 `n` 的值 `+2`。

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `has_more` | 布尔值 | `true` 表示有下一页。 |
| `cursor` | 字符串 | 分页指示器。 |
| `items` | 数组 | 合集列表。 |
| `items.mix_id` | 字符串 | 合集ID。 |
| `items.desc` | 字符串 | 合集名称。 |
| `items.mix_name` | 字符串 | 合集名称。 |
| `items.create_time` | 字符串 | 合集创建时间。 |

### 24. 获取指定合集详情

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_mix_info`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `mixId` | 字符串 | 合集ID（从接口23获取）。 |

- **请求次数抵扣**： 1:2
- **返回参数**： 太多，请实际请求查看。

### 25. 获取指定合集中的视频列表

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_mix_list`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `mixId` | 字符串 | 合集ID（从接口23获取）。 |
| `cursor` | 字符串 | 分页游标。 |

- **请求次数抵扣**： 1:2

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `has_more` | 布尔值 | `true` 表示有下一页。 |
| `cursor` | 字符串 | 分页指示器。 |
| `items` | 数组 | 视频列表。 |
| `items.shareUrl` | 字符串 | 作品分享链接。 |
| `items.desc` | 字符串 | 作品标题。 |
| `items.duration` | 整型数字 | 作品时长。 |
| `items.digg_count` | 整型数字 | 点赞数。 |
| `items.share_count` | 整型数字 | 分享数。 |
| `items.collect_count` | 整型数字 | 收藏数。 |
| `items.post_time` | 字符串 | 发布时间。 |
| `items.comment_count` | 整型数字 | 评论数。 |

### 26. 获取用户短剧列表

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_series`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `userInfo` | 字符串 | 用户 `sec_id` 或用户主页的分享链接。 |
| `cursor` | 字符串 | 分页游标。 |

- **请求次数抵扣**： 1:2

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `has_more` | 布尔值 | `true` 表示有下一页。 |
| `cursor` | 字符串 | 分页指示器。 |
| `items` | 数组 | 短剧列表。 |
| `items.series_id` | 字符串 | 短剧ID。 |
| `items.desc` | 字符串 | 短剧名称。 |
| `items.series_name` | 字符串 | 短剧名称。 |
| `items.create_time` | 字符串 | 短剧创建时间。 |

### 27. 获取指定短剧详情

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_series_info`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `seriesId` | 字符串 | 短剧ID（从接口26获取）。 |

- **请求次数抵扣**： 1:2
- **返回参数**： 太多，请实际请求查看。

### 28. 获取指定短剧中的视频列表

- **接口地址**： `https://www.mxnzp.com/api/douyin_pro/user_series_list`
- **请求方式**： `GET`
- **请求参数**：

| 名称 | 类型 | 说明 |
| :--- | :--- | :--- |
| `seriesId` | 字符串 | 短剧ID（从接口26获取）。 |
| `cursor` | 字符串 | 分页游标。 |

- **请求次数抵扣**： 1:2

| 返回参数 | 类型 | 说明 |
| :--- | :--- | :--- |
| `has_more` | 布尔值 | `true` 表示有下一页。 |
| `cursor` | 字符串 | 分页指示器。 |
| `items` | 数组 | 视频列表（参数同接口25的 `items`）。 |
